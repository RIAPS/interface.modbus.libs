# RIAPS Modbus Interface

## Overview
The library provides a device component implementation of modbus for the RIAPS platform.
To use the library the app developer must provide:
1. A device list configuration YAML file e.g., `cfg/Test_Device.yaml`
2. Corresponding device configuration YAML files, e.g., `cfg/Test_NEC-BESS1.yaml`
3. Specification of the device in the application's (dot)riaps file
4. A python class file implementing the Modbus device component specified in the (dot)riaps file. 
An example application using this library can be found in the [`example/Minimal` folder](https://github.com/RIAPS/interface.modbus.libs/tree/main/example/Minimal) with further usage details. 


## Dependencies

## Optional Dependencies

# Installation

## Install RIAPS Modbus library

* On single node locally
```commandline
sudo python3 -m pip install 'riaps.interfaces.modbus @ git+https://github.com/RIAPS/interface.modbus.libs.git'
```
* On cluster of nodes using python fabric
```commandline
riaps_fab sys.sudo:'"python3 -m pip install git+https://github.com/RIAPS/interface.modbus.libs.git"'
```

* Via cloning
```commandline
git clone https://github.com/RIAPS/interface.modbus.libs.git
cd interface.modbus.libs
sudo python3 -m pip install .
```
