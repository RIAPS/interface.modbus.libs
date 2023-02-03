import logging
import threading


# Class derived from Thread to handle polling
# master : the modbus-tk object used for communincation
# params : dictionary of parameters to poll
# eventport : the inside port in riaps that receives the messages generated by the thread
# interval_ms : timing at which each parameter is polled
class ModbusPoller(threading.Thread):

    def __init__(self, dvcname, slaveid, master, params, eventport, interval_ms):
        """
        An instance of this class is started when a modbus device configuration file contains entries
        under the `poll` keyword.
        :param dvcname: name of modbus device
        :param slaveid:
        :param master: the modbus-tk object used for communincation
        :param params: dictionary of parameters to poll
        :param eventport: the inside port in riaps that receives the messages generated by the thread
        :param interval_ms: timing at which each parameter is polled
        """
        super().__init__()
        # threading.Thread.__init__(self)
        self.logger = logging.getLogger(__name__)
        self.params = params
        self.master = master
        self.device_name = dvcname
        self.eventport = eventport
        self.interval_ms = interval_ms
        self.slave = slaveid
        self.param_keys = self.params.keys()
        self.numparms = len(self.param_keys)

        self.plug = None
        self.active = threading.Event()
        self.active.set()

    def get_plug(self):
        return self.plug

    def deactivate(self):
        self.active.clear()

    # Do not allow the polling loop to send messages to the modbus device
    def disable_polling(self):
        self.logger.info("Disabling modbus polling for - %s" % self.device_name)
        self.poll_exit = True

    # Allow the polling loop to send messages to the modbus device
    def enable_polling(self):
        self.logger.info("Enabling modbus polling for - %s" % self.device_name)
        self.poll_exit = False

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

    def run(self):
        self.logger.info(f"Modbus poller {self.device_name} thread started...")
        self.plug = self.eventport.setupPlug(self)
        self.poller = zmq.Poller()
        self.poller.register(self.plug, zmq.POLLIN)

        while self.active.is_set():
            s = dict(self.poller.poll(self.interval_ms))
            if len(s) > 0:  # process messages from the main slave thread
                # currently any message sent to the poller terminates the thread
                # this can do other things if needed
                msg = self.plug.recv_pyobj()
                self.deactivate()
                break
            else:  # do polling
                start = dt.datetime.now()
                poll_error = 0
                for k in self.param_keys:
                    cmdlist = self.params[k]
                    function_code = getattr(cst, cmdlist[0])
                    starting_address = cmdlist[1]
                    length = cmdlist[2]
                    scale = cmdlist[3]
                    units = cmdlist[4]
                    data_fmt = cmdlist[5]
                    max_thr = cmdlist[6]
                    min_thr = cmdlist[7]

                    PostNewEvent = True

                    try:
                        # read the parameter from the Modbus device
                        response = list(self.master.execute(self.slave,
                                                            function_code,
                                                            starting_address,
                                                            quantity_of_x=length,
                                                            data_format=data_fmt))

                        if len(response) == 1:
                            response[0] = response[0] * scale
                            if max_thr != None and min_thr != None:
                                if max_thr >= response[0] and min_thr <= response[0]:
                                    PostNewEvent = False
                        else:
                            for idx, n in response:
                                response[idx] = float(n)
                    except Exception as ex:
                        poll_error = ModbusSystem.Errors.CommError
                        response = [ModbusSystem.DataRanges.MIN_FLT32, ]
                        units = "error"

                    stop = dt.datetime.now()
                    if PostNewEvent == True:
                        evtmsg = msg_struct.DeviceEvent.new_message()
                        evtmsg.event = "POLLED"
                        evtmsg.command = "READ"
                        evtmsg.names = list([k, ])
                        evtmsg.values = list(response)
                        evtmsg.units = list([units, ])
                        evtmsg.device = self.device_name
                        evtmsg.error = poll_error
                        evtmsg.et = (stop - start).total_seconds()
                        self.plug.send_pyobj(evtmsg)
        self.logger.info(f"Modbus slave poller for {self.device_name} exited.")