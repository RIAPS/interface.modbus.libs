# riaps:keep_import:begin
from statistics import mode
from riaps.run.comp import Component
import riaps.interfaces.modbus.TerminalColors as tc
import spdlog
import capnp
import riaps.interfaces.modbus.device_capnp as msg_schema


# riaps:keep_import:end

class ModbusManager(Component):

# riaps:keep_constr:begin
    def __init__(self):
        super(ModbusManager, self).__init__()
        self.device_names = []
        self.num_devices = 0
        self.count = 0
        self.msgcnt = 1
        self.Connected = False
        self.params = {}
        self.access = "R"
        self.clear = False
# riaps:keep_constr:end

# riaps:keep_device_configured:begin
    def on_device_configured(self):
        msg = self.device_configured.recv_pyobj()
        (keys, dvcs) = msg
        self.device_names = keys
        self.devices = dvcs
        self.num_devices = len( self.device_names )

        for k in keys :
            self.params[k] = {}
            parms = list( self.devices[k][k].keys() )
            self.logger.info( f"{tc.Yellow}List of parms:{parms}{tc.RESET}" )
            for p in parms :
                item = self.devices[k][k][p]
                if isinstance( item, dict ) :
                    if "start" in item :
                        if "bit_position" in item :
                            is_bit = True
                        else:
                            is_bit = False

                        start = item["start"]
                        if str(p).find( "_WRITE" ) != -1 :
                            name = str(p).replace( "_WRITE", "" )
                            output = float( item["output_value"][0] )
                            acc = "W"
                        elif str(p).find( "_READ" ) != -1 :
                            name = str(p).replace( "_READ", "" )
                            acc = "R"
                            output = None
                        else:
                            name = p
                            acc = ""    
                            output = None

                        if not name in self.params[k] :
                            self.params[k][name] = {"access": acc, "address": start, "output" : output, "bitfield" : is_bit }
                        else:
                            astr = self.params[k][name]["access"]
                            astr = astr + acc
                            self.params[k][name]["access"] = astr
                            if output != None :
                                 self.params[k][name]["output"] = output


            self.logger.info( f"List of parameters for {tc.Green}{k}{tc.RESET}:" )        
            for p in self.params[k] :
                acc = self.params[k][p]["access"]
                self.logger.info( f"{tc.Yellow}{p}{tc.RESET} ({tc.Cyan}{acc}{tc.RESET})" )       
               
        self.logger.info( f"{tc.Purple}on_device_configured:{tc.RESET}{self.device_names}" )
# riaps:keep_device_configured:end

# riaps:keep_event_from_driver:begin
    def on_event_from_driver(self):
        # struct DeviceEvent {
        #     event @0: Text = "";
        #     command @1: Text = "";
        #     names @2: List(Text);
        #     values @3: List(Float64);
        #     units @4: List(Text) = ["None"];
        #     device @5: Text = "";
        #     error @6: Int16 = 0;
        #     et    @7: Float32 = 0.0;
        # }

        msg = self.event_from_driver.recv_pyobj()
        self.logger.info( f"{tc.Green}{msg.event}{tc.RESET} from {tc.Yellow}{msg.device}{tc.RESET}" )
        idx = 0 
        for p in msg.names :
            s = str(p)
            s = s.replace("_READ", "" )
            self.logger.info( f"{s}={msg.values[idx]} {msg.units[idx]}" )
            idx = idx + 1
# riaps:keep_event_from_driver:end

# riaps:keep_periodic:begin
    def on_periodic(self):
        now = self.periodic.recv_pyobj()

        # verify connected before sending messages
        if not self.Connected:
            try:
                self.Connected = bool( self.driver_qa.connected() )
                self.logger.info( f"on_periodic:Connected={tc.Red}{self.Connected}{tc.RESET}" )
            except AttributeError:
                self.Connected = True
                self.logger.info( f"{tc.Red}on_periodic:driver_qa.connected() is invalid! Connected={self.Connected}{tc.RESET}" )            


        if self.Connected :
            if self.num_devices > 0 :
                # struct DeviceQry {
                #     device @0: Text = "";
                #     operation @1: Text = "";
                #     params @2: List(Text);
                #     values @3: List(Float64) = [0];
                #     timestamp @4: Float64;
                #     msgcounter @5: Int64;
                # }
                
                dvc = self.device_names[self.count]
                for p in self.params[dvc] :
                    msg = msg_schema.DeviceQry.new_message()
                    msg.device = dvc
                    astr = str( self.params[dvc][p]["access"] )
                    if self.access == "R" :
                        if astr.find( "R" ) != -1 :
                            msg.operation = "READ"
                            msg.params = [ p ]
                            msg.values = [ 0 ]
                            msg.msgcounter = self.msgcnt
                            self.msgcnt = self.msgcnt + 1
                            self.driver_qa.send_pyobj( msg )
                            self.logger.info( f"{tc.Purple}Read{tc.RESET} of {msg.params} on {tc.Yellow}{msg.device}{tc.RESET}: Message ID={msg.msgcounter}" )
                        else:
                            pass
                    elif self.access == "W" :
                        if astr.find( "W" ) != -1 :
                            msg.operation = "WRITE"
                            msg.params = [ p ]
                            if not self.clear :
                                msg.values = [ self.params[dvc][p]["output"] ]
                            else:
                                msg.values = [ 0.0 ]
                            msg.msgcounter = self.msgcnt
                            self.msgcnt = self.msgcnt + 1
                            self.driver_qa.send_pyobj( msg )
                            self.logger.info( f"{tc.Purple}Write{tc.RESET} {p}={msg.values} on {tc.Yellow}{msg.device}{tc.RESET}: Message ID={msg.msgcounter}" )
                        else:
                            pass

                self.count = self.count + 1
                if self.count >= self.num_devices :
                    self.count = 0
                    if self.access == "W" :
                        self.access = "R"
                    else:
                        self.access = "W"
            else:
                self.logger.info( f"{tc.Yellow}on_periodic:No devices configured!{tc.RESET}" )    
        else:
            self.logger.info( f"{tc.Red}on_periodic:driver_qa is not connected!{tc.RESET}" )
# riaps:keep_periodic:end

# riaps:keep_driver_qa:begin
    def on_driver_qa(self):
        # struct DeviceAns {
        #     device @0: Text = "";
        #     reply @1: Text= "";
        #     operation @3: Text = "";
        #     params @2: List(Text);
        #     values @4: List(Float64)=[0.0];
        #     states @5: List(Bool)=[false];
        #     units @6: List(Text);
        #     error @7: Int16 = 0;
        #     et    @8: Float32 = 0.0;
        #     msgcounter @9: Int64;
        # }
        msg = self.driver_qa.recv_pyobj()

        self.logger.info( f"{tc.Cyan}Answer{tc.RESET} from {tc.Yellow}{msg.device}{tc.RESET}: Message ID={msg.msgcounter}" )
        idx = 0 
        for p in msg.params :
            s = str(p)
            s = s.replace("_READ", "" )
            s = s.replace("_WRITE", "" ) 
            self.logger.info( f"{s}={msg.values[idx]} {msg.units[idx]}" )
            idx = idx + 1

        
# riaps:keep_driver_qa:end

# riaps:keep_impl:begin
    def handleActivate(self):
        self.periodic.setPeriod( 5.0 )
# riaps:keep_impl:end