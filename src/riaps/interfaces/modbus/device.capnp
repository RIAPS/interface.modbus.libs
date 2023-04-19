@0xb98379e22fbae393;

using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("testmodbusopal::messages");

# riaps:keep_deviceevent:begin
struct DeviceEvent {
    event @0: Text = "";
    command @1: Text = "";
    names @2: List(Text);
    values @3: List(Float64);
    units @4: List(Text) = ["None"];
    device @5: Text = "";
    error @6: Int16 = 0;
    et    @7: Float32 = 0.0;
}
# riaps:keep_deviceevent:end

# riaps:keep_deviceans:begin
struct DeviceAns {
    device @0: Text = "";
    reply @1: Text= "";
    operation @3: Text = "";
    params @2: List(Text);
    values @4: List(List(Float64))=[[0.0]];
    states @5: List(Bool)=[false];
    units @6: List(Text);
    returnStatus @7: List(Text) = [];
    et    @8: Float32 = 0.0;
    msgcounter @9: Int64;
}
# riaps:keep_deviceans:end

# riaps:keep_deviceqry:begin
struct DeviceQry {
    device @0: Text = "";
    operation @1: Text = "";
    params @2: List(Text);
    values @3: List(List(Int64))=[[0]];
    timestamp @4: Float64;
    msgcounter @5: Int64;
}
# riaps:keep_deviceqry:end
