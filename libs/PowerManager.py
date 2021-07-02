# riaps:keep_import:begin
from riaps.run.comp import Component
import spdlog
import capnp
import device_capnp
# riaps:keep_import:end


    # riaps:keep_constr:begin
class PowerManager(Component):
    def __init__(self, config):
        super(PowerManager, self).__init__()
        self.logger.info("setup PowerManager")
    # riaps:keep_constr:end

    # riaps:keep_local_event_port:begin
    def on_local_event_port(self):
        evt_bytes = self.local_event_port.recv()
        self.event_port.send(evt_bytes)
    # riaps:keep_local_event_port:begin

    # riaps:keep_device_port:begin
    def on_device_port(self):
        bytes = self.device_port.recv()
        self.control_port.send(bytes)
    # riaps:keep_device_port:end

    # riaps:keep_control_port:begin
    def on_control_port(self):
        bytes = self.control_port.recv()
        self.device_port.send(bytes)
    # riaps:keep_control_port:begin

    def on_poller(self):
        pass

    # riaps:keep_impl:begin
    # riaps:keep_impl:end
