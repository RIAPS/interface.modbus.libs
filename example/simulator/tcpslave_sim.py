import argparse
import struct

import modbus_tk
from modbus_tk import modbus_tcp
import yaml

import riaps.interfaces.modbus.TerminalColors as tc

required_parameters = {
    "modbus_block": ["block_type", "starting_address", "num_registers"],
    "device": [
        "register_name",
        "block_name",
        "starting_address",
        "initial_values",
        "num_registers",
    ],
}
verbose = True


def load_config(config_path, config_type):
    with open(config_path) as f:
        config = yaml.safe_load(f)
    register_config = config["REGISTERS"]
    for item in register_config:
        for parameter in required_parameters[config_type]:
            if register_config[item].get(parameter) is None:
                print(
                    f"Parameter {parameter} not defined in {item}:{register_config[item]}"
                )
                return
    return config


def main(port, address, modbus_config_file_path, device_config_file_path):
    """
    :param port:
    :param address:
    :param modbus_config_file_path:
    :param device_config_file_path:
    :return:
    """
    Cyan = "\033[96m"
    Yellow = "\033[93m"
    modbus_block_config = load_config(modbus_config_file_path, "modbus_block")[
        "REGISTERS"
    ]
    if not modbus_block_config:
        return

    device_conifg = load_config(device_config_file_path, "device")
    if not device_conifg:
        return

    server = modbus_tcp.TcpServer(port, address)
    slave1 = server.add_slave(
        slave_id=device_conifg["SlaveID"]
    )  # TODO: add new config file for this

    for block_type_name in modbus_block_config:
        block_type_config = modbus_block_config[block_type_name]
        if verbose:
            print(
                f"Adding memory for {block_type_name} block. \n"
                f"block_type: {getattr(modbus_tk.defines, block_type_name)} "
                f'registers: {block_type_config["num_registers"]}'
            )

        slave1.add_block(
            block_name=block_type_name,
            block_type=block_type_config["block_type"],
            starting_address=block_type_config["starting_address"],
            size=block_type_config["num_registers"],
        )

    if verbose:
        print(
            f'{Yellow}{"Initialization info":<56}'
            f': {"Variable Name":<30}'
            f'{"Address":<14}'
            f'{"Order":<8}'
            f'{"Value":<10}'
            f'{"Raw data":<10}'
            f"{tc.RESET}"
        )

    device_register_config = device_conifg["REGISTERS"]
    for parameter_name in device_register_config:
        parameter = device_register_config[parameter_name]
        byte_order = parameter.get("byte_order")
        struct_byte_order = ">" if byte_order == "BE" else "<"
        initial_values = list(
            map(
                lambda x: x * parameter.get("scale_factor", 1),
                parameter.get("initial_values"),
            )
        )
        print(initial_values)
        format = f'{struct_byte_order}{parameter.get("data_type")*len(initial_values)}'
        intermediate_bytes = struct.pack(format, *initial_values)
        register_values = list(
            struct.unpack(
                f'{struct_byte_order}{"H"*parameter.get("num_registers")}',
                intermediate_bytes,
            )
        )

        slave1.set_values(
            block_name=parameter.get("block_name"),
            address=parameter.get("starting_address"),
            values=register_values,
        )

        if verbose:
            print(
                f'Initializing {f"{format}{len(intermediate_bytes)*8}":<8}'
                f'( Memory Block={parameter.get("block_name")} ) : '
                f'{Cyan}{parameter.get("register_name"):30}{tc.RESET}'
                f'({parameter.get("starting_address"):0>5}) '
                f"{byte_order:>10} "
                f"{tc.Yellow}{str(initial_values):12}{tc.RESET} "  # str cast is used so that string offset will work.
                f"{intermediate_bytes.hex()}"
            )

    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-a",
        "--address",
        required=False,
        help="IP Address. Default:127.0.0.1",
        default="127.0.0.1",
    )
    parser.add_argument(
        "-p",
        "--port",
        required=False,
        help="Modbus TCP Port (1-65535). Default:501",
        default=501,
        type=int,
    )
    parser.add_argument(
        "-c",
        "--cfg",
        required=False,
        help="Path to modbus config file",
        default="modbus_cfg.yaml",
        type=str,
    )
    parser.add_argument(
        "-d",
        "--dcfg",
        required=False,
        help="Path to device config file",
        default="device_cfg.yaml",
        type=str,
    )

    args = parser.parse_args()
    server = main(
        port=args.port,
        address=args.address,
        modbus_config_file_path=args.cfg,
        device_config_file_path=args.dcfg,
    )
    server.start()
    print("Started")
