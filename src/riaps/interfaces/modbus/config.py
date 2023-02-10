import os
import logging
import yaml


def load_config_files(path_to_device_list):

    with open(path_to_device_list, 'r') as file:
        device_list = yaml.safe_load(file)

    global_debug_mode = device_list.get("GlobalDebugMode")
    path_to_configs = device_list["path_to_config_files"]
    device_configs = {}
    for device_name in device_list["names"]:
        path_to_device_config = f"{path_to_configs}/{device_name}.yaml"
        with open(path_to_device_config, "r") as file:
            device_configs[device_name] = yaml.safe_load(file)

    return device_configs, global_debug_mode



