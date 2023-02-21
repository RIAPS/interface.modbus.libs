# Standalone Modbus TCP Master and Configurable Modbus Slave
 
    The master accepts socket connections, takes generalized commands, formats the command for Modbus RTU transmission, executes the command. Command format is shown below, each segment is separated by a comma.

        $ <ipaddress>:<port>:<id>,access,parameter or $<device name>,access,parameter

        Examples: a) $ 10.0.3.100:502:1,READ,Power Real    
                  b) $ BBB-53B9,READ,Power Real    
                  
# Configurable Modbus Slave

    Slave execution command:

    $ sudo python3 tcpslave.py --address <ip_address> --port <port_number> --name <NameOfDevice> --config <path_to_config>

    Example:

    $ sudo python3 tcpslave.py --address '10.0.3.102' --port 502 --name PhotoVoltaic --config ./pv_slave.yaml

    * Modify the slave.yaml file to define the parameter names, addresses, and default values required.  

    * For Banshee simulation slaves see: dg_slave.yaml, pv_slave.yaml, and ess_slave.yaml for Diesel Generator, Photovoltaic, and Battery controller definitions.


# Start the Master Modbus application as follows:

    1) Change directory to the location of 'riaps_tcpmaster.py'
    2) Insure the configuration file is located in this directory or specify complete path ('./master.yaml')

    $ sudo riaps_tcpmaster.py --config ./master.yaml --address 10.0.3.104 --port 12345

    This reads the configuration file and connects to the modbus slaves described in the master.yaml file.

# Modbus master useful commands

    A list of all Modbus parameters that are configured for the device may be viewed using the following (ls) command:

    The device must contain the IP, Port, and slave index for the device to query.

        $ ls 10.0.3.100:502:1    or    $ ls BBB-53B9

        Parameter list for BBB-53B9(10.0.3.100:502:1):
        
        $ Name: Vrms Phase A Access: ['READ'] Type: float Units: V
        
                Example: 10.0.3.100:502:1,READ,Vrms Phase A
        
        $ Name: Vrms Phase B Access: ['READ'] Type: float Units: V
        
                Example: 10.0.3.100:502:1,READ,Vrms Phase B
        
        $ Name: Vrms Phase C Access: ['READ'] Type: float Units: V
        
                Example: 10.0.3.100:502:1,READ,Vrms Phase C
        
        $ Name: Power Real Access: ['READ'] Type: float Units: KW
        
                Example: 10.0.3.100:502:1,READ,Power Real
        
        $ Name: Power Reactive Access: ['READ'] Type: float Units: KW
        
                Example: 10.0.3.100:502:1,READ,Power Reactive
        
        $ Name: Power Apparent Access: ['Read'] Type: float Units: KW
        
                Example: 10.0.3.100:502:1,Read,Power Apparent
        
        $ Name: Frequency Access: ['READ', 'WRITE'] Type: float Units: Hz
        
                Example: 10.0.3.100:502:1,READ,Frequency

        $ Name: Frequency Droop Access: ['READ', 'WRITE'] Type: float Units: PCT

                Example: 10.0.3.100:502:1,READ,Frequency Droop

        $ Name: Voltage Droop Access: ['READ', 'WRITE'] Type: float Units: PCT

                Example: 10.0.3.100:502:1,READ,Voltage Droop


    A list of all Modbus devices configured and controlled by the master application may be viewed using the (ls) command:

        $ ls -d

        Name        IP            Port    ID    State        Description
        BBB-53B9    10.0.3.100    502     1     Running      Genset Model-100
        BBB-D5B5    10.0.3.102    502     1     Running      Genset Model-102
        VM-LOCAL    127.0.0.1     502     1     Running      Genset Model-8901
