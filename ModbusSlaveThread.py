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
    def __init__( self, logger, dvcname, slaveid, master, params, eventport, interval_ms ) :
        threading.Thread.__init__( self )
        self.logger = logger
        self.params = params
        self.master = master
        self.device_name = dvcname
        self.eventport = eventport
        self.interval_ms = interval_ms
        self.slave = slaveid
        self.param_keys = self.params.keys()
        self.numparms = len( self.param_keys )

        if self.numparms >= 1 :
            self.poll_interval_ms = self.interval_ms/self.numparms
        else:
            self.poll_interval_ms = self.interval_ms

        self.plug = None
        self.active = threading.Event()
        self.active.set()

    def get_plug( self ):
        return self.plug

    def deactivate(self):
        self.active.clear()

    # Do not allow the polling loop to send messages to the modbus device
    def disable_polling(self):
        self.logger.info("Disabling modbus polling for - %s" % self.device_name)
        self.poll_exit = True

    # Allow the polling loop to send messages to the modbus device
    def enable_polling(self):
        self.logger.info("Enabling modbus polling for - %s" % self.device_name)
        self.poll_exit = False

    """ Function creates a dictionary of associated items    
    start : the address of the first register that was read
    length : the number of registers read
    dev : the configuration data for all modbus-device's commands
    data : the raw data returned from the modbus query

    This function matches the data, by index, with the configured address and then
    adds an entry in the dictionary.
    Each entry contains:
    Value: In floating point and scaled as required
    Units: The units of the measurement
    Address: The register address"""

    def format_multi_register_read(self, start, length, dev, data):
        resp_dict = {}
        for p in dev:
            # only look at read parameter definitions in the device configuration
            if p.find('_READ') != -1:
                # get the parameter information
                parm = dev[p]
                # make sure there is a units field in the definition
                if 'Units' in list(parm.keys()):
                    cur_addr = parm['start']
                    cur_len = parm['length']
                    # do add entries for commands that read multiple registers
                    if cur_len == 1:
                        if start <= cur_addr < (start + length):
                            # apply the scale and format the data into floating point
                            cur_scaler = float(parm['Units'][0])
                            cur_units = parm['Units'][1]
                            index = cur_addr - start
                            resp_dict[p] = {'Value': (float(data[index]) * cur_scaler),
                                            'Units': cur_units,
                                            'Address': cur_addr}
                        else:
                            pass
                else:
                    pass
            else:
                pass

        return resp_dict

    def run(self):
        self.logger.info( f"Modbus poller {self.device_name} thread started" ) 
        self.plug = self.eventport.setupPlug(self)
        self.poller = zmq.Poller()
        self.poller.register( self.plug, zmq.POLLIN )

        while self.active.is_set() :
            for k in self.param_keys :
                cmdlist = self.params[k]
                function_code = getattr(cst, cmdlist[0])
                starting_address = cmdlist[1]
                length = cmdlist[2]
                scale = cmdlist[3]
                units = cmdlist[4]
                data_fmt = cmdlist[5]
                max_thr = cmdlist[6]
                min_thr = cmdlist[7]
                s = dict( self.poller.poll( self.poll_interval_ms ) )
                if len(s) > 0 : # process messages from the main slave thread
                    # currently any message sent to the poller terminates the thread
                    # this can do other things if needed
                    msg = self.plug.recv_pyobj()
                    self.deactivate()
                    break
                else:  # do polling 
                    start = dt.datetime.now()
                    #read the parameter from the Modbus device           
                    response = list( self.master.execute(   self.slave,
                                                            function_code,
                                                            starting_address,
                                                            quantity_of_x=length,
                                                            data_format=data_fmt ) )

                    PostNewEvent = True

                    if len( response ) == 1:
                        response[0] = response[0] * scale
                        if max_thr != None and min_thr != None :
                            if max_thr >= response[0] and min_thr <= response[0] :
                                PostNewEvent = False
                    else:
                        for idx, n in response :
                            response[idx] = float(n)    

                    stop = dt.datetime.now()
                    if PostNewEvent == True :
                        evtmsg = device_capnp.DeviceEvent.new_message()
                        evtmsg.event = "POLLED"
                        evtmsg.command = "READ"
                        evtmsg.names = list( [ k, ] )
                        evtmsg.values = list( response )
                        evtmsg.units = list( [ units, ] )
                        evtmsg.device = self.device_name
                        evtmsg.error = 0
                        evtmsg.et = (stop-start).total_seconds()
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
        self.device = "NONE"

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
                        self.device = self.dvc[comname]['device']
                        self.master = modbus_rtu.RtuMaster(serial.Serial(   port=self.device,
                                                                            baudrate=self.dvc[comname]['baudrate'],
                                                                            bytesize=self.dvc[comname]['bytesize'],
                                                                            parity=self.dvc[comname]['parity'],
                                                                            stopbits=self.dvc[comname]['stopbits'],
                                                                            xonxoff=self.dvc[comname]['xonxoff'])   )

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
                        self.device = "TCP"
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


                if self.master != None :
                    if self.eventport != None:
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

                                    if self.dvc["poll"][v]:
                                        max_thr = self.dvc["poll"][v][0]
                                        min_thr = self.dvc["poll"][v][1]
                                    else:
                                        max_thr = None
                                        min_thr = None

                                    self.poll_dict[v] = [   function_code, 
                                                            starting_address, 
                                                            length, 
                                                            scale, 
                                                            units, 
                                                            data_fmt,
                                                            max_thr,
                                                            min_thr ]
                        
                        # If there are parameters to poll then create a polling thread object 
                        if len( self.poll_dict ) == 0 :
                            self.logger.warn(f"Modbus poller will not be started!")                        
                            self.logger.warn(f"Modbus poller parameters are either not configured or not present in configuration file.")                        
                        else:
                            self.polling_thread = ModbusPoller( self.logger, 
                                                                self.device_name,
                                                                self.slave,
                                                                self.master, 
                                                                self.poll_dict,
                                                                self.eventport, 
                                                                self.interval )

                    else:
                        self.logger.info(f"Modbus poller has no RIAPS publish port defined.")                        

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
    
    def enable_debug_mode(self, enable=True):
        self.debugMode = enable
        self.logger.info( f"Modbus Slave [{self.device_name}] debugMode is set to [{self.debugMode}]" )

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

    # set an individual bit on a value
    def set_bit(self, value, bit):
        """ Sets a bit in the data 'value' at position index specified by 'bit' """
        return value | (1 << bit)

    # clear an individual bit on a value
    def clr_bit(self, value, bit):
        """ Clears a bit in the data 'value' at position index specified by 'bit' """
        return value & ~(1 << bit)

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
                        ansmsg = device_capnp.DeviceAns.new_message()
                        ansmsg.error = 0
                        for idx, p in enumerate(msg.params):
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
                    self.logger.info( f"Modbus slave {self.get_device_name()} polling thread exited normally." )     
                                             
            self.logger.info( f"Modbus slave {self.get_device_name()} thread exited." ) 
        else:
            self.logger.info( f"Modbus slave {self.get_device_name()} thread exited due to configuration errors!" ) 

