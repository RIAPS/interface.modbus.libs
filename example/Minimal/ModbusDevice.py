from riaps.interfaces.modbus.ModbusDeviceComponent import ModbusDeviceComponent


class ModbusDevice(ModbusDeviceComponent):
    def __init__(self):
        super().__init__()

    def on_poller(self):
        now = self.periodic.recv_pyobj()
