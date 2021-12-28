import time
import yaml
import os
import struct
import can
import threading
import queue
import zmq
import time
import datetime as dt
from modbus_tk import modbus_rtu
from modbus_tk import modbus_tcp
import modbus_tk.defines as cst
from libs.ModbusSystemSettings import ModbusSystem
import libs.helper as tc
import serial
import spdlog
import device_capnp

class ModbusPoller( threading.Thread ) :
    def __init__( self, logger, dvcname, master, params, eventport, interval_ms ) :
        threading.Thread.__init__( self )
        self.logger = logger
        self.params = params
        self.master = master
        self.device_name = dvcname
        self.eventport = eventport
        self.interval_ms = interval_ms
        self.slave = 1
        self.numparms = len( self.params )
        if self.numparms < 1 :
            self.numparms = 1

        self.poll_interval_ms = self.interval_ms/self.numparms
        self.plug = None
        self.active = threading.Event()
        self.active.set()
        self.param_keys = self.params.keys()
        self.logger.info( f"Modbus polled parameters..." ) 

    def get_plug( self ):
        return self.plug

    def deactivate(self):
        self.active.clear()

    def run(self):
        current_item = 1
        self.logger.info( f"Modbus poller {self.device_name} thread started" ) 
        self.plug = self.eventport.setupPlug(self)
        self.poller = zmq.Poller()
        self.poller.register( self.plug, zmq.POLLIN )

        while self.active.is_set() :
            for k in self.param_keys :
                # self.logger.info( f"{k}:{self.params[k]}" ) 
                # cmdlist = [ function_code, starting_address, length, scale, units, data_fmt ]
                cmdlist = self.params[k]
                s = dict( self.poller.poll( self.poll_interval_ms ) )
                if len(s) > 0 :
                    # currently any message sent to the poller terminates the thread
                    # this can do other things if needed
                    msg = self.plug.recv_pyobj()
                    self.deactivate()
                    break
                else:
                    response = list( self.master.execute(   self.slave,
                                                            getattr(cst, cmdlist[0]),
                                                            cmdlist[1],
                                                            quantity_of_x=cmdlist[2],
                                                            data_format=cmdlist[5] ) )
                    # do polling            
                    # if current_item < self.numparms :
                    evtmsg = device_capnp.DeviceEvent.new_message()
                    evtmsg.event = "POLLED"
                    evtmsg.command = str( k )
                    evtmsg.names = list( [ k, ] )
                    evtmsg.values = list( response )
                    evtmsg.units = list( [cmdlist[4], ] )
                    evtmsg.device = self.device_name
                    evtmsg.error = 0
                    evtmsg.et = 0.0
                    msgbytes =  evtmsg.to_bytes()
                    self.plug.send_pyobj( evtmsg )

class ModbusSlave(threading.Thread):
    def __init__( self, logger, config, deviceport, eventport=None ) :
        threading.Thread.__init__( self )
        self.logger = logger
        self.dvc = None
        self.deviceport = deviceport
        self.eventport = eventport
        self.polling_thread = None
        self.poll_dict = {}
        self.active = threading.Event()
        self.active.set()
        self.dormant = threading.Event()
        self.dormant.clear()
        self.address = None
        self.port = None
        self.id = 0
        self.plug = None
        self.master = None
        self.slave = None
        self.debugMode = False

        try:
            self.device_name = list(config.keys())[0]
            self.dvc = config[self.device_name]
            self.ModbusConfigError = False
        except KeyError as kex:
            self.logger.info(f"Modbus device configuration error: {kex}")    
            self.ModbusConfigError = True
 
        if not self.ModbusConfigError :
            try : # handle dictionary key errors
                # set slave id. Argument required by modbus tk to send commands to Modbus
                self.slave = self.dvc['Slave']
                # set the polling interval
                self.interval = self.dvc['Interval']
                # set the debug mode for logging
                self.debugMode = self.dvc["debugMode"]
                # Start Modbus master
                # if Serial is defined in config file then use serial communication
                if 'RS232' in self.dvc :
                    comname = 'RS232'
                elif 'Serial' in self.dvc :
                    comname = 'Serial'
                elif 'TCP' in self.dvc :
                    comname = 'TCP'
                else:
                    comname = ""

                if comname == 'RS232' or comname == 'Serial' :
                    try:
                        self.master = modbus_rtu.RtuMaster(serial.Serial(port=self.dvc[comname]['device'],
                                                                        baudrate=self.dvc[comname]['baudrate'],
                                                                        bytesize=self.dvc[comname]['bytesize'],
                                                                        parity=self.dvc[comname]['parity'],
                                                                        stopbits=self.dvc[comname]['stopbits'],
                                                                        xonxoff=self.dvc[comname]['xonxoff']))

                        self.master.set_timeout(ModbusSystem.Timeouts.TTYSComm)
                        self.master.set_verbose(ModbusSystem.Debugging.Verbose)
                        self.logger.info( 'Modbus RTU Connected to Slave [{0}] on Port [{1}]'.format( self.slave, self.device ) )
                    except Exception as ex:
                        self.logger.info('Modbus RTU Creation Exception: {0}'.format(ex))
                        self.master = None

                elif comname == 'TCP':
                    addr = self.dvc[comname]['Address']
                    port = self.dvc[comname]['Port']

                    try:
                        self.master = modbus_tcp.TcpMaster(addr, port)
                        self.master.set_timeout(ModbusSystem.Timeouts.TCPComm)
                        self.master.set_verbose(ModbusSystem.Debugging.Verbose)
                        self.logger.info( 'Modbus TCP Connected to Slave [{0}] on Address [{1}:{2}]'.format( self.slave, addr, port ) )
                    except Exception as ex:
                        self.logger.info(f"Modbus TCP Creation Exception: {ex}")
                        self.master = None
                else :
                    self.logger.info(f"Modbus device has no communication configuration defined.")
                    self.master = None


                if self.master != None and self.eventport != None:
                    if "poll" in list( self.dvc.keys() ):
                        if self.dvc["poll"] :
                            for v in self.dvc["poll"] :
                                poll_func = self.dvc[ v ]
                                function_code = poll_func['function']
                                starting_address = poll_func['start']
                                length = poll_func['length']
                                scale = poll_func['Units'][0]
                                units = poll_func['Units'][1]
                                if 'data_format' in list(poll_func.keys()):
                                    data_fmt = poll_func['data_format']
                                else:
                                    data_fmt = ''
                                
                                self.poll_dict[v] = [ function_code, starting_address, length, scale, units, data_fmt ]

                            if len( self.poll_dict.keys() ) >= 1 :
                                self.polling_thread = ModbusPoller( self.logger, 
                                                                    self.device_name,
                                                                    self.master, 
                                                                    self.poll_dict,
                                                                    self.eventport, 
                                                                    self.interval )

            except KeyError as kex:
                self.logger.info(f"Modbus configuration is missing required setting: {kex}")    
                self.ModbusConfigError = True

        else:
            pass # Device cannot operate due to configuration error

        self.logger.info( f"ModbusSlave __init__ complete" )

    def get_device_name(self):
        return self.device_name

    def get_plug( self ):
        return self.plug

    def deactivate(self):
        self.active.clear()

    def pause(self):
        self.dormant.set()

    def resume(self):
        self.dormant.clear()

    def read_modbus(self, command ):
        modbus_func = self.dvc[ command ]
        # read Modbus command parameters from yaml file
        function_code = modbus_func['function']
        starting_address = modbus_func['start']
        length = modbus_func['length']
        units = modbus_func['Units'][1]
        # scale value per yaml file and convert to int to send to Modbus slave

        if 'data_format' in list(modbus_func.keys()):
            data_fmt = modbus_func['data_format']
        else:
            data_fmt = ''

        if self.debugMode :
            t1 = dt.datetime.now()
            self.logger.info( f"Reading: starting_address={starting_address}, quantity_of_x={length}, timestamp={t1}" )
        
        response = list( self.master.execute( self.slave,
                                        getattr(cst, function_code),
                                        starting_address,
                                        quantity_of_x=length,
                                        data_format=data_fmt ) )
        
        if self.debugMode :
            t1 = dt.datetime.now()
            self.logger.info( f"Response: starting_address={starting_address}, response={response}, timestamp={t1}" )

        values = []
        for v in response:
            values.append( float( v * modbus_func['Units'][0] ) )  

        results = { "command" : command, "values" : values, "units" : units }

        if self.debugMode :
            self.logger.info( f"Return values: {results}" )

        return results

    def write_modbus(self, command, values ):
        results = {}
        modbus_func = self.dvc[ command ]
        # read Modbus command parameters from cofiguration
        function_code = modbus_func['function']
        starting_address = modbus_func['start']
        length = modbus_func['length']
        units = modbus_func['Units'][1]

 
        if 'data_format' in list(modbus_func.keys()):
            data_fmt = modbus_func['data_format']
        else:
            data_fmt = ""

        if data_fmt == "" :
            modbus_value = []
            for v in values:
                modbus_value.append( int( v / modbus_func['Units'][0] ) )        
        else:
            modbus_value = values       

        if self.debugMode :
            self.logger.info( f"values={values}, length={length}, modbus values = {modbus_value}" )

        modbus_response = self.master.execute( self.slave,
                                        getattr(cst, function_code),
                                        starting_address,
                                        output_value=modbus_value,
                                        quantity_of_x=length,
                                        data_format=data_fmt )

        response = list( modbus_response )
        if self.debugMode :
            self.logger.info( f"modbus reply = {response}" )
        # if the write is successful the result is:
        # [ (starting address), (number of registers written) ]
        if len( response ) == 2 :
            if response[0] == starting_address :
                if response[1] == length :
                    results = { "command" : command, "values" : values, "units" : units }
        else:
            results = { "command" : command, "values" : [], "units" : units }


        return results

    def run(self):
        self.logger.info( f"Modbus slave {self.device_name} thread started" )             
        self.plug = self.deviceport.setupPlug(self)
        self.poller = zmq.Poller()
        self.poller.register( self.plug, zmq.POLLIN )
        if not self.ModbusConfigError :
            #if a polling thread was configured start it now
            if self.polling_thread != None :
                self.polling_thread.start()

            while self.active.is_set() :
                s = dict( self.poller.poll( 1000.0 ) )
                if not self.dormant.is_set() :
                    if len(s) > 0 :
                        msg = self.plug.recv_pyobj()
                        results = []
                        for idx, p in enumerate(msg.params):
                            ansmsg = device_capnp.DeviceAns.new_message()
                            ansmsg.error = 0
                            cmd = f"{p}_{msg.operation}"
                            if self.debugMode :
                                self.logger.info( f"ModbusSlaveThread {self.get_device_name()} message request={cmd}" )
                            if msg.operation == "READ" :
                                response = self.read_modbus( cmd )
                            elif msg.operation == "WRITE" :
                                if len( msg.params ) == len( msg.values ) :
                                    values = [ msg.values[idx],]
                                else:
                                    values = None 
                                    self.logger.warn( f"ModbusSlaveThread {self.get_device_name()} block write not implemented={cmd}" ) 
                                if values != None:
                                    response = self.write_modbus( cmd, values )
                            else:
                                response = {}
 
                            if self.debugMode :
                                self.logger.info( f"ModbusSlaveThread {self.get_device_name()} results={response}" ) 
                            
                            results.append( response )
                            if len( response["values"] ) == 0:
                                ansmsg.error = ModbusSystem.Errors.InvalidOperation 


                        vals = []
                        units = []
                        parms = [] 
                        for d in results:
                            vals.append( d["values"][0] )
                            units.append( d["units"] )
                            parms.append( d["command"] )
                        if self.debugMode :     
                            self.logger.info( f"{self.get_device_name()} vals={vals}" ) 
                            self.logger.info( f"{self.get_device_name()} units={units}" ) 
                            self.logger.info( f"{self.get_device_name()} parms={parms}" ) 
                        ansmsg.values = list(vals)
                        ansmsg.units = list(units)
                        ansmsg.params = list(parms)
                        ansmsg.device = self.get_device_name()
                        ansmsg.operation = msg.operation
                        ansmsg.msgcounter = msg.msgcounter
                        self.plug.send_pyobj( ansmsg )
                else:
                    self.logger.info( f"Device is dormant, ignoring commands!" )

            if self.polling_thread != None :
                self.polling_thread.deactivate()
                self.polling_thread.join( 5.0 )
                if self.polling_thread.is_alive() :
                    self.logger.info( f"Modbus slave {self.get_device_name()} polling thread did not exit in the alloted time." )
                else:
                    self.logger.info( f"Modbus slave {self.get_device_name()} poling thread exited." )     
                                             
            self.logger.info( f"Modbus slave {self.get_device_name()} thread exited." ) 
        else:
            self.logger.info( f"Modbus slave {self.get_device_name()} thread exited due to configuration errors!" ) 

