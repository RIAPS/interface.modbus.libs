import yaml


def load_config_paths(path_to_device_list):

    with open(path_to_device_list, "r") as file:
        device_list = yaml.safe_load(file)

    global_debug_mode = device_list.get("GlobalDebugMode")
    path_to_configs = device_list["path_to_config_files"]
    device_config_paths = {}
    for device_name in device_list["names"]:
        path_to_device_config = f"{path_to_configs}/{device_name}.yaml"
        device_config_paths[device_name] = path_to_device_config
    return device_config_paths, global_debug_mode


def load_config_file(path_to_file):
    with open(path_to_file, "r") as file:  # Intentionally do not handle exception
        device_config = yaml.safe_load(file)
    return device_config


def load_config_files(device_config_paths):
    device_configs = {}
    for device_name in device_config_paths:
        config_path = device_config_paths[device_name]
        device_configs[device_name] = load_config_file(config_path)
    return device_configs


def validate_configuration(device_config):
    required_parameters = [
        "Name",
        "Protocol",
        device_config.get("Protocol", "MISSING"),
        "SlaveID",
    ]
    for parameter in required_parameters:
        if parameter not in device_config:
            return {"return_code": 1, "msg": f"Configuration missing for {parameter}"}

    valid_device = _validate_device_config(device_config)
    if valid_device["return_code"] != 0:
        return valid_device

    return {"return_code": 0, "msg": "Valid configuration"}


def _validate_device_config(device_config):
    """
    Validate the device configuration to ensure all required keys are present.
    """
    required_keys = {
        "TCP": ["Address", "Port"],
        "Serial": ["device", "baudrate", "bytesize", "parity", "stopbits"],
    }

    protocol = device_config.get("Protocol")
    if protocol not in required_keys:
        error_message = f"Unsupported protocol: {protocol}"
        return {"return_code": 1, "msg": error_message}

    missing_keys = [
        key
        for key in required_keys[protocol]
        if key not in device_config.get(protocol, {})
    ]
    if missing_keys:
        error_message = (
            f"Missing keys in {protocol} configuration: {', '.join(missing_keys)}"
        )
        return {"return_code": 1, "msg": error_message}

    return {"return_code": 0, "msg": "Valid device configuration"}
