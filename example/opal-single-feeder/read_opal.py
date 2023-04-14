import logging
import time

from riaps.interfaces.modbus.ModbusInterface import ModbusInterface

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

path_to_config_file = "/home/riaps/projects/RIAPS/interface.modbus.libs/example/opal-single-feeder/cfg/GEN2-Banshee.yaml"
modbus_interface = ModbusInterface(path_to_file=path_to_config_file, logger=logger)

result = modbus_interface.read_modbus(parameter="FREQ")
# result = modbus_interface.read_modbus(parameter="P")
# result = modbus_interface.write_modbus(parameter="CONTROL", values=[1])
# print(result)
# time.sleep(2)
# result = modbus_interface.read_modbus(parameter="P")
# print(result)
# time.sleep(2)
# result = modbus_interface.write_modbus(parameter="REAL_POWER", values=[300])
# print(result)
# time.sleep(2)
# result = modbus_interface.read_modbus(parameter="P")
print(result)
