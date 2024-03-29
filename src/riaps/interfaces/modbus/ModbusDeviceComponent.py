import yaml
from riaps.run.comp import Component

import riaps.interfaces.modbus.config as config
from riaps.interfaces.modbus.ModbusMasterThread import ModbusMaster
import riaps.interfaces.modbus.TerminalColors as tc


class ModbusDeviceComponent(Component):
    def __init__(self, path_to_device_list):
        super().__init__()

        self.device_config_paths, self.global_debug_mode = config.load_config_paths(path_to_device_list)
        self.device_threads = {}

    # riaps:keep_modbus_evt_port:begin
    def on_modbus_event_port(self):
        msg = self.modbus_event_port.recv_pyobj()
        self.logger.info(f"modbus_event_port received msg: {msg}")
        return msg
    # riaps:keep_modbus_evt_port:end

    # riaps:keep_modbus_cmd_port:begin
    def on_modbus_command_port(self):
        # Receive response from modbus device
        msg = self.modbus_command_port.recv_pyobj()
        self.logger.info(f"{tc.Red}"
                         f"ModbusDeviceComponent | on_modbus_command_port | receive modbus response msg: \n {msg}"
                         f"{tc.RESET}")
        return msg
    # riaps:keep_modbus_cmd_port:end

    # riaps:keep_impl:begin
    def handleActivate(self):
        self.logger.info("handleActivate")
        for device_name in self.device_config_paths:
            device_config_path = self.device_config_paths[device_name]
            device_thread = ModbusMaster(path_to_config_file=device_config_path,
                                         logger=self.logger,
                                         command_port=self.modbus_command_port,
                                         event_port=self.modbus_event_port
                                         )
            self.device_threads[device_name] = device_thread
            device_thread.start()
            # self.modbus_command_port.set_identity(device_thread.get_identity(self.modbus_command_port))
            # self.modbus_command_port.activate()
        self.logger.info("handleActivate complete")

    def send_modbus(self, msg):
        self.logger.info(f"{tc.Cyan}"
                         f"ModbusDeviceComponent | send_modbus | send riaps msg to modbus: {msg}"
                         f"{tc.RESET}")

        recipient = msg["to_device"]
        device_thread = self.device_threads[recipient]
        plug = device_thread.command_port_plug
        plug_identity = self.modbus_command_port.get_plug_identity(plug)
        self.modbus_command_port.set_identity(plug_identity)
        self.modbus_command_port.activate()
        self.modbus_command_port.send_pyobj(msg)

    def __destroy__(self):
        pass
        # stop all threads
    # riaps:keep_impl:end
