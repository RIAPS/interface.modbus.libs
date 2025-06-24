import pathlib
import pytest
import socket
import time
import riaps.interfaces.modbus.ModbusInterface as ModbusInterface
import riaps.interfaces.modbus.slave as slave


@pytest.fixture(scope="session")
def device_sim():
    here = pathlib.Path(__file__).parent
    path_to_file = here / "cfg.yaml"
    server = slave.Slave()
    device_config = server.load_cfg(path_to_file)
    slave_id = device_config["DEVICE"]["SlaveID"]

    server.setup_from_cfg(device_config)
    print(
        f"sever.get_values(): {server.slaves[slave_id].get_values('hr0-10000', 8501)}"
    )
    server.start()
    print("Server started")

    # Wait for the server to be ready by polling the port
    is_ready = False
    retries = 10
    addr = device_config["DEVICE"]["TCP"]["Address"]
    port = device_config["DEVICE"]["TCP"]["Port"]
    while not is_ready and retries > 0:
        try:
            with socket.create_connection((addr, port), timeout=0.1):
                is_ready = True
                print(f"Server is ready on {addr}:{port}")
        except (socket.timeout, ConnectionRefusedError):
            retries -= 1
            time.sleep(0.2)

    if not is_ready:
        pytest.fail(f"Server did not start in time on {addr}:{port}")

    yield server
    server.stop()


@pytest.fixture(scope="function")
def modbus_interface(testslogger):

    here = pathlib.Path(__file__).parent
    path_to_file = here / "registers.yaml"
    return ModbusInterface.ModbusInterface(path_to_file, logger=testslogger)


def test_sim(device_sim, modbus_interface):
    params = ["CMD"]
    for param in params:
        result = modbus_interface.read_modbus(parameter=param)
        print(f"param: {param} value: {result['values']}")


# def test_read_write(modbus_interface):
#     print("test_read_write")
#     # Read current value
#     result = modbus_interface.read_modbus(parameter="ExampleHolding0")
#     print(f"initial register value: {result['values']}")

#     # Write new value
#     value = [3.145]
#     result = modbus_interface.write_modbus(parameter="ExampleHolding1", values=value)

#     # Read new value
#     result = modbus_interface.read_modbus(parameter="ExampleHolding1")
#     print(f"input: {value} output: {result['values']}")

#     # Write new value
#     value = [1_000_000_000]
#     result = modbus_interface.write_modbus(parameter="ExampleHolding5", values=value)
#     print(f"Result of writing: {result}")

#     # # Read new value
#     result = modbus_interface.read_modbus(parameter="ExampleHolding5")
#     print(f"input: {value} output: {result['values']}")

#     # Ensure that new values matches value set
#     # assert result["values"] == [v * 10 for v in value]


def test_struct():
    import struct

    packed = struct.pack(">i", 12345678)
    print(packed)

    unpacked = struct.unpack(">i", packed)
    print(unpacked)

    packed = struct.pack(">f", 3.14)
    print(packed)

    unpacked = struct.unpack(">f", packed)
    print(unpacked)
