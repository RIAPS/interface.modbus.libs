import logging
import threading
import zmq

from riaps.interfaces.modbus.ModbusInterface import ModbusInterface


class ModbusMaster(threading.Thread):
    def __init__(self, path_to_config_file, logger=None, command_port=None, event_port=None):
        super().__init__()

        local_logger = logging.getLogger(__name__)
        if local_logger.handlers:
            self.logger = local_logger
        elif logger:
            self.logger = logger
        else:
            self.logger = local_logger

        self.stop_polling = threading.Event()
        self.poller = zmq.Poller()
        if command_port:
            self.command_port = command_port.setupPlug(self)
            self.poller.register(self.command_port, zmq.POLLIN)
        if event_port:
            self.event_port = event_port.setupPlug(self)
            self.poller.register(self.event_port, zmq.POLLIN)

        self.modbus_interface = ModbusInterface(path_to_file=path_to_config_file, logger=self.logger)
        self.device_config = self.modbus_interface.device_config

    def run(self) -> None:
        poll_interval = self.device_config.get("Poll_Interval_Seconds")
        parameters_to_poll = self.device_config.get("poll")

        if not parameters_to_poll:
            self.logger.warning("No parameters configured to poll")
            return

        self.logger.debug(f"parameters_to_poll: {parameters_to_poll}")
        while not self.stop_polling.wait(timeout=poll_interval):
            for parameter in parameters_to_poll:
                self.logger.debug(f"poll parameter: {parameter}")
                self.modbus_interface.read_modbus(parameter=parameter)




