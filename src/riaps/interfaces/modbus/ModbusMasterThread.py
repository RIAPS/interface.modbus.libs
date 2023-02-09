import logging
import threading
import zmq

from riaps.interfaces.modbus.ModbusInterface import ModbusInterface


class ModbusMaster(threading.Thread):
    def __init__(self, path_to_config_file, logger=None):
        super().__init__()
        self.logger = logger if logger else logging.getLogger(__name__)
        # TODO: Maybe use getLogger first and check for handlers, then check for
        #  passed loggers, then use getLogger.
        self.stop_polling = threading.Event()
        self.poller = zmq.Poller()

        self.modbus_interface = ModbusInterface(path_to_file=path_to_config_file, logger=self.logger)
        self.device_config = self.modbus_interface.device_config

    def run(self) -> None:
        poll_interval = self.device_config.get("Interval")
        parameters_to_poll = self.device_config.get("poll")

        if not parameters_to_poll:
            self.logger.warning("No parameters configured to poll")
            return

        self.logger.debug(f"parameters_to_poll: {parameters_to_poll}")
        while not self.stop_polling.wait(timeout=10):
            for parameter in parameters_to_poll:
                self.logger.debug(f"poll parameter: {parameter}")
                self.modbus_interface.read_modbus(parameter=parameter)




