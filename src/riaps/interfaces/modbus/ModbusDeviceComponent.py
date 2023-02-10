import yaml
from riaps.run.comp import Component

import riaps.interfaces.modbus.config as config
from riaps.interfaces.modbus.ModbusMasterThread import ModbusMaster


class ModbusDeviceComponent(Component):
    def __init__(self, path_to_device_list):
        super().__init__()

        self.device_configs, global_debug_mode = config.load_config_files(path_to_device_list)
        self.device_threads = {}

    # riaps:keep_modbus_evt_port:begin
    def on_modbus_evt_port(self):
        msg = self.modbus_evt_port.recv_pyobj()

    # riaps:keep_modbus_evt_port:end

    # riaps:keep_modbus_cmd_port:begin
    def on_modbus_cmd_port(self):
        msg = self.modbus_cmd_port.recv_pyobj()
    # riaps:keep_modbus_cmd_port:end

    # riaps:keep_impl:begin
    def handleActivate(self):
        for device_name in self.device_configs:
            device_thread = ModbusMaster(device_name)
            self.device_threads[device_name] = device_thread
            device_thread.run()

        # start a thread for each device and pass the cmd and event ports.

    def __destroy__(self):
        pass
        # stop all threads
    # riaps:keep_impl:end
