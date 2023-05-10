# Simulated Modbus Slave for testing

Slave execution command:

    $ sudo python3 tcpslave_sim.py --address <ip_address> --port <port_number> --config <path_to_modbus_config> --dcfg <path_to_device_config>


Example:

    $ sudo python3 tcpslave_sim.py --address '10.0.3.102' --port 5502 --cfg ./modbus_cfg.yaml --dcfg ./device_cfg.yaml

The `modbus_cfg.yaml` file specifies the parameters of the blocks to be created for the simulated modbus device. Following the `modbus_tk` library the block types are:
```python
COILS = 1
DISCRETE_INPUTS = 2
HOLDING_REGISTERS = 3
ANALOG_INPUTS = 4
```
The `starting_address` can be set to mimic a particular modbus device.
The `num_registers` is the number of register to include that block. 

The `device_cfg.yaml` file is used to set the initial values in the simulated device.
The top level parameter name (e.g., `Parm1`) can be set as desired for readability.
* `register_name` is a convenience parameter for readability.
* `block_name` is one of the blocks defined in the `modbus_cfg.yaml`
* `starting_address` is the 0-indexed address of the first 16 bit register for the data.
* `initial_values` is a list of the values to put into the registers
* `byte_order` is either `BE` or `LE` and determines whether to store the values as big or little-endian. 
* `data_type` is one of the types defined in the [python struct library](https://docs.python.org/3/library/struct.html#format-characters)
* `num_registers` is the number of 16 bit registers required to hold the values. E.g., a 32 bit float would use `f` and require 2 16 bit registers. While a 64 bit float would use `d` and require 4 16 bit registers. The "standard size" in the python struct library is the number of bytes (8bits) used by each data type.  
* `scale_factor` scales the input values if required to be compatible with the specified data type.
* `Units` is for readability and convenience. It is not used in the code.

# Additional Examples
From the `example/simulator` directory:

Terminal 1:
```bash
sudo python3 tcpslave_sim.py --dcfg ncsu_opal_dsp115_cfg.yaml
```

Terminal 2:
```bash
sudo python3 tcpslave_sim.py --dcfg ncsu_opal_dsp116_cfg.yaml
```

From the `example/simulator/reader` directory:
Terminal 3:
```bash
python3 read_sim.py
```