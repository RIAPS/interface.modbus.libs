# RIAPS Modbus Library

Overview

Modbus is used to communicate and control hardware based in a, present day, standard power grid.  The intent of this project is to provide a common interface with mapping to desired parameters using an external configuration file.  This allows for the main control parameters to be defined and used across many variants by changing the address mapping and data definition of the parameters.

The RIAPS Modbus library is implemented as a device-component and, as such, is allowed elevated access to hardware resources required for Modbus communication.  Two types of communication exist, ModbusTCP and ModbusRTU.  Using the configuration file, communication over either of the previouly mentioned Modbus protocols can be realized.  T


Structure

RIAPS application may interact with the Modbus library in one of two ways, by query/answer, or, by receiving events from polled parameters.  To use the library an application must derive a device component from the ModbusDevice object.  After this the messages used must be defined and connected to RIAPS-device as shown below:

    class GEN1(ModbusDevice):
        def __init__(self, config):
            super(GEN1, self).__init__(config)       
            self.logger.info("setup GEN1")

The RIAPS-device must be defined similar to the defintion below to allow acces to the correct RIAPS ports and accept the configuration file.

	device GEN1(config)
	{
		timer poller 10 sec;
		inside modbus_cmd_port;		
		inside modbus_evt_port;
		pub event_port: LocalDeviceEvent;
		ans device_port: (Gen1DeviceQry, Gen1DeviceAns) timed;
	}

In the above device definition, modbus_evt_port and modbus_cmd_port are required and must be named as shown to allow communication to the Modbus RIAPS device.  THe application must alow define event_port if events are required and setup in the device configuration files.  In order to query the RIAPS-Modbus device the device_port is required as this is the primary port for most communitions.

Operation

Starting up the ModbusDevice is passed in the main configuration file.  In this file, all the configured Modbus-device files are listed as shown in the sample below:

filename: interface.modbus.apps/TestModbusOpal/cfg/Devices5.yaml

configs:
  - ./cfg/NEC-BESS-VM1.yaml
  - ./cfg/NEC-BESS-VM2.yaml
  - ./cfg/NEC-BESS-VM3.yaml
  - ./cfg/NEC-BESS-VM4.yaml
  - ./cfg/NEC-BESS-VM5.yaml
GobalDebugMode: 1 # 0=no debug messages, 1=RAIPS Device level debug, 2=Modbus slave low level messages

The above file lists the configuration for 5 independent Modbus-devices. Each file in the list contains the specific mapping and setup for the target Modbus hardware registers. 
 
Sample taken from filename: interface.modbus.apps/TestModbusOpal/cfg/NEC-BESS-VM1.yaml

#### NEC-BESS-VM1: 
##### Description: NEC BESS1
##### TCP:
   -    Address: 10.0.1.107 
   -    Port: 501
##### RS232:
   -   device: /dev/ttyS1
   -   baudrate: 57600
   -   bytesize: 8
   -   parity: 'N'
   -   stopbits: 1
   -   xonxoff: 0
##### Slave: 1
##### Interval: 5000
##### Neighbors: []
##### VoltageRegulateDG: 1
##### poll:
##### ReferenceInput_READ:
   - max: 2.0 
   - min: 1.0        
##### debugMode: False

##### realpowermode_READ:
   -    info: Description of parameter or command
   -    function: READ_HOLDING_REGISTERS
   -    start: 7000
   -    length: 1
   -    output_value: 0
   -    data_format: ""
   -    expected_length: -1
   -    write_starting_address_FC23: 0
   -    Units:
          - 1
          - None
   -    #Info: Generator real power (P)
 

##### realpowermode_WRITE:
   -    info: Description of parameter or command
   -    function: WRITE_MULTIPLE_REGISTERS
   -    start: 7000
   -    length: 1
   -    output_value: [0]
   -    data_format: ""
   -    expected_length: -1
   -    write_starting_address_FC23: 0
   -    Units:
          - 1
          - None
   -    #Info: Generator real power (P)

##### ReferenceInput_READ:
   -    info: Description of parameter or command
   -    function: READ_HOLDING_REGISTERS
   -    start: 7020
   -    length: 2
   -    output_value: 0
   -    data_format: ">f"
   -    expected_length: -1
   -    write_starting_address_FC23: 0
   -    Units:
          - 1
          - None
   -    #Info: Generator reference 
 

##### ReferenceInput_WRITE:
   -    info: Description of parameter or command
   -    function: WRITE_MULTIPLE_REGISTERS
   -    start: 7020
   -    length: 2
   -    output_value: [0]
   -    data_format: ">f"
   -    expected_length: -1
   -    write_starting_address_FC23: 0
   -    Units:
          - 1
          - None
   -    #Info: Generator reference 


The above configuration shows the details to configure a ModbusTCP node as slave 1.  The polling interval, if required, is set to 5 seconds.  In this example 'ReferenceInput' is polled and and if the mesaured value is less than 1.0 or greater than 2.0 an event is posted via modbus_event_port.



