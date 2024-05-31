import pytest
import riaps.interfaces.modbus.ModbusInterface as ModbusInterface


@pytest.fixture(scope="function")
def modbus_interface(testslogger):
    path_to_file = (
        "/home/riaps/projects/RIAPS/interface.modbus.libs/example/devices/example.yaml"
    )
    return ModbusInterface.ModbusInterface(path_to_file, logger=testslogger)


def test_read_write(modbus_interface):
    print("test_read_write")
    # Read current value
    result = modbus_interface.read_modbus(parameter="ExampleHolding0")
    print(f"initial register value: {result['values']}")

    # Write new value
    value = [3.145]
    result = modbus_interface.write_modbus(parameter="ExampleHolding1", values=value)

    # Read new value
    result = modbus_interface.read_modbus(parameter="ExampleHolding1")
    print(f"input: {value} output: {result['values']}")

    # Write new value
    value = [1_000_000_000]
    result = modbus_interface.write_modbus(parameter="ExampleHolding5", values=value)
    print(f"Result of writing: {result}")

    # # Read new value
    result = modbus_interface.read_modbus(parameter="ExampleHolding5")
    print(f"input: {value} output: {result['values']}")

    # Ensure that new values matches value set
    # assert result["values"] == [v * 10 for v in value]


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
