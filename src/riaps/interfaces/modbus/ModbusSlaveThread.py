import threading
import zmq
import datetime as dt
from modbus_tk import modbus_rtu
from modbus_tk import modbus_tcp
import modbus_tk.defines as cst
import serial
import spdlog
import capnp
import riaps.interfaces.modbus.device_capnp as msg_schema
import riaps.interfaces.modbus.TerminalColors as tc
from riaps.interfaces.modbus.ModbusSystemSettings import ModbusSystem
from riaps.interfaces.modbus.ModbusPoller import ModbusPoller


# Class that communicates with a Modbus-TCP device
class ModbusSlave(threading.Thread):
    def __init__(self, logger, config, deviceport, eventport=None):
        threading.Thread.__init__(self)
        self.logger = logger
        self.dvc = None
        self.deviceport = deviceport
        self.eventport = eventport
        self.polling_thread = None
        self.poll_dict = {}
        self.active = threading.Event()
        self.active.set()
        self.dormant = threading.Event()
        self.dormant.clear()
        self.address = None
        self.port = None
        self.id = 0
        self.plug = None
        self.master = None
        self.slave = None
        self.debugMode = False
        self.device = "NONE"

        try:
            self.device_name = list(config.keys())[0]
            self.dvc = config[self.device_name]
            self.ModbusConfigError = False  # TODO: probably remove this once things are cleaner.
        except KeyError as kex:
            self.logger.info(f"Modbus device configuration error: {kex}")
            self.ModbusConfigError = True
            return

        try:  # handle dictionary key errors
            # set slave id. Argument required by modbus tk to send commands to Modbus
            self.slave = self.dvc['Slave']
            # set the polling interval
            self.interval = self.dvc['Interval']
            # set the debug mode for logging
            self.debugMode = self.dvc["debugMode"]
            # Start Modbus master
            # if Serial is defined in config file then use serial communication
            if 'RS232' in self.dvc:
                comname = 'RS232'
            elif 'Serial' in self.dvc:
                comname = 'Serial'
            elif 'TCP' in self.dvc:
                comname = 'TCP'
            else:
                comname = ""

            if comname == 'RS232' or comname == 'Serial':
                try:
                    self.device = self.dvc[comname]['device']
                    self.master = modbus_rtu.RtuMaster(serial.Serial(port=self.device,
                                                                     baudrate=self.dvc[comname]['baudrate'],
                                                                     bytesize=self.dvc[comname]['bytesize'],
                                                                     parity=self.dvc[comname]['parity'],
                                                                     stopbits=self.dvc[comname]['stopbits'],
                                                                     xonxoff=self.dvc[comname]['xonxoff']))

                    self.master.set_timeout((ModbusSystem.Timeouts.TTYSComm / 1000.0), use_sw_timeout=True)
                    self.master.set_verbose(ModbusSystem.Debugging.Verbose)
                    self.logger.info(
                        'Modbus RTU Connected to Slave [{0}] on Port [{1}]'.format(self.slave, self.device))
                except Exception as ex:
                    self.logger.info('Modbus RTU Creation Exception: {0}'.format(ex))

            elif comname == 'TCP':
                addr = self.dvc[comname]['Address']
                port = self.dvc[comname]['Port']

                try:
                    self.device = "TCP"
                    self.master = modbus_tcp.TcpMaster(addr, port)
                    self.master.set_timeout((ModbusSystem.Timeouts.TCPComm / 1000.0))
                    self.master.set_verbose(ModbusSystem.Debugging.Verbose)
                    self.logger.info(
                        'Modbus TCP Connected to Slave [{0}] on Address [{1}:{2}]'.format(self.slave, addr, port))
                except Exception as ex:
                    self.logger.info(f"Modbus TCP Creation Exception: {ex}")
            else:
                self.logger.info(f"Modbus device has no communication configuration defined.")

            if self.master is None:
                return

            if self.eventport is None:
                self.logger.info(f"Modbus poller has no RIAPS publish port defined.")
                return

            if self.dvc.get("poll"):  # If the 'poll' key is defined in the device configuration file.
                for v in self.dvc["poll"]:
                    poll_func = self.dvc[v]
                    function_code = poll_func['function']
                    starting_address = poll_func['start']
                    length = poll_func['length']
                    scale = poll_func['Units'][0]
                    units = poll_func['Units'][1]

                    data_fmt = poll_func.get("data_format",
                                             '')  # use value from config if it exists, otherwise use an empty string
                    max_thr = self.dvc["poll"][v].get("max", None)
                    min_thr = self.dvc["poll"][v].get("min", None)

                    self.poll_dict[v] = [function_code,
                                         starting_address,
                                         length,
                                         scale,
                                         units,
                                         data_fmt,
                                         max_thr,
                                         min_thr]

            # If there are parameters to poll then create a polling thread object
            if len(self.poll_dict) == 0:
                self.logger.warn(f"Modbus poller will not be started!")
                self.logger.warn(
                    f"Modbus poller parameters are either not configured or not present in configuration file.")
                return

            self.polling_thread = ModbusPoller(self.device_name,
                                               self.slave,
                                               self.master,
                                               self.poll_dict,
                                               self.eventport,
                                               self.interval)

        except KeyError as kex:
            self.logger.info(f"Modbus configuration is missing required setting: {kex}")

        self.logger.info(f"ModbusSlave __init__ complete")

    def get_device_name(self):
        return self.device_name

    def get_plug(self):
        return self.plug

    def deactivate(self):
        self.active.clear()

    def pause(self):
        self.dormant.set()

    def resume(self):
        self.dormant.clear()

    def enable_debug_mode(self, enable=True):
        self.debugMode = enable
        self.logger.info(f"Modbus Slave [{self.device_name}] debugMode is set to [{self.debugMode}]")

    def read_modbus(self, command):
        try:
            modbus_func = self.dvc[command]
            # read Modbus command parameters from yaml file
            function_code = modbus_func['function']
            starting_address = modbus_func['start']
            length = modbus_func['length']

            bit_position = modbus_func.get("bit_position", -1)
            Units = modbus_func.get("Units", [1.0, "None"])  # Default values aren't used for anything
            scale_factor = float(Units[0])
            units = Units[1]
            data_fmt = modbus_func.get("data_format", '')

            if self.debugMode:
                t1 = dt.datetime.now()
                self.logger.info(
                    f"Reading: starting_address={starting_address}, quantity_of_x={length}, timestamp={t1}")

            values = []

            try:
                response = list(self.master.execute(self.slave,
                                                    getattr(cst, function_code),
                                                    starting_address,
                                                    quantity_of_x=length,
                                                    data_format=data_fmt))
            except Exception as ex:
                results = {"command": command, "values": values, "units": "error"}
                if self.debugMode:
                    self.logger.info(f"Modbus command({command}) error={ex})")
                return results

            if self.debugMode:
                self.logger.info(
                    f"Response: starting_address={starting_address}, "
                    f"response={response}, "
                    f"timestamp={dt.datetime.now()}")

            # Get the current value of the bit at the bit_position specified
            for current_value in response:
                if bit_position < 0:  # If bit_position is not valid
                    values.append(float(current_value * scale_factor))
                else:
                    self.logger.info(f"get bit value at position {bit_position} in {current_value}")
                    bit_value = self.get_bit(current_value, bit_position=bit_position)
                    values.append(bit_value)

                    if self.debugMode:
                        human_readable = "Set" if bit_value == 1 else "Clear"
                        self.logger.info(
                            f"{tc.Yellow}"
                            f"Bit Read: command={command},"
                            f" register value={current_value}, "
                            f"target bit={bit_position}, "
                            f"result={human_readable}"
                            f"{tc.RESET}")

            results = {"command": command, "values": values, "units": units}

        except KeyError:
            units = "Unknown"
            results = {"command": command, "values": [], "units": units}
            self.logger.error(f"Unexpected Exception. Create new handler: {results}")

        if self.debugMode:
            self.logger.info(f"Return values: {results}")

        return results

    def write_modbus(self, command, values):
        bit_read_error = False
        results = {}
        try:
            modbus_func = self.dvc[command]
            # read Modbus command parameters from cofiguration
            function_code = modbus_func['function']
            starting_address = modbus_func['start']
            length = modbus_func['length']
            if "bit_position" in modbus_func:
                units = "None"
                scaler = 1
                bit = int(modbus_func["bit_position"])
                cmd = command.replace("WRITE", "READ")
                data = self.read_modbus(cmd)
                if len(data["values"]) > 0:
                    temp = int(data["values"][0])
                    if values[0] == 0:
                        values[0] = float(self.clr_bit(temp, bit))
                    else:
                        values[0] = float(self.set_bit(temp, bit))
                else:
                    bit_read_error = True
            else:
                scaler = modbus_func['Units'][0]
                units = modbus_func['Units'][1]

            if 'data_format' in modbus_func:
                data_fmt = modbus_func['data_format']
            else:
                data_fmt = ""

            if data_fmt == "":
                modbus_value = []
                for v in values:
                    modbus_value.append(int(v / scaler))
            else:
                modbus_value = values

            if self.debugMode:
                self.logger.info(f"values={values}, length={length}, modbus values = {modbus_value}")

            if not bit_read_error:
                try:
                    modbus_response = self.master.execute(self.slave,
                                                          getattr(cst, function_code),
                                                          starting_address,
                                                          output_value=modbus_value,
                                                          quantity_of_x=length,
                                                          data_format=data_fmt)

                    response = list(modbus_response)
                except Exception as ex:
                    if self.debugMode:
                        self.logger.info(f"Modbus command({command}) write error={ex})")
                    response = []
                    units = "error"
            else:
                if self.debugMode:
                    self.logger.info(f"Modbus command({command}) bit read/modify/write error)")
                response = []
                units = "error"

            if self.debugMode:
                self.logger.info(f"modbus reply = {response}")
            # if the write is successful the result is:
            # [ (starting address), (number of registers written) ]
            if len(response) == 2:
                if response[0] == starting_address:
                    if response[1] == length:
                        results = {"command": command, "values": values, "units": units}
            else:
                results = {"command": command, "values": [], "units": units}
        except KeyError:
            units = "Unknown"
            results = {"command": command, "values": [], "units": units}

        return results

    # get the value of an individual bit in a value
    def get_bit(self, value, bit_position):
        """ Gets a bit in the data 'value' at position index specified by 'bit'
        https://realpython.com/python-bitwise-operators/#getting-a-bit"""
        return (value >> bit_position) & 1  # If the bit value at the position is 1 this returns 1.

    # set an individual bit on a value
    def set_bit(self, value, bit):
        """ Sets a bit in the data 'value' at position index specified by 'bit' """
        return value | (1 << bit)

    # clear an individual bit on a value
    def clr_bit(self, value, bit):
        """ Clears a bit in the data 'value' at position index specified by 'bit' """
        return value & ~(1 << bit)

    def run(self):
        self.logger.info(f"Modbus slave {self.device_name} thread started")
        self.plug = self.deviceport.setupPlug(self)
        self.poller = zmq.Poller()
        self.poller.register(self.plug, zmq.POLLIN)

        if self.ModbusConfigError:
            self.logger.info(f"Modbus slave {self.get_device_name()} thread exited due to configuration errors!")
            return

        while self.active.is_set():
            s = dict(self.poller.poll(1000.0))
            if not self.dormant.is_set():
                if len(s) > 0:
                    msg = self.plug.recv_pyobj()
                    results = []
                    ansmsg = msg_schema.DeviceAns.new_message()
                    ansmsg.error = 0
                    for idx, p in enumerate(msg.params):
                        cmd = f"{p}_{msg.operation}"
                        if self.debugMode:
                            self.logger.info(f"ModbusSlaveThread {self.get_device_name()} message request={cmd}")
                        if msg.operation == "READ":
                            response = self.read_modbus(cmd)
                        elif msg.operation == "WRITE":
                            if len(msg.params) == len(msg.values):
                                values = [msg.values[idx], ]
                            else:
                                values = None
                                self.logger.warn(
                                    f"ModbusSlaveThread {self.get_device_name()} block write not implemented={cmd}")
                            if values:
                                response = self.write_modbus(cmd, values)
                        else:
                            response = {}

                        if self.debugMode:
                            self.logger.info(f"ModbusSlaveThread {self.get_device_name()} results={response}")

                        results.append(response)

                        if len(response["values"]) == 0:
                            if response["units"] == "error":
                                ansmsg.error = ModbusSystem.Errors.CommError
                            else:
                                ansmsg.error = ModbusSystem.Errors.InvalidOperation
                            response["values"] = [ModbusSystem.DataRanges.MIN_FLT32]
                        else:
                            pass

                    vals = []
                    units = []
                    parms = []
                    for d in results:
                        vals.append(d["values"][0])
                        units.append(d["units"])
                        parms.append(d["command"])
                    if self.debugMode:
                        self.logger.info(f"{self.get_device_name()} vals={vals}")
                        self.logger.info(f"{self.get_device_name()} units={units}")
                        self.logger.info(f"{self.get_device_name()} parms={parms}")
                    ansmsg.values = list(vals)
                    ansmsg.units = list(units)
                    ansmsg.params = list(parms)
                    ansmsg.device = self.get_device_name()
                    ansmsg.operation = msg.operation
                    ansmsg.msgcounter = msg.msgcounter
                    self.plug.send_pyobj(ansmsg)
            else:
                self.logger.info(f"Device is dormant, ignoring commands!")

        self.logger.info(f"Modbus slave {self.get_device_name()} thread exited.")


if __name__ == '__main__':
    print("Hurray the imports work!")
