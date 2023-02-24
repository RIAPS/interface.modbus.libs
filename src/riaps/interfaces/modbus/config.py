import os
import logging
import yaml


def load_config_paths(path_to_device_list):

    with open(path_to_device_list, 'r') as file:
        device_list = yaml.safe_load(file)

    global_debug_mode = device_list.get("GlobalDebugMode")
    path_to_configs = device_list["path_to_config_files"]
    device_config_paths = {}
    for device_name in device_list["names"]:
        path_to_device_config = f"{path_to_configs}/{device_name}.yaml"
        device_config_paths[device_name] = path_to_device_config
        # with open(path_to_device_config, "r") as file:
        #     device_configs[device_name] = yaml.safe_load(file)

    return device_config_paths, global_debug_mode



