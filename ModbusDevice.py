# riaps:keep_import:begin
import time

from riaps.run.comp import Component
from libs.ModbusSystemSettings import ModbusSystem
import yaml
from modbus_tk import modbus_tcp
from modbus_tk import modbus_rtu
import modbus_tk.defines as cst
import spdlog
import capnp
import device_capnp
import os
import datetime
import struct
import serial

import libs.helper as helper


# riaps:keep_import:end


class ModbusDevice(Component):
    # riaps:keep_constr:begin
    def __init__(self, config):
        super(ModbusDevice, self).__init__()

        self.ModbusConfigError = True

        self.poll_exit = False

        self.logger.info("starting")

        self.pid = os.getpid()

        try:
            if os.path.exists( config ) :
                # Load config file to interact with Modbus device
                with open(config, 'r') as cfg:
                    self.cfg = yaml.safe_load(cfg)

                self.ModbusConfigError = False
            else:
                self.logger.info( 'Configuration file does not exist [{0}].'.format( config ) )

        except OSError:
            self.logger.info( 'File I/O error [{0}].'.format( config ) )

        if not self.ModbusConfigError :
            try : # handle dictionary key errors

                # Get the names of all the devices
                self.modbus_devices = list(self.cfg.keys())

                # Get the first modbus device from the yaml file
                self.dvc = self.cfg[self.modbus_devices[0]]

                # set device_name, used in events sent to the controller to identify the device
                self.device_name = str(self.modbus_devices[0])

                # set slave id. Argument required by modbus tk to send commands to Modbus
                self.slave = self.dvc['Slave']

                # set the polling interval
                self.interval = self.dvc['Interval']

                # Start Modbus master
                # if Serial is defined in config file then use serial communication
                if 'RS232' in self.dvc :
                    try:
                        self.master = modbus_rtu.RtuMaster(serial.Serial(port=self.dvc['RS232']['device'],
                                                                        baudrate=self.dvc['RS232']['baudrate'],
                                                                        bytesize=self.dvc['RS232']['bytesize'],
                                                                        parity=self.dvc['RS232']['parity'],
                                                                        stopbits=self.dvc['RS232']['stopbits'],
                                                                        xonxoff=self.dvc['RS232']['xonxoff']))

                        self.master.set_timeout(ModbusSystem.Timeouts.TTYSComm)
                        self.master.set_verbose(ModbusSystem.Debugging.Verbose)
                        self.logger.info( 'Modbus RTU Connected to Slave [{0}] on Port [{1}]'.format( self.slave, self.device ) )
                    except Exception as ex:
                        self.logger.info('Modbus RTU Creation Exception: {0}'.format(ex))
                        self.master = None

                elif 'TCP' in self.dvc:
                    addr = self.dvc['TCP']['Address']
                    port = self.dvc['TCP']['Port']

                    try:
                        self.master = modbus_tcp.TcpMaster(addr, port)
                        self.master.set_timeout(ModbusSystem.Timeouts.TCPComm)
                        self.master.set_verbose(ModbusSystem.Debugging.Verbose)
                        self.logger.info( 'Modbus TCP Connected to Slave [{0}] on Address [{1}:{2}]'.format( self.slave, addr, port ) )
                    except Exception as ex:
                        self.logger.info(f"Modbus TCP Creation Exception: {ex}")
                        self.master = None
                else :
                    self.logger.info(f"Modbus device has no communication configuration defined.")
                    self.master = None
                    
            except KeyError as kex:
                self.logger.info(f"Modbus configuration is missing required setting: {kex}")    
                self.ModbusConfigError = True

        else:
            pass # Device cannot operate due to configuration error

    # riaps:keep_constr:end

    # riaps:keep_device_port:begin
    def on_device_port(self):
        # receive
        start = datetime.datetime.now()  # measure how long it takes to complete query
        msg_bytes = self.device_port.recv()  # required to remove message from queue
        msg = device_capnp.DeviceQry.from_bytes(msg_bytes)

        values = []
        modbus_duration = {}
        for idx, param in enumerate(msg.param):

            # construct yaml file command
            param_op = f"{param}_{msg.operation}"

            # fetch yaml file command
            modbus_func = self.cfg[msg.device][param_op]

            # read Modbus command parameters from yaml file
            function_code = modbus_func['function']
            starting_address = modbus_func['start']
            length = modbus_func['length']
            value = msg.value[idx]  # value is specified in the request message
            # scale value per yaml file and convert to int to send to Modbus slave

            if 'data_format' in list(modbus_func.keys()):
                data_fmt = modbus_func['data_format']
            else:
                data_fmt = ''

            if 'bit_position' in list(modbus_func.keys()):
                bit_pos = modbus_func['bit_position']
                modbus_value = int(value)
            else:
                bit_pos = -1
                if data_fmt == '':
                    modbus_value = [int(value / modbus_func['Units'][0])]
                else:
                    modbus_value = value

            try:
                # if this is a bit write operation read the current value
                # then mask in the correct new value
                # finally write the modified value back to the modbus device
                if bit_pos != -1 and "WRITE" in function_code:
                    temp_code = cst.READ_HOLDING_REGISTERS
                    # TODO: measure time of this in OPAL
                    modbus_start = datetime.datetime.now()
                    temp_response = self.master.execute(self.slave,
                                                        temp_code,
                                                        starting_address,
                                                        quantity_of_x=length,
                                                        output_value=modbus_value,
                                                        data_format=data_fmt)
                    modbus_duration[f"{param}_READ"] = (datetime.datetime.now() - modbus_start).total_seconds()
                    # FIRST READ REGISTER

                    if modbus_value == 0:
                        modbus_value = self.clr_bit(temp_response[0], bit_pos)
                    else:
                        modbus_value = self.set_bit(temp_response[0], bit_pos)
                    # THEN MASK IN CORRECT VALUE
                    # TODO: Better way to mask?

                modbus_start = datetime.datetime.now()  # measure how long it takes to query modbus
                response = self.master.execute(self.slave,
                                               getattr(cst, function_code),
                                               starting_address,
                                               quantity_of_x=length,
                                               output_value=modbus_value,
                                               data_format=data_fmt)
                modbus_duration[param] = (datetime.datetime.now() - modbus_start).total_seconds()
                # modbus_duration.append((datetime.datetime.now() - modbus_start).total_seconds())  # measure how long it takes to query modbus
                # EXECUTE REQUESTED FUNCTION

                if bit_pos != -1:
                    if str(bin(response[0])[2:][bit_pos]) == "1":
                        value = 1
                    else:
                        value = 0
                else:
                    if self.dvc["debugMode"]:
                        self.logger.info(f"\n{helper.Yellow}"
                                         f"Param_op: {param_op}"
                                         f"\nCommand: {function_code}"
                                         f"\nSector: {getattr(cst, function_code)}"
                                         f"\nResponse from modbus: "
                                         f"\n{response}{helper.RESET}")
                    if msg.operation == "WRITE":
                        value = response[1]
                    else:
                        value = response[0] * modbus_func['Units'][0]
                values.append(value)

            except Exception as ex:
                modbus_evt = device_capnp.DeviceEvent.new_message()
                modbus_evt.event = f"Modbus({msg.device}) Exception on_device_port()->{ex}"
                modbus_evt_bytes = modbus_evt.to_bytes()
                self.event_port.send(modbus_evt_bytes)

                # Construct message to send back to controller
                # The parameters are defined in modbusexample.capnp

        ans_msg = device_capnp.DeviceAns.new_message()
        ans_msg.reply = msg.operation
        ans_msg.values = values
        ans_msg.delay = time.time() - msg.timestamp
        ans_msg_bytes = ans_msg.to_bytes()

        # Send message to controller
        self.device_port.send(ans_msg_bytes)

        elapsed_time = datetime.datetime.now() - start

        # log Modbus call
        if self.dvc["debugMode"]:
            self.logger.info(f"{helper.Cyan}\n\n"
                             f"\nMessage from Control: \n {msg}"
                             f"\nMessage time: {msg.timestamp}"  # time when ComputationalComponent sent message to modbus device
                             f"\nCurrent time: {time.time()}"
                             f"\n modbus_response: {values}"
                             f"\nelapsed_time: {elapsed_time}"
                             f"\nmodbus query time: {modbus_duration}\n{helper.RESET}")

    # riaps:keep_device_port:end

    # riaps:keep_poller:begin
    def on_poller(self):
        """Poll all variable names specified in yaml file"""

        now = self.poller.recv_pyobj()
        if self.dvc["debugMode"]:
            self.logger.info(f"on_poller now: {now}")
        comm_error = False
        time_over_run = False

        if self.dvc["poll"]:
            for var in self.dvc["poll"]:
                modbus_evt = device_capnp.DeviceEvent.new_message()
                modbus_evt.device = self.device_name
                # Prepare status message to send on pub port.

                if not self.poll_exit and not comm_error and not time_over_run:
                    t1 = datetime.datetime.now()
                    values = []
                    names = []
                    units = []
                    post_event = False

                    # setup limits if they exist
                    if self.dvc["poll"][var]:
                        max_threshold = self.dvc["poll"][var][0]
                        min_threshold = self.dvc["poll"][var][1]
                    else:
                        max_threshold = None
                        min_threshold = None

                    # Construct message from yaml file
                    # The message fields are defined in the capnp file
                    func = self.dvc[var]
                    function_code = func['function']
                    starting_address = func['start']
                    length = func['length']
                    if 'data_format' in list(func.keys()):
                        data_fmt = func['data_format']
                    else:
                        data_fmt = ''

                    # See if this is a bit read
                    if 'bit_position' in list(func.keys()):
                        bit_pos = func['bit_position']
                    else:
                        bit_pos = -1

                    modbus_evt.command = var

                    # Send command to Modbus slave
                    try:
                        modbus_response_uint = self.master.execute(self.slave,
                                                                   getattr(cst, function_code),
                                                                   starting_address,
                                                                   quantity_of_x=length,
                                                                   data_format=data_fmt)
                        # fill out more status fields
                        modbus_evt.event = 'POLLED'
                        modbus_evt.error = 0
                        # self.logger.info(f"{helper.Cyan}\ncall: {var}; response: {str(modbus_response_uint)}\n{helper.RESET}")

                        # convert Modbus response from uint to int
                        if data_fmt == '':
                            # modbus_response = (np.array(modbus_response_uint, dtype="uint16").view(np.int16))
                            modbus_response = list(
                                map(lambda ui:
                                    struct.unpack("h",
                                                  struct.pack("H", ui))[0],
                                    modbus_response_uint))
                        else:
                            modbus_response = modbus_response_uint
                            # self.logger.info( "modbus_response: {0}".format( modbus_response ) )

                    except Exception as ex:
                        if self.dvc["debugMode"]:
                            self.logger.info('Modbus Exception: {0}'.format(ex))
                        modbus_evt.event = 'ERROR'
                        modbus_evt.error = -1
                        names = ['Exception: {0}'.format(ex), ]
                        units = ['ERROR', ]
                        values = [-1.0, ]
                        modbus_response = [modbus_evt.error, ]
                        min_threshold = None
                        max_threshold = None
                        comm_error = True
                        if self.dvc["debugMode"]:
                            self.logger.info(f'Modbus response error {str(modbus_response)}')

                    # if there is an error the length of the list will always be 1
                    # Must distinguish between a single value register or single value float, word, dword
                    # if data_fmt = '' we are dealing with a single register
                    # otherwise this is a data type greater than a 16bit value
                    if len(modbus_response) == 1 and data_fmt == '':
                        if modbus_evt.event == 'POLLED':
                            # only do a bit mask operation for single register polling
                            if bit_pos != -1:
                                # only return the state of the bit we are interested in
                                if modbus_response[0] & (1 << bit_pos) != 0:
                                    modbus_response[0] = True  # if the bit is set return True
                                else:
                                    modbus_response[0] = False
                                scaler = 1.0
                                units = ['', ]
                            else:
                                scaler = float(func['Units'][0])
                                units = [(func['Units'][1]), ]

                            formatted_value = float(modbus_response[0])
                            formatted_value = formatted_value * scaler
                            names = [var, ]
                            values = [formatted_value, ]
                        else:
                            pass
                    else:
                        # reading many different values
                        if data_fmt == '':
                            """ put the values into the riaps message """
                            d = self.format_multi_register_read(
                                starting_address,
                                length,
                                self.dvc,
                                modbus_response)

                            names = list(d.keys())
                            for n in names:
                                values.append(d[n]['Value'])
                                units.append(d[n]['Units'])
                            min_threshold = None
                            max_threshold = None
                        else:  # reading a single value that was multiple registers
                            names = [var, ]
                            values = [modbus_response[0], ]
                            units = [(func['Units'][1]), ]

                    # if no limits then always post the modbus response
                    if min_threshold is None and max_threshold is None:
                        post_event = True
                    else:  # if there are limits then evaluate them
                        if max_threshold is not None:
                            if values[0] > max_threshold:  # if value is greater than limit then post event
                                post_event = True
                        if min_threshold is not None:
                            if values[0] < min_threshold:  # if value is less than limit post event
                                post_event = True

                    # Finish status message to send on pub port
                    modbus_evt.values = values
                    modbus_evt.names = names
                    modbus_evt.units = units
                    et = datetime.datetime.now() - t1
                    modbus_evt.et = et.total_seconds()

                    # Publish status message on pub port if outside of limits or no limits
                    if post_event:
                        self.event_port.send(modbus_evt.to_bytes())
                    if et.total_seconds() > self.interval / 1000:
                        time_over_run = True
                else:
                    # the polling loop did not complete normally, show a message why
                    if self.poll_exit:
                        self.error(modbus_evt,
                                   "Polling loop deactivated",
                                   self.device_name,
                                   ModbusSystem.Errors.AppPollExit)
                    elif comm_error == True:
                        self.error(modbus_evt,
                                   "Polling loop communication error",
                                   self.device_name,
                                   ModbusSystem.Errors.CommError)
                    else:
                        self.error(modbus_evt,
                                   "Polling loop timer overrun",
                                   [self.interval, "msec"],
                                   ModbusSystem.Errors.PollTimerOverrun)

                    self.event_port.send(modbus_evt.to_bytes())
                    break
        else: # nothing to poll
            pass
            
    # riaps:keep_poller:end

    # riaps:keep_impl:begin
    def handleActivate(self):
        if not self.dvc["poll"]:
            if self.poller != None:
                self.poller.halt()
                self.logger.info("No parameters configured for polling. Modbus poller timer has been stopped!")
        else:    
            if self.poller != None:
                cur_period = self.poller.getPeriod() * 1000
                self.poller.setPeriod(self.interval / 1000.0)
                new_period = self.poller.getPeriod() * 1000
                self.logger.info(f"Modbus Poller Interval changed from {cur_period} msec to {new_period} msec")
                if 'RS232' in self.dvc:
                    comm_time_out = ModbusSystem.Timeouts.TTYSComm
                    self.logger.info(f"Modbus RTU device comm timeout is {comm_time_out} msec")
                else:
                    comm_time_out = ModbusSystem.Timeouts.TCPComm
                    self.logger.info( f"Modbus TCP device comm timeout is {comm_time_out} msec" )  
                
                if new_period < comm_time_out :
                    self.logger.info( f"Modbus Poller Interval is less than communication timeout of {comm_time_out} msec. " )  
                    self.disable_polling()

   # Should be called before __destroy__ when app is shutting down.  
   # this does not appear to work correctly       
    def handleDeactivate( self ):
        self.logger.info( "Deactivating Modbus Device" )
        self.logger.info( f"self.master is {self.master}" )

    # Format and error event message that will get passed to an upper level
    # RIAPS component
    def error( self, evt, error, vals, errnum = -1, et=None ):
        evt.device = self.device_name
        evt.event = 'ERROR'
        evt.error = errnum
        evt.values = [-1.0, ]
        evt.names = [f"{error} ({vals})"]
        evt.units = ['ERROR', ]
        if et != None:
            evt.et = et
        return evt

    # Clean up and shutdown 
    def __destroy__(self):
        if self.poller.running() == True :
            self.disable_polling()
            
            if self.master != None :
                self.master.close()
            
            self.poller.terminate() 

        self.logger.info("__destroy__ complete for - %s" % self.device_name)    
 
    # Do not allow the polling loop to send messages to the modbus device
    def disable_polling(self):
        self.logger.info("Disabling modbus polling for - %s" % self.device_name)
        self.poll_exit = True

    # Allow the polling loop to send messages to the modbus device
    def enable_polling(self):
        self.logger.info("Enabling modbus polling for - %s" % self.device_name)
        self.poll_exit = False

    # set an individual bit on a value
    def set_bit(self, value, bit):
        """ Sets a bit in the data 'value' at position index specified by 'bit' """
        return value | (1 << bit)

    # clear an individual bit on a value
    def clr_bit(self, value, bit):
        """ Clears a bit in the data 'value' at position index specified by 'bit' """
        return value & ~(1 << bit)

    """ Function creates a dictionary of associated items    
    start : the address of the first register that was read
    length : the number of registers read
    dev : the configuration data for all modbus-device's commands
    data : the raw data returned from the modbus query

    This function matches the data, by index, with the configured address and then
    adds an entry in the dictionary.
    Each entry contains:
    Value: In floating point and scaled as required
    Units: The units of the measurement
    Address: The register address"""

    def format_multi_register_read(self, start, length, dev, data):
        resp_dict = {}
        for p in dev:
            # only look at read parameter definitions in the device configuration
            if p.find('_READ') != -1:
                # get the parameter information
                parm = dev[p]
                # make sure there is a units field in the definition
                if 'Units' in list(parm.keys()):
                    cur_addr = parm['start']
                    cur_len = parm['length']
                    # do add entries for commands that read multiple registers
                    if cur_len == 1:
                        if start <= cur_addr < (start + length):
                            # apply the scale and format the data into floating point
                            cur_scaler = float(parm['Units'][0])
                            cur_units = parm['Units'][1]
                            index = cur_addr - start
                            resp_dict[p] = {'Value': (float(data[index]) * cur_scaler),
                                            'Units': cur_units,
                                            'Address': cur_addr}
                        else:
                            pass
                else:
                    pass
            else:
                pass

        return resp_dict
# riaps:keep_impl:end