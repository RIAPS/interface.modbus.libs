# riaps:keep_import:begin
import time
from riaps.run.comp import Component
import yaml
from modbus_tk import modbus_tcp
from modbus_tk import modbus_rtu
import modbus_tk.defines as cst
import spdlog
import capnp
import os
import datetime
import modbuslibs.device_capnp as msg_struct
import modbuslibs.helper as helper
from modbuslibs.ModbusSystemSettings import ModbusSystem
from modbuslibs.ModbusSlaveThread import ModbusSlave


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
        self.global_debug_mode = 0

        try:
            if os.path.exists(config):
                # Load config file to interact with Modbus device
                with open(config, 'r') as cfglist:
                    configs = yaml.safe_load(cfglist)

                if "GobalDebugMode" in list(configs.keys()):
                    self.global_debug_mode = configs["GobalDebugMode"]
                    self.logger.info(
                        f"Debug setting for all devices are overridden: GlobalDebugMode={self.global_debug_mode}")

                for c in configs["configs"]:
                    cfgdev = None
                    if os.path.exists(c):
                        with open(c, 'r') as dvc:
                            cfgdev = yaml.safe_load(dvc)

                        if cfgdev != None:
                            devname = list(cfgdev.keys())
                            self.modbus_device_cfgs[devname[0]] = cfgdev
                    else:
                        self.ModbusConfigError = True
                        self.logger.info(f"Device config:{c} does not exist!")

                # Get the names of all the devices
                self.modbus_device_keys = list(self.modbus_device_cfgs.keys())

            else:
                self.ModbusConfigError = True
                self.logger.info('System configuration file does not exist [{0}].'.format(config))

        except OSError:
            self.ModbusConfigError = True
            self.logger.info('File I/O error [{0}].'.format(config))

        if self.ModbusConfigError:
            self.logger.info(f"{len(self.modbus_device_keys)} Modbus device configuration error!")
        else:
            self.logger.info(f"{len(self.modbus_device_keys)} Modbus devices found in configuration:")
            for k in self.modbus_device_keys:
                self.logger.info(f"{k}")

    # riaps:keep_constr:end

    # riaps:keep_modbus_evt_port:begin
    def on_modbus_evt_port(self):
        msg = self.modbus_evt_port.recv_pyobj()
        evtmsg = msg_struct.DeviceEvent.new_message()
        evtmsg.event = msg.event
        evtmsg.command = msg.command
        evtmsg.names = list(msg.names)
        evtmsg.values = list(msg.values)
        evtmsg.units = list(msg.units)
        evtmsg.device = msg.device
        evtmsg.error = msg.error
        evtmsg.et = msg.et
        self.postEvent(evtmsg)
        if self.global_debug_mode == 1:
            self.logger.info(
                f"ModbusDevice::on_modbus_evt_port( {evtmsg.device}:{evtmsg.event}:{evtmsg.names}:{evtmsg.values} )")

    # riaps:keep_modbus_evt_port:end

    # riaps:keep_modbus_cmd_port:begin
    def on_modbus_cmd_port(self):
        msg = self.modbus_cmd_port.recv_pyobj()
        ansmsg = msg_struct.DeviceAns.new_message()
        ansmsg.error = msg.error
        ansmsg.device = msg.device
        ansmsg.operation = msg.operation
        ansmsg.params = list(msg.params)
        ansmsg.values = list(msg.values)
        ansmsg.units = list(msg.units)
        ansmsg.msgcounter = msg.msgcounter
        msgbytes = ansmsg.to_bytes()
        self.device_port.send(msgbytes)
        if self.global_debug_mode == 1:
            self.logger.info(
                f"ModbusDevice::on_modbus_cmd_port( {ansmsg.device}:ANSWER:{ansmsg.params}:{ansmsg.values}:{ansmsg.msgcounter} )")

    # riaps:keep_modbus_cmd_port:end

    # riaps:keep_device_port:begin
    def on_device_port(self):
        # receive
        start = datetime.datetime.now()  # measure how long it takes to complete query
        msg_bytes = self.device_port.recv()  # required to remove message from queue
        msg = msg_struct.DeviceQry.from_bytes(msg_bytes)

        dvcname = msg.device
        if dvcname == "":
            dvcname = self.modbus_device_keys[0]
        # if the device name is empty then use the first device in the list of keys
        try:
            self.modbus_cmd_port
            dthd = self.devices[dvcname]
            plug_identity = self.modbus_cmd_port.get_plug_identity(dthd.get_plug())
            self.modbus_cmd_port.set_identity(plug_identity)
            self.modbus_cmd_port.send_pyobj(msg)
        except AttributeError:
            self.logger.info(f"ModbusDevice::on_device_port() modbus_cmd_port is not defined!")

    # riaps:keep_device_port:end

    # riaps:keep_poller:begin
    def on_poller(self):
        now = self.poller.recv_pyobj()

    # riaps:keep_poller:end

    # riaps:keep_impl:begin
    def handleActivate(self):
        if not self.ModbusConfigError:
            # check if the modbus event port is defined 
            try:
                # if defined then proceed normally
                self.modbus_evt_port
            except AttributeError:
                # if not defined then create the attribute and set it to none
                self.modbus_evt_port = None
                self.logger.warn(f"ModbusDevice::handleActivate() RIAP::modbus_evt_port is not defined!")

            # create the device threads and poller threads if needed
            try:
                self.modbus_cmd_port
                for dvcname in self.modbus_device_keys:
                    device_thread = ModbusSlave(self.logger, self.modbus_device_cfgs[dvcname], self.modbus_cmd_port,
                                                self.modbus_evt_port)
                    # override the local debug setting if the top level configuration requests it
                    if self.global_debug_mode <= 1:
                        device_thread.enable_debug_mode(enable=False)
                    elif self.global_debug_mode >= 2:
                        device_thread.enable_debug_mode(enable=True)

                    dn = device_thread.get_device_name()
                    self.devices[dn] = device_thread
                    self.devices[dn].start()
                    # if a polling thread was configured start it now
                    if self.devices[dn].polling_thread != None:
                        self.devices[dn].polling_thread.start()

                    while self.devices[dn].get_plug() == None:
                        time.sleep(0.1)
            except AttributeError:
                self.logger.warn(
                    f"ModbusDevice::handleActivate() Cannot create threads, RIAPS::modbus_cmd_port is not defined!")

        # post a startup event showing the device is active 
        evt = msg_struct.DeviceEvent.new_message()
        evt.event = "ACTIVE"
        evt.command = "STARTUP"
        evt.values = [0.0]
        evt.names = [""]
        evt.units = [""]
        evt.device = f"{self.modbus_device_keys}"
        evt.error = 0
        evt.et = 0.0
        self.postEvent(evt)
        self.logger.info(f"ModbusDevice::handleActivate() complete")

    # Should be called before __destroy__ when app is shutting down.
    # this does not appear to work correctly
    def handleDeactivate(self):
        self.logger.info("Deactivating Modbus Device")
        self.logger.info(f"self.master is {self.master}")

    # Format and error event message that will get passed to an upper level
    # RIAPS component
    def error(self, evt, error, vals, errnum=-1, et=None):
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
        for d in self.devices:
            thd = self.devices[d]
            self.logger.info(f"Deactivating thread {thd.device_name}...")
            if thd.polling_thread != None:
                thd.polling_thread.deactivate()
            thd.deactivate()
            time.sleep(0.1)

        for d in self.devices:
            thd = self.devices[d]
            if thd.polling_thread != None:
                if thd.polling_thread.is_alive():
                    thd.polling_thread.join(timeout=5.0)
                    if thd.polling_thread.is_alive():
                        self.logger.warn(f"Failed to terminate polling thread!")

            if thd.is_alive():
                thd.join(timeout=5.0)
                if thd.is_alive():
                    self.logger.warn(f"Failed to terminate thread!")

        self.logger.info(f"ModbusDevice::__destroy__() complete")

    # post an event if the required attributes exist and the event is valid
    def postEvent(self, evt):
        try:
            if evt != None:
                self.event_port.send(evt.to_bytes())
                if self.global_debug_mode == 1:
                    self.logger.info(f"ModbusDevice::postEvent( {evt.device}, {evt.event}, {evt.names}, {evt.values} )")
            else:
                self.logger.warn(f"Invalid event: {evt}!")
        except AttributeError:
            self.logger.warn(f"Modbus attribute [self.event_port] is not defined! Cannot process event{evt}! ")

            # riaps:keep_impl:end
