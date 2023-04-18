import logging
import threading
import zmq

from riaps.interfaces.modbus.ModbusInterface import ModbusInterface


class ModbusMaster(threading.Thread):
    def __init__(self, path_to_config_file, logger=None, command_port=None, event_port=None):
        super().__init__()

        local_logger = logging.getLogger(__name__)
        if local_logger.handlers:
            self.logger = local_logger
        elif logger:
            self.logger = logger
        else:
            self.logger = local_logger

        self.port_poller = zmq.Poller()
        self.command_port_plug = None
        self.event_port_plug = None
        if command_port:
            self.command_port_plug = command_port.setupPlug(self)
            self.port_poller.register(self.command_port_plug, zmq.POLLIN)
        if event_port:
            self.event_port_plug = event_port.setupPlug(self)
        #     self.port_poller.register(self.event_port_plug, zmq.POLLIN)

        self.modbus_interface = ModbusInterface(path_to_file=path_to_config_file, logger=self.logger)
        self.device_config = self.modbus_interface.device_config

        self.stop_polling = threading.Event()
        self.polling_thread = threading.Thread(target=self.poller)
        self.polling_thread.start()

    def run(self):
        if not self.command_port_plug:
            return

        while True:
            ports_with_events = dict(self.port_poller.poll(1000))
            if not ports_with_events:
                continue
            msg = self.command_port_plug.recv_pyobj()
            self.logger.info(f"ModbusMasterThread | run | receive message on command port: {msg}")

            # read message and read modbus
            operation = msg["operation"]
            parameters = msg["parameters"]
            values = msg["values"]
            modbus_response_values = {"device_name": msg["to_device"],
                                      "operation": operation,
                                      "parameters": parameters,
                                      "values": [],
                                      "return_status": [],
                                      "msgcounter": msg["msgcounter"]}
            for (parameter, value) in zip(parameters, values):
                if operation == "READ":
                    modbus_result = self.modbus_interface.read_modbus(parameter=parameter)
                    if not modbus_result:
                        self.logger.warn(f"ModbusMasterThread | run | READ | modbus is unresponsive")
                    modbus_response_values["values"].append(modbus_result["values"])
                    modbus_response_values["return_status"].append(modbus_result.get("errors", "OK"))
                    self.logger.info(f"ModbusMasterThread | run | operation: {operation} | result: {modbus_result}")
                elif operation == "WRITE":
                    modbus_result = self.modbus_interface.write_modbus(parameter=parameter,
                                                                       values=value)
                    if not modbus_result:
                        self.logger.warn(f"ModbusMasterThread | run | WRITE | modbus is unresponsive")
                    modbus_response_values["values"].append(modbus_result["values"])
                    modbus_response_values["return_status"].append(modbus_result.get("errors", "OK"))
                    self.logger.info(f"ModbusMasterThread | run | operation: {operation} | result: {modbus_result}")
                else:
                    # TODO: test this code.
                    #  also consider updating the other instances of this data structure
                    #  to use the return_status for the error messages instead of units or
                    #  whatever is being used currently.
                    modbus_result = {"device_name": msg["to_device"],
                                     "parameter": f"{parameter}",
                                     "operation": f"{operation}",
                                     "values": None,
                                     "units": None,
                                     "errors": f"{parameter}_{operation} is not defined"
                                     }
                    modbus_response_values["values"].append(modbus_result["values"])
                    modbus_response_values["return_status"].append(modbus_result.get("errors", "OK"))

            self.command_port_plug.send_pyobj(modbus_response_values)

    def poller(self) -> None:
        poll_interval = self.device_config.get("Poll_Interval_Seconds")
        parameters_to_poll = self.device_config.get("poll")

        if not parameters_to_poll:
            self.logger.warn("No parameters configured to poll")
            return

        self.logger.debug(f"parameters_to_poll: {parameters_to_poll}")
        while not self.stop_polling.wait(timeout=poll_interval):
            for parameter in parameters_to_poll:
                self.logger.debug(f"poll parameter: {parameter}")
                modbus_result = self.modbus_interface.read_modbus(parameter=parameter)
                if self.event_port_plug:
                    self.event_port_plug.send_pyobj(modbus_result)




