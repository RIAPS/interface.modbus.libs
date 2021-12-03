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

class ModbusSlave(threading.Thread):
    def __init__( self, logger, config, deviceport ) :
        threading.Thread.__init__( self )
        self.logger = logger
        self.dvc = None
        self.deviceport = deviceport
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

    def read_modbus(self, command ):
        modbus_func = self.dvc[ command ]
        # read Modbus command parameters from yaml file
        function_code = modbus_func['function']
        starting_address = modbus_func['start']
        length = modbus_func['length']
        # scale value per yaml file and convert to int to send to Modbus slave

        if 'data_format' in list(modbus_func.keys()):
            data_fmt = modbus_func['data_format']
        else:
            data_fmt = ''

        response = list( self.master.execute( self.slave,
                                        getattr(cst, function_code),
                                        starting_address,
                                        quantity_of_x=length,
                                        data_format=data_fmt ) )
        values = []
        for v in response:
            values.append( float( v * modbus_func['Units'][0] ) )  

        return values

    def write_modbus(self, command, values ):
        modbus_func = self.dvc[ command ]
        # read Modbus command parameters from cofiguration
        function_code = modbus_func['function']
        starting_address = modbus_func['start']
        length = modbus_func['length']
 
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

        self.logger.warn( f"values={values}, length={length}, modbus values = {modbus_value}" )

        modbus_response = self.master.execute( self.slave,
                                        getattr(cst, function_code),
                                        starting_address,
                                        output_value=modbus_value,
                                        quantity_of_x=length,
                                        data_format=data_fmt )

        response = list( modbus_response )
        self.logger.warn( f"modbus reply = {response}" )
        # if the write is successful the result is:
        # [ (starting address), (number of registers written) ]
        if len( response ) == 2 :
            if response[0] == starting_address :
                if response[1] == length :
                    response = [ starting_address, ]
                    for v in values :
                        response.append( v )
        else:
            response = [ starting_address, None ]

        return response

    def run(self):
        self.logger.info( f"Modbus slave {self.device_name} thread started" ) 
        self.plug = self.deviceport.setupPlug(self)
        self.poller = zmq.Poller()
        self.poller.register( self.plug, zmq.POLLIN )
        if not self.ModbusConfigError :
            while self.active.is_set() :
                s = dict( self.poller.poll( 1000.0 ) )
                if not self.dormant.is_set() :
                    if len(s) > 0 :
                        ansmsg = device_capnp.DeviceAns.new_message()
                        ansmsg.error = 0
                        msg = self.plug.recv_pyobj()
                        cmd = f"{msg.param}_{msg.operation}"
                        if msg.operation == "READ" :
                            response = self.read_modbus( cmd )
                        elif msg.operation == "WRITE" :
                            values = msg.values
                            response = self.write_modbus( cmd, values )
                        else:
                            response = [None]
                            ansmsg.error = ModbusSystem.Errors.InvalidOperation
                               
                        ansmsg.device = self.get_device_name()
                        ansmsg.operation = msg.operation
                        ansmsg.param = msg.param
                        ansmsg.values = response
                        ansmsg.msgcounter = msg.msgcounter    
                        self.plug.send_pyobj( ansmsg )
                else:
                    self.logger.info( f"Device is dormant, ignoring commands!" )
            self.logger.info( f"Modbus slave {self.get_device_name()} thread exited." ) 
        else:
            self.logger.info( f"Modbus slave {self.get_device_name()} thread exited due to configuration errors!" ) 

