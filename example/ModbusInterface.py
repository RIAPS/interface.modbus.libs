# riaps:keep_import:begin
from riaps.run.comp import Component
import capnp
import yaml
import os
import datetime
import struct
import time
from datetime import datetime
from riaps.interfaces.modbus.ModbusSlaveThread import ModbusSlave
import riaps.interfaces.modbus.TerminalColors as tc
import spdlog

# riaps:keep_import:end

class ModbusInterface(Component):

# riaps:keep_constr:begin
    def __init__(self, config):
        super(ModbusInterface, self).__init__()
        self.ModbusConfigError = False
        self.modbus_device_cfgs = {}
        self.modbus_device_keys = []
        self.devices ={}
        try:
            if os.path.exists( config ) :
                # Load config file to interact with Modbus device
                with open(config, 'r') as cfglist:
                    configs = yaml.safe_load( cfglist )

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

        self.logger.info( f"ModbusInterface __init__ complete" )

# riaps:keep_constr:end

# riaps:keep_manager_qa:begin
    def on_manager_qa(self):
        msg = self.manager_qa.recv_pyobj()
        dthd =  self.devices[ msg.device ]
        plug_identity = self.modbus_cmd_port.get_plug_identity( dthd.get_plug() )
        self.modbus_cmd_port.set_identity( plug_identity )
        self.modbus_cmd_port.send_pyobj( msg )

# riaps:keep_manager_qa:end

# riaps:keep_modbus_evt_port:begin
    def on_modbus_evt_port(self):
        msg = self.modbus_evt_port.recv_pyobj()
        self.event_to_manager.send_pyobj( msg )
# riaps:keep_modbus_evt_port:end

# riaps:keep_modbus_cmd_port:begin
    def on_modbus_cmd_port(self):
        msg = self.modbus_cmd_port.recv_pyobj()
        self.manager_qa.send_pyobj( msg )
# riaps:keep_modbus_cmd_port:end

# riaps:keep_command_from_manager:begin
    def on_command_from_manager(self):
        pass
# riaps:keep_command_from_manager:end

# riaps:keep_impl:begin
    def handleActivate(self):
        try:
            # if defined then proceed normally
            self.modbus_evt_port
        except AttributeError :
            # if not defined then create the attribute and set it to none
            self.modbus_evt_port = None
            self.logger.warn(f"{tc.Red}ModbusInterface::handleActivate() RIAP::modbus_evt_port is not defined!{tc.RESET}")
   
        if not self.ModbusConfigError :
            for dvcname in self.modbus_device_keys:
                device_thread = ModbusSlave( self.logger, self.modbus_device_cfgs[dvcname], self.modbus_cmd_port, self.modbus_evt_port )
                dn = device_thread.get_device_name()    
                self.devices[dn] = device_thread 
                self.devices[dn].start()
                #if a polling thread was configured start it now
                if self.devices[dn].polling_thread != None :
                    self.devices[dn].polling_thread.start()
                while self.devices[dn].get_plug() == None :
                    time.sleep( 0.1 )
        msg = (self.modbus_device_keys,self.modbus_device_cfgs)
        self.device_configured.send_pyobj( msg )
        self.logger.info(f"handleActivate() complete")

    def __destroy__(self):
        for d in self.devices:
            thd = self.devices[d]
            self.logger.info(f"Deactivating thread {tc.Green}{thd.device_name}{tc.RESET}...")
            if thd.polling_thread != None :
                thd.polling_thread.deactivate()
            thd.deactivate()
            time.sleep( 0.1 )

        for d in self.devices:
            thd = self.devices[d]
            if thd.polling_thread != None :
                if thd.polling_thread.is_alive() :
                    thd.polling_thread.join( timeout=5.0 )
                    if thd.polling_thread.is_alive() :
                        self.logger.warn( f"{tc.Red}Failed to terminate polling thread!{tc.RESET}" )

            if thd.is_alive() :
                thd.join( timeout=5.0 )
                if thd.is_alive() :
                    self.logger.warn( f"{tc.Red}Failed to terminate thread!{tc.RESET}" )
            self.logger.info(f"Successfully terminated Modbus slave {tc.Green}{thd.device_name}{tc.RESET}...")

        self.logger.info(f"__destroy__() complete")

# riaps:keep_impl:end
