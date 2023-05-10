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

project_path = "/home/riaps/projects/RIAPS/interface.modbus.libs/example/simulator/reader/cfg"
devices = ["DSP115-Banshee", "DSP116-Banshee"]
modbus_interfaces = []
for device in devices:
    path_to_config_file = f"{project_path}/{device}.yaml"
    modbus_interface = ModbusInterface(path_to_file=path_to_config_file, logger=logger)
    modbus_interfaces.append(modbus_interface)

for modbus_interface in modbus_interfaces:
    for parameter in ["FREQ", "VA_RMS"]:
        result = modbus_interface.read_modbus(parameter=parameter)
        print(result)
