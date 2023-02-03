import os
import logging
import yaml


class Config:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.global_debug_mode = 0
        self.device_configs = {}

    def load_config_file(self, path_to_device_component_config):

        device_component_config_file_missing = not os.path.exists(path_to_device_component_config)
        if device_component_config_file_missing:
            success = False
            error_msg = f"Component configuration file does not exist: [{path_to_device_component_config}]"
            return success, error_msg

        with open(path_to_device_component_config, 'r') as file:
            device_component_config = yaml.safe_load(file)

        if "GlobalDebugMode" in device_component_config:
            self.global_debug_mode = device_component_config["GlobalDebugMode"]
            self.logger.info(
                f"Debug setting for all devices are overridden: GlobalDebugMode={self.global_debug_mode}")

        for device_name in device_component_config["deviceNames"]:
            path_to_device_config = f"{device_component_config['path']}/{device_name}.yaml"
            device_config_file_missing = not os.path.exists(path_to_device_config)
            if device_config_file_missing:
                success = False
                error_msg = f"Device configuration file does not exist: [{path_to_device_config}]"
                return success, error_msg

            with open(path_to_device_config, 'r') as file:
                device_config = yaml.safe_load(file)

            self.device_configs[device_name] = device_config[device_name]

        number_of_devices_configured = len(self.device_configs)
        self.logger.info(f"{number_of_devices_configured} Modbus devices found in configuration:")
        for k in self.device_configs:
            self.logger.info(f"{k}")
        success = True
        msg = f"Modbus devices found in configuration: {len(self.device_configs)}"
        return success, msg
