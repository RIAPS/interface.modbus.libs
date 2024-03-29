# Modbus Example Application

## Overview
This is an example of how to use the device component implementation of Modbus for the RIAPS platform.

# Application Developer Notes

An application using a modbus device component requires:
1. A device list configuration YAML file e.g., `cfg/Test_Device.yaml`
2. Corresponding device configuration YAML files, e.g., `cfg/Test_NEC-BESS1.yaml`
3. Specification of the device in the application's (dot)riaps file
4. A python class file implementing the Modbus device component specified in the (dot)riaps file. 
 

## Modbus Device List Configuration YAML File
The Modbus device list configuration YAML file defines:
1. The relative path to the device configuration files from the application directory
2. A list of the names of the device configuration files

## Modbus Device Configuration YAML Files
A Modbus device configuration YAML file defines:
1. Name: The device name
2. Protocol: The communication protocol
3. TCP/RS232: The parameters for the selected protocol
4. SlaveID: The id of the modbus device
5. Poll_Interval_Seconds: The delay between modbus polling events
6. poll: The list of parameters to poll
7. debugMode: If True then the debug statements will be printed.
8. The names of the modbus device variables and parameters, which have as values the parameters required by the `execute` command of the modbus_tk library. The parameters are:
   1. function: The tested modbus functions are:
      1. READ_HOLDING_REGISTERS
      2. WRITE_MULTIPLE_REGISTERS
      3. READ_INPUT_REGISTERS
   2. start: The starting registry address for the device parameter
   3. length: The number of registers used to store the device parameter
   4. output_value(write): The value to write to the register
   5. data_format: Makes it possible to extract the data like defined in the struct python module documentation
   6. expected_length: Not used
   7. write_starting_address_FC23: Not used
   8. Additional Parameters: Indicating ***EITHER*** scale factor and unit ***OR*** bit position
      -  scale_factor: Used to scale input and output values if necessary to store in the register
      -  units: Units of the input and out of the modbus 

         ***OR***

      - bit_position: If the parameter of interest is a bit in a particular register, this allows the user to specify that bit's position
  

## RIAPS Application File
The (dot)riaps file  must contain a device that takes a path to the device list file and provides two inside ports called `modbus_command_port` and `modbus_event_port`. 
```
device ModbusDevice(path_to_device_list)
    {
    	inside modbus_command_port;
		inside modbus_event_port;
    }
```

## Python Modbus Device Class 

The python class file implementing the Modbus device component specified in the (dot)riaps file inherits from `ModbusDeviceComponent` class from ` riaps.interfaces.modbus/ModbusDeviceComponent.py` and should implement the `on_modbus_command_port` and `on_modbus_event_port` handlers to do anything with the response from the modbus. 
```python
from riaps.interfaces.modbus.ModbusDeviceComponent import ModbusDeviceComponent
...
class ModbusDevice(ModbusDeviceComponent):
   def __init__(self, path_to_device_list):
      super().__init__(path_to_device_list)
        
   def on_modbus_event_port(self):
     msg = self.modbus_event_port.recv_pyobj()
     self.logger.info(f"modbus_event_port received msg: {msg}")
     # --- message handling logic here ---
     
   def on_modbus_command_port(self):
     # Receive response from modbus device
     msg = self.modbus_command_port.recv_pyobj()
     self.logger.info(f"modbus_command_port receive response msg: {msg}")
     # --- message handling logic here ---

   def some_function(self):
      msg = {"to_device": "Test_NEC-BESS1",
             "parameter": "GeneratorStatus",
             "operation": "write",
             "values": [5]}
      self.send_modbus(msg) 
```

The `on_modbus_event_port` and `on_modbus_command_port` handlers receive the response from the modbus polling and sent commands respectively.

### Sending Messages
Messages can be sent to the modbus device using the `send_modbus` function which takes a dictionary of the form:
```python
msg = {"to_device": "[modbus device name]",
       "parameter": "[parameter of interest]",
       "operation": "[read or write]",
       "values": "[values to write to registers]"}
```

- The value `[modbus device name]` needs to match the name specified in the Modbus device list configuration YAML file. For example, `Test_NEC-BESS1`.
- `[parameter of interest]` is the parameter to read or write, e.g., `GeneratorStatus`.
- `[read or write]` is the string `"read"` or the string `"write"`. 
- `[values to write to registers]` is a list of the values to be written.

# How to Use This Example
1. Modify the `MinimalModbusAppl.depl`, `cfg/Test_NEC-BESS1.yaml` and `cfg/Test_NEC-BESS2.yaml` files to the IP address of the system simulating the Modbus.
2. Launch the Modbus slave simulator
   1. ```commandline
      cd simulator
      ```
   2. Open two terminal windows
   3. run the command below with `--port 501` in one and `--port 502` in the other for the appropriate IP address.
      ```commandline
      sudo python3 tcpslave.py --address 172.21.20.70 --config nec_bess_slave.yaml --port 501
      ```
3. Launch the application using `riaps_ctrl`.

# Tests for Library Developers
When installing this package, use the following command to include additional testing packages:
```commandline
sudo python3 -m pip install .[dev]
```

To run the included test example, the `interface.modbus.libs/example/Minimal/MinimalModbusApp.depl` and `required_clients` in `interface.modbus.libs/tests/test_app.py` must be updated to reflect the IP address of the node that communicates with the modbus device. Then tests can be run with:
```commandline
pytest -s -v .
```

# Troubleshooting

# Package Notes 

# Notes

# Roadmap
