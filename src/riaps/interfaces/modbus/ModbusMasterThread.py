import logging
import threading

from riaps.interfaces.modbus.ModbusInterface import ModbusInterface

class ModbusMaster(threading.Thread):
    def __init__(self, path_to_config_file, logger=None):
        super().__init__()
        self.logger = logger if logger else logging.getLogger(__name__)
        self.stop_polling = threading.Event

        self.modbus_interface = ModbusInterface(path_to_file=path_to_config_file)

    def run(self) -> None:
        while not self.stop_polling.wait(timeout=1)



