from riaps.interfaces.modbus.ModbusDeviceComponent import ModbusDeviceComponent


class ModbusDevice(ModbusDeviceComponent):
    def __init__(self, path_to_device_list):
        super().__init__(path_to_device_list)

    def on_poller(self):
        now = self.poller.recv_pyobj()
        self.logger.info(f"on_poller: {now}")

        msg = {"to_device": "Test_NEC-BESS1",
               "parameter": "GeneratorStatus",
               "operation": "read",
               "values": [3.14]}
        self.send_modbus(msg)


