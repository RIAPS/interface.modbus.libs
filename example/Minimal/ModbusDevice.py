from riaps.interfaces.modbus.ModbusDeviceComponent import ModbusDeviceComponent


class ModbusDevice(ModbusDeviceComponent):
    def __init__(self, path_to_device_list):
        super().__init__(path_to_device_list)

        self.counter = 0
        self.values_to_write = [0, 1, 4, 5]

    def on_poller(self):
        now = self.poller.recv_pyobj()
        self.logger.info(f"on_poller: {now}")
        msg = None

        if 0 <= self.counter < len(self.values_to_write):
            msg = {"to_device": "Test_NEC-BESS1",
                   "parameters": ["GeneratorStatus"],
                   "operation": "WRITE",
                   "values": [self.values_to_write[self.counter]]}
        if msg:
            self.counter += 1
            self.send_modbus(msg)


