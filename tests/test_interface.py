import multiprocessing
import random
import time

import pytest

import riaps.interfaces.modbus.ModbusInterface as ModbusInterface
import example.simulator.tcpslave_sim as tcpslave_sim


@pytest.fixture(scope="session")
def modbus_interface():
    path_to_file = "/home/riaps/projects/RIAPS/interface.modbus.libs/example/Minimal/cfg/Test_NEC-BESS1.yaml"
    return ModbusInterface.ModbusInterface(path_to_file)


@pytest.fixture(scope="session")
def tcp_slave():
    modbus_config_file_path = "/home/riaps/projects/RIAPS/interface.modbus.libs/example/simulator/modbus_cfg.yaml"
    device_config_file_path = "/home/riaps/projects/RIAPS/interface.modbus.libs/example/simulator/device_cfg.yaml"
    server = tcpslave_sim.main(port=5501,
                               address="172.21.20.70",
                               modbus_config_file_path=modbus_config_file_path,
                               device_config_file_path=device_config_file_path)
    server.start()
    time.sleep(0.1)
    yield server


def test_device_config_failure():
    path_to_file = "does_not_exist.yaml"
    with pytest.raises(FileNotFoundError) as e_info:
        ModbusInterface.ModbusInterface(path_to_file)
        print(e_info)


def test_create_interface(modbus_interface):
    rc = modbus_interface.config_validation_receipt
    assert rc["return_code"] == 0


def test_slave_failure(modbus_interface):
    result = modbus_interface.read_modbus(parameter="ReferenceInput")
    print(f"output: {result}")


def test_create_slave(tcp_slave):
    assert tcp_slave._go.isSet(), "Slave not created correctly"


def test_write_read(modbus_interface, tcp_slave):
    # value = [random.uniform(0, 100)]
    value = [11.315823554992676]
    result = modbus_interface.write_modbus(parameter="ReferenceInput",
                                           values=value)
    result = modbus_interface.read_modbus(parameter="ReferenceInput")
    print(f"input: {value} output: {result['values']}")
    assert result['values'] == value


def test_slave_failure2(modbus_interface, tcp_slave):
    """
    This test highligts  a problem with the modbus_tk implementation.
    It uses recv without knowing if anything is on the socket and has no error handling.
    https://github.com/ljean/modbus-tk/blob/6e22b6ba68fc2f0e15c598b50b55d667a6a8e7f2/modbus_tk/modbus_tcp.py#L216
    https://stackoverflow.com/questions/2719017/how-to-set-timeout-on-pythons-socket-recv-method
    """
    import socket
    tcp_slave.stop()
    with pytest.raises(socket.timeout) as e_info:
        result = modbus_interface.read_modbus(parameter="ReferenceInput")
        print(e_info)
