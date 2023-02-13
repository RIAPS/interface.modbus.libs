import datetime as dt
import logging
from modbus_tk import modbus_rtu
from modbus_tk import modbus_tcp
from modbus_tk import exceptions as modbus_exceptions
import modbus_tk.defines as cst
import serial
import sys
import yaml

from riaps.interfaces.modbus.ModbusSystemSettings import ModbusSystem
import riaps.interfaces.modbus.TerminalColors as tc

# get the value of an individual bit in a value
from typing import List


def get_bit(value, bit_position):
    """ Gets a bit in the data 'value' at position index specified by 'bit'
    https://realpython.com/python-bitwise-operators/#getting-a-bit"""
    return (value >> bit_position) & 1  # If the bit value at the position is 1 this returns 1.


def set_bit(value, bit_position, bit_value):
    mask = 1 << bit_position
    value &= ~mask
    if bit_value:
        value |= mask
    return value


class ModbusInterface:
    def __init__(self, path_to_file, logger=None, debug_mode=False):

        local_logger = logging.getLogger(__name__)
        if local_logger.handlers:
            self.logger = local_logger
        elif logger:
            self.logger = logger
        else:
            self.logger = local_logger

        self.device_config = self.load_config_file(path_to_file)
        self.config_validation_receipt = self.validate_configuration()
        self.device_name = self.device_config["Name"]
        self.master = self.setup_master(self.device_config)
        self.debug_mode = debug_mode if debug_mode else self.device_config.get("debugMode", False)

    def load_config_file(self, path_to_file):
        with open(path_to_file, 'r') as file:  # Intentionally do not handle exception
            device_config = yaml.safe_load(file)
        return device_config

    def validate_configuration(self):
        required_parameters = ["Name", "Protocol", self.device_config.get("Protocol", "MISSING"), "SlaveID"]
        for parameter in required_parameters:
            if parameter not in self.device_config:
                return {"return_code": 1, "msg": f"Configuration missing for {parameter}"}
        return {"return_code": 0, "msg": "Valid device configuration"}

    def setup_master(self, device_config):
        protocol = device_config["Protocol"]
        comm_config = device_config[protocol]
        if protocol == "TCP":
            master = self.setup_tcp_master(comm_config)
        elif protocol in ["Serial", "RS232"]:
            master = self.setup_rtu_master(comm_config)
        else:
            self.logger.error(f"{protocol} protocol not implemented")
            return None
        master.set_verbose(ModbusSystem.Debugging.Verbose)
        return master

    def setup_tcp_master(self, comm_config):
        addr = comm_config['Address']
        port = comm_config['Port']
        master = modbus_tcp.TcpMaster(addr, port)
        master.set_timeout((ModbusSystem.Timeouts.TCPComm / 1000.0))
        return master

    def setup_rtu_master(self, comm_config):
        serial_connection = serial.Serial(port=comm_config["device"],
                                          baudrate=comm_config['baudrate'],
                                          bytesize=comm_config['bytesize'],
                                          parity=comm_config['parity'],
                                          stopbits=comm_config['stopbits'],
                                          xonxoff=comm_config['xonxoff'])
        master = modbus_rtu.RtuMaster(serial_connection)
        master.set_timeout((ModbusSystem.Timeouts.TTYSComm / 1000.0), use_sw_timeout=True)
        return master

    def execute_modbus_command(self, command_name: str, value_to_write=0):
        command_config = self.device_config[command_name]
        function_code = command_config['function']
        starting_address = command_config['start']
        length = command_config['length']
        data_fmt = command_config.get("data_format", '')

        if self.debug_mode:
            msg = f"{command_name}: value_to_write: {value_to_write}" if value_to_write else f"{command_name}"
            self.logger.info(msg)

        try:
            result: tuple = self.master.execute(self.device_config["SlaveID"],
                                                getattr(cst, function_code),
                                                starting_address,
                                                quantity_of_x=length,
                                                output_value=value_to_write,
                                                data_format=data_fmt)
        except ConnectionRefusedError as ex:
            self.logger.error(f"error={ex})")
            return
        else:
            if self.debug_mode:
                self.logger.info(
                    f"device_name: {self.device_name}, "
                    f"Response: starting_address={starting_address}, "
                    f"response={result}, "
                    f"timestamp={dt.datetime.now()}")
            return list(result)

    def scale_response(self, response, command_name: str, force_full_register_read=False):

        command_config = self.device_config[command_name]
        bit_position = command_config.get("bit_position")
        scale_factor = self.device_config[command_name].get("scale_factor")
        units = self.device_config[command_name].get("units")
        values = []
        for value in response:
            if scale_factor:
                values.append(value * scale_factor)
            elif force_full_register_read:
                values.append(value)
            elif bit_position:
                bit_value = get_bit(value, bit_position=bit_position)
                values.append(bit_value)

        results = {"device_name": self.device_name, "command": command_name, "values": values, "units": units}
        return results

    def read_modbus(self, parameter: str, force_full_register_read=False):

        command_name = f"{parameter}_READ"
        response: list = self.execute_modbus_command(command_name)
        if not response:
            return None
        result = self.scale_response(response, command_name, force_full_register_read)

        if self.debug_mode:
            self.logger.info(f"Modbus result: {result}")

        return result

    def write_modbus(self, parameter: str, values: list):
        # Get Current registry values:
        current_registry_value = self.read_modbus(parameter, force_full_register_read=True)["values"]
        self.logger.debug(f"Read current_registry_value before write: {current_registry_value}")

        command_name = f"{parameter}_WRITE"
        command_config = self.device_config[command_name]

        starting_address = self.device_config[command_name].get("start")
        register_length = self.device_config[command_name].get("length")
        data_format = self.device_config[command_name].get("data_format", "")
        scale_factor = self.device_config[command_name].get("scale_factor")
        units = self.device_config[command_name].get("units", "")

        bit_position = command_config.get("bit_position")

        values_to_write = []
        if bit_position:
            bit_value = values[0]
            value = set_bit(current_registry_value[0], bit_position, bit_value)
            self.logger.debug(f"value after setting bit: {value}")
            values_to_write.append(value)
        elif scale_factor:
            for value in values:
                scaled_value = value / scale_factor
                # Why did Gerry cast this as an int?
                # Because the division causes it to be a float, and it may need to be
                # an int to be compatible with the modbus_tk library.
                # TODO: There are likely some cases that this implementation does not cover.
                #  for example, if data_format is defined as >H. This was not handled in the
                #  prior implementation either.
                if data_format == "":
                    # if data_format is not specified the modbus_tk library will
                    # set it to either shorts (e.g,.  data_format = ">" + (quantity_of_x * "H"))
                    # or unsigned characters, so we make sure
                    # the input is an int before sending it.
                    scaled_value = int(scaled_value)
                values_to_write.append(scaled_value)
        else:
            values_to_write = values

        response: list = self.execute_modbus_command(command_name, value_to_write=values_to_write)
        self.logger.info(f"Response to writing value: {response}")

        # In response to a successful WRITE command the modbus returns
        # 1: The starting address of the parameters
        # 2: The number of registers written.
        if len(response) != 2:
            self.logger.info(f"{tc.Red}If this happens update code."
                             f"Response wrong length: {response}"
                             f"{tc.RESET}")
            results = {"command": command_name, "values": [], "units": units}
            return results
        if response[0] != starting_address or response[1] != register_length:
            self.logger.info(f"{tc.Red}If this happens update code."
                             f"Parameter mismatch: {response}"
                             f"{tc.RESET}")
            results = {"command": command_name, "values": [], "units": units}
            return results

        # Since a WRITE command does not return the written value, we insert the written value
        # manually into the response, and as a result we do not need to scale it.
        # result = self.scale_response([response[1]], command_name, force_full_register_read=True)
        # result = self.scale_response(values, command_name, force_full_register_read=True)
        result = {"device_name": self.device_name, "command": command_name, "values": values, "units": units}

        if self.debug_mode:
            self.logger.info(f"Modbus result: {result}")
        return result
