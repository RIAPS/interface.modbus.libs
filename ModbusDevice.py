# riaps:keep_import:begin
import time

from riaps.run.comp import Component
from libs.ModbusSystemSettings import ModbusSystem
from libs.ModbusSlaveThread import ModbusSlave
import yaml
from modbus_tk import modbus_tcp
from modbus_tk import modbus_rtu
import modbus_tk.defines as cst
import spdlog
import capnp
import device_capnp
import os
import datetime
import struct
import serial

import libs.helper as helper


# riaps:keep_import:end


class ModbusDevice(Component):
    # riaps:keep_constr:begin
    def __init__(self, config):
        super(ModbusDevice, self).__init__()

        self.ModbusConfigError = True

        self.poll_exit = False

        self.logger.info("starting")

        self.pid = os.getpid()

        self.ModbusConfigError = False
        self.modbus_device_cfgs = {}
        self.modbus_device_keys = []
        self.devices = {}
        self.global_debug_mode = False

        try:
            if os.path.exists( config ) :
                # Load config file to interact with Modbus device
                with open(config, 'r') as cfglist:
                    configs = yaml.safe_load( cfglist )

                if "GobalDebugMode" in list( configs.keys() ):
                    self.global_debug_mode = configs["GobalDebugMode"]
                
                for c in configs["configs"]:
                    cfgdev = None
                    if os.path.exists( c ) :
                        with open(c, 'r') as dvc:
                            cfgdev = yaml.safe_load( dvc )

                        if cfgdev != None :
                            devname = list(cfgdev.keys())
                            self.modbus_device_cfgs[devname[0]] = cfgdev
                    else:
                        self.ModbusConfigError = True
                        self.logger.info( f"Device config:{c} does not exist!" )
                

                # Get the names of all the devices
                self.modbus_device_keys = list( self.modbus_device_cfgs.keys() )

            else:
               self.ModbusConfigError = True
               self.logger.info( 'System configuration file does not exist [{0}].'.format( config ) )

        except OSError:
            self.ModbusConfigError = True
            self.logger.info( 'File I/O error [{0}].'.format( config ) )

        if self.ModbusConfigError :
            self.logger.info( f"{len( self.modbus_device_keys )} Modbus device configuration error!")
        else:    
            self.logger.info( f"{len( self.modbus_device_keys )} Modbus devices found in configuration:")
            for k in self.modbus_device_keys :
                self.logger.info( f"{k}")

    # riaps:keep_constr:end

# riaps:keep_modbus_evt_port:begin
    def on_modbus_evt_port(self):
        msg = self.modbus_evt_port.recv_pyobj()
        evtmsg = device_capnp.DeviceEvent.new_message()
        evtmsg.event = msg.event
        evtmsg.command = msg.command
        evtmsg.names = list(msg.names)
        evtmsg.values = list(msg.values)
        evtmsg.units = list(msg.units)
        evtmsg.device = msg.device
        evtmsg.error = msg.error
        evtmsg.et = msg.et
        msgbytes =  evtmsg.to_bytes()
        self.event_port.send( msgbytes )
 # riaps:keep_modbus_evt_port:end


# riaps:keep_modbus_cmd_port:begin
    def on_modbus_cmd_port(self):
        msg = self.modbus_cmd_port.recv_pyobj()
        ansmsg = device_capnp.DeviceAns.new_message()
        ansmsg.error = msg.error
        ansmsg.device = msg.device
        ansmsg.operation = msg.operation
        ansmsg.params = list(msg.params)
        ansmsg.values = list(msg.values)
        ansmsg.msgcounter = msg.msgcounter    
        msgbytes =  ansmsg.to_bytes()
        self.device_port.send( msgbytes )
# riaps:keep_modbus_cmd_port:end


    # riaps:keep_device_port:begin
    def on_device_port(self):
        # receive
        start = datetime.datetime.now()  # measure how long it takes to complete query
        msg_bytes = self.device_port.recv()  # required to remove message from queue
        msg = device_capnp.DeviceQry.from_bytes(msg_bytes)

        dvcname = msg.device
        # if the device name is empty then use the first device in the list of keys
        if dvcname == "" :
            dvcname = self.modbus_device_keys[0]

        dthd =  self.devices[ dvcname ]
        plug_identity = self.modbus_cmd_port.get_plug_identity( dthd.get_plug() )
        self.modbus_cmd_port.set_identity( plug_identity )
        self.modbus_cmd_port.send_pyobj( msg )

    # riaps:keep_device_port:end

    # riaps:keep_poller:begin
    def on_poller(self):
        now = self.poller.recv_pyobj()
    # riaps:keep_poller:end

    # riaps:keep_impl:begin
    def handleActivate(self):
        if not self.ModbusConfigError :
            for dvcname in self.modbus_device_keys:
                device_thread = ModbusSlave(self.logger, self.modbus_device_cfgs[dvcname], self.modbus_cmd_port, self.modbus_evt_port )
                # override the local debug setting if the top level configuration requests it
                device_thread.enable_debug_mode( enable=self.global_debug_mode )
                dn = device_thread.get_device_name()    
                self.devices[dn] = device_thread 
                self.devices[dn].start()
                while self.devices[dn].get_plug() == None :
                    time.sleep( 0.1 )
        
        # ppost a startup event showing the device is active 
        evt = device_capnp.DeviceEvent.new_message()
        evt.event = "ACTIVE"
        evt.command = "STARTUP"
        evt.values = [ 0.0 ]      
        evt.names = [ "" ]
        evt.units = [ "" ]
        evt.device = f"{self.modbus_device_keys}"
        evt.error = 0
        evt.et = 0.0
        self.postEvent( evt )
        self.logger.info(f"handleActivate() complete")


   # Should be called before __destroy__ when app is shutting down.  
   # this does not appear to work correctly       
    def handleDeactivate( self ):
        self.logger.info( "Deactivating Modbus Device" )
        self.logger.info( f"self.master is {self.master}" )

    # Format and error event message that will get passed to an upper level
    # RIAPS component
    def error( self, evt, error, vals, errnum = -1, et=None ):
        evt.device = self.device_name
        evt.event = 'ERROR'
        evt.error = errnum
        evt.values = [-1.0, ]
        evt.names = [f"{error} ({vals})"]
        evt.units = ['ERROR', ]
        if et != None:
            evt.et = et
        return evt

    # Clean up and shutdown 
    def __destroy__(self):
        keys = list( self.devices.keys() )
        for k in keys:
            thd = self.devices[k]
            thd.deactivate()
            thd.join( timeout=5.0 )
            if thd.is_alive() :
                self.logger.warn( f"Failed to terminate thread!" )

        self.logger.info(f"__destroy__() complete")
 
    #post an event if the required attributes exist and the event is valid
    def postEvent(self, evt):
        try:
            if evt != None :
                self.event_port.send( evt.to_bytes() )
            else:
                self.logger.info( f"Invalid event: {evt}!" )                
        except AttributeError:
            self.logger.info( f"Modbus attribute [self.event_port] is not defined! Cannot process event{evt}! " )  

 
    # Do not allow the polling loop to send messages to the modbus device
    def disable_polling(self):
        self.logger.info("Disabling modbus polling for - %s" % self.device_name)
        self.poll_exit = True

    # Allow the polling loop to send messages to the modbus device
    def enable_polling(self):
        self.logger.info("Enabling modbus polling for - %s" % self.device_name)
        self.poll_exit = False

    # set an individual bit on a value
    def set_bit(self, value, bit):
        """ Sets a bit in the data 'value' at position index specified by 'bit' """
        return value | (1 << bit)

    # clear an individual bit on a value
    def clr_bit(self, value, bit):
        """ Clears a bit in the data 'value' at position index specified by 'bit' """
        return value & ~(1 << bit)

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
# riaps:keep_impl:end