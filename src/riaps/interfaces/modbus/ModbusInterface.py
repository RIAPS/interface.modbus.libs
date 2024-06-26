import datetime as dt
import logging
import socket

from modbus_tk import modbus_rtu
from modbus_tk import modbus_tcp
from modbus_tk import exceptions as modbus_exceptions
import modbus_tk.defines as cst
import serial
import sys
import yaml

from riaps.interfaces.modbus.ModbusSystemSettings import ModbusSystem
from riaps.interfaces.modbus.config import load_config_file, validate_configuration
import riaps.interfaces.modbus.TerminalColors as tc


# get the value of an individual bit in a value from typing import List
def get_bit(value, bit_position):
    """Gets a bit in the data 'value' at position index specified by 'bit'
    https://realpython.com/python-bitwise-operators/#getting-a-bit"""
    return (
        value >> bit_position
    ) & 1  # If the bit value at the position is 1 this returns 1.


def set_bit(value, bit_position, bit_value):
    mask = 1 << bit_position
    value &= ~mask
    if bit_value:
        value |= mask
    return value


class ModbusInterface:
    def __init__(self, path_to_file, logger=None, debug_mode=False):

        local_logger = logging.getLogger(__name__)
        if logger:
            self.logger = logger
        else:
            self.logger = local_logger

        self.device_config = load_config_file(path_to_file)
        self.config_validation_receipt = validate_configuration(self.device_config)
        self.device_name = self.device_config["Name"]
        self.master = self.setup_master(self.device_config)
        self.debug_mode = (
            debug_mode if debug_mode else self.device_config.get("debugMode", False)
        )

    def setup_master(self, device_config):
        protocol = device_config["Protocol"]
        comm_config = device_config[protocol]
        if protocol == "TCP":
            master = self.setup_tcp_master(comm_config)
        elif protocol in ["Serial", "RS232"]:
            master = self.setup_rtu_master(comm_config)
        else:
            self.logger.error(
                f"ModbusInterface | setup_master | {protocol} protocol not implemented"
            )
            return None
        master.set_verbose(ModbusSystem.Debugging.Verbose)
        return master

    def setup_tcp_master(self, comm_config):
        addr = comm_config["Address"]
        port = comm_config["Port"]
        master = modbus_tcp.TcpMaster(addr, port)
        master.set_timeout((ModbusSystem.Timeouts.TCPComm / 1000.0))
        return master

    def setup_rtu_master(self, comm_config):
        serial_connection = serial.Serial(
            port=comm_config["device"],
            baudrate=comm_config["baudrate"],
            bytesize=comm_config["bytesize"],
            parity=comm_config["parity"],
            stopbits=comm_config["stopbits"],
            xonxoff=comm_config["xonxoff"],
        )
        master = modbus_rtu.RtuMaster(serial_connection)
        master.set_timeout(
            (ModbusSystem.Timeouts.TTYSComm / 1000.0), use_sw_timeout=True
        )
        return master

    def execute_modbus_command(self, command_name: str, value_to_write=0):
        command_config = self.device_config[command_name]
        function_code = command_config["function"]
        starting_address = command_config["start"]
        length = command_config["length"]
        data_fmt = command_config.get("data_format", "")

        try:
            response: tuple = self.master.execute(
                self.device_config["SlaveID"],
                getattr(cst, function_code),
                starting_address,
                quantity_of_x=length,
                output_value=value_to_write,
                data_format=data_fmt,
            )
            result = {"command": command_name, "response": list(response)}
        except ConnectionRefusedError as ex:
            result = {
                "command": command_name,
                "errors": ex,
            }
            self.logger.error(f"ModbusInterface | execute_modbus_command | error={ex})")
            return result

        except Exception as ex:
            result = {
                "command": command_name,
                "errors": ex,
            }
            self.logger.error(f"ModbusInterface | execute_modbus_command | error={ex})")
            return result
        # TODO: catching socket.timeout doesn't work.
        # except socket.timeout as e_info:
        #     self.logger.error(f"error={e_info})")
        #     return True
        else:
            if self.debug_mode:
                # Uncomment strings below if desired.
                strings = [
                    f"ModbusInterface | execute_modbus_command",
                    # f"device_name: {self.device_name}",
                    f"parameter: {command_name}",
                    # f"starting_address: {starting_address}",
                    f"response: {result}",
                    # f"timestamp: {dt.datetime.now()}"
                ]
                for string in strings:
                    try:
                        self.logger.debug(f"{tc.White}" f"{string}" f"{tc.RESET}")
                    except TypeError as ex:
                        self.logger.warn(
                            f"{tc.Red}"
                            f"ModbusInterface | execute_modbus_command |"
                            f"Spdlog had trouble: {ex}"
                            f"{tc.RESET}"
                        )
            return result

    def scale_response(
        self, response, command_name: str, force_full_register_read=False
    ):

        command_config = self.device_config[command_name]
        bit_position = command_config.get("bit_position")
        scale_factor = self.device_config[command_name].get("scale_factor")
        units = self.device_config[command_name].get("units")
        values = []
        errors = []  # TODO: add errors as they come up

        for value in response:
            if scale_factor:
                values.append(value * scale_factor)
            elif force_full_register_read:
                values.append(value)
            elif bit_position is not None:
                bit_value = get_bit(value, bit_position=bit_position)
                values.append(bit_value)
                self.logger.info(
                    f"{tc.Red}"
                    f"{command_name}\n"
                    f"response: {response}\n"
                    f"scale_factor: {scale_factor}\n"
                    f"force_full_register_read: {force_full_register_read}\n"
                    f"bit_position: {bit_position}\n"
                    f"bit_value: {bit_value}"
                    f"{tc.RESET}"
                )
            else:
                values.append(value)

        results = {
            "device_name": self.device_name,
            "command": command_name,
            "values": values,
            "units": units,
        }

        # If there are errors, add them to the result.
        # The ModbusMasterThread will check if there are errors, and if there are not then it will send a return
        # status of OK
        if errors:
            results["errors"] = errors

        return results

    def read_modbus(self, parameter: str, force_full_register_read=False):

        command_name = f"{parameter}_READ"
        result: list = self.execute_modbus_command(command_name)
        if result.get("errors"):
            return result
        result = self.scale_response(
            result["response"], command_name, force_full_register_read
        )

        if self.debug_mode:
            self.logger.info(f"ModbusInterface | read_modbus | Modbus result: {result}")

        return result

    def write_modbus(self, parameter: str, values: list):

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
            # Get Current registry values:
            current_registry_value = self.read_modbus(
                parameter, force_full_register_read=True
            )["values"]
            self.logger.debug(
                f"ModbusInterface | write_modbus | Read current_registry_value before write: {current_registry_value}"
            )

            bit_value = values[0]
            value = set_bit(current_registry_value[0], bit_position, bit_value)
            self.logger.debug(
                f"ModbusInterface | write_modbus | value after setting bit: {value}"
            )
            values_to_write.append(value)
        elif scale_factor:
            for value in values:
                scaled_value = value / scale_factor
                # TODO: There are likely some cases that this implementation does not cover.
                #  for example, if data_format is defined as >H. This was not handled in the
                #  prior implementation either.
                if data_format == "" or data_format in [">H", ">h", ">I", ">i"]:
                    # Why cast this as an int?
                    # Because the division above causes it to be a float
                    # and if data_format is not specified the modbus_tk library will
                    # set it to either shorts (e.g,.  data_format = ">" + (quantity_of_x * "H"))
                    # or unsigned characters, so we make sure
                    # the input is an int before sending it.
                    scaled_value = int(scaled_value)
                values_to_write.append(scaled_value)
        else:
            values_to_write = values

        result: list = self.execute_modbus_command(
            command_name, value_to_write=values_to_write
        )
        #  https://ozeki.hu/p_5883-mobdbus-function-code-16-write-multiple-holding-registers.html

        # In response to a successful WRITE command the modbus returns
        # 1: The starting address of the parameters
        # 2: The number of registers written.
        if result.get("errors"):
            self.logger.error(
                f"{tc.Red}"
                f"ModbusInterface | write_modbus | "
                f"{result['errors']}"
                f"{tc.RESET}"
            )
            return result

        response = result["response"]
        self.logger.info(
            f"ModbusInterface | write_modbus | Response to writing value: {response}"
        )
        if len(response) != 2:
            self.logger.warn(
                f"{tc.Red}"
                f"ModbusInterface | write_modbus | "
                f"If this happens update code."
                f"Response wrong length: {response}"
                f"{tc.RESET}"
            )
            error = f"Response wrong length"
            result = {
                "command": command_name,
                "values": [],
                "units": units,
                "errors": error,
            }
            return result
        if response[0] != starting_address or response[1] != register_length:
            self.logger.warn(
                f"{tc.Red}"
                f"ModbusInterface | write_modbus | "
                f"If this happens update code."
                f"Parameter mismatch: {response}"
                f"{tc.RESET}"
            )
            error = f"Modbus Parameter mismatch"
            result = {
                "command": command_name,
                "values": [],
                "units": units,
                "errors": error,
            }
            return result

        # Since a WRITE command does not return the written value, we insert the written value
        # manually into the response, and as a result we do not need to scale it.
        # result = self.scale_response([response[1]], command_name, force_full_register_read=True)
        # result = self.scale_response(values, command_name, force_full_register_read=True)
        result = {
            "device_name": self.device_name,
            "command": command_name,
            "values": values,
            "units": units,
        }

        if self.debug_mode:
            self.logger.info(f"Modbus result: {result}")
        return result
