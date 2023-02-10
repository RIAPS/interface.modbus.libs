from riaps.interfaces.modbus.ModbusDeviceComponent import ModbusDeviceComponent


class ModbusDevice(ModbusDeviceComponent):
    def __init__(self, path_to_device_list):
        super().__init__(path_to_device_list)

    def on_poller(self):
        now = self.poller.recv_pyobj()
        self.logger.info(f"on_poller: {now}")

        msg = {"device_name": "Test_NEC-BESS1"}
        self.send_modbus(msg)

    def send_modbus(self, msg):
        self.logger.info(f"send_modbus: {msg}")

        recipient = msg["device_name"]

        device_thread = self.device_threads[recipient]

        plug = device_thread.command_port
        plug_identity = self.modbus_command_port.get_plug_identity(plug)

        self.modbus_command_port.set_identity(plug_identity)
        self.modbus_command_port.activate()

        self.modbus_command_port.activate()

        self.modbus_command_port.send_pyobj(msg)
