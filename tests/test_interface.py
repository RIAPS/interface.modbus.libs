import logging
import multiprocessing
import pytest
import random
import time


import riaps.interfaces.modbus.ModbusInterface as ModbusInterface
import example.simulator.tcpslave_sim as tcpslave_sim

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


@pytest.fixture(scope="session")
def modbus_interface():
    path_to_file = "/home/riaps/projects/RIAPS/interface.modbus.libs/example/Minimal/cfg/Test_NEC-BESS1.yaml"
    return ModbusInterface.ModbusInterface(path_to_file)


@pytest.fixture(scope="session")
def opal_modbus_gen_interface():
    path_to_file = "/home/riaps/projects/RIAPS/interface.modbus.libs/example/Minimal/cfg/GEN1-Banshee.yaml"
    return ModbusInterface.ModbusInterface(path_to_file)


@pytest.fixture(scope="session")
def opal_modbus_relay_interface():
    path_to_file = "/home/riaps/projects/RIAPS/interface.modbus.libs/example/Minimal/cfg/F1PCC.yaml"
    return ModbusInterface.ModbusInterface(path_to_file, logger=logger)


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
    value = [11.0]
    result = modbus_interface.write_modbus(parameter="ReferenceInput",
                                           values=value)
    result = modbus_interface.read_modbus(parameter="ReferenceInput")
    print(f"input: {value} output: {result['values']}")
    assert result['values'] == value
    tcp_slave.stop()


@pytest.mark.skip
def test_slave_failure2(modbus_interface, tcp_slave):
    """
    This test highligts  a problem with the modbus_tk implementation.
    It uses recv without knowing if anything is on the socket and has no error handling.
    Unfortunately it is non-deterministic, so it sometimes fails to fail.
    https://github.com/ljean/modbus-tk/blob/6e22b6ba68fc2f0e15c598b50b55d667a6a8e7f2/modbus_tk/modbus_tcp.py#L216
    https://stackoverflow.com/questions/2719017/how-to-set-timeout-on-pythons-socket-recv-method
    """
    import socket
    with pytest.raises(socket.timeout) as e_info:
        result = modbus_interface.read_modbus(parameter="ReferenceInput")
        print(e_info)


def test_opal_read(opal_modbus_gen_interface):
    # values = [1]
    # result = opal_modbus_gen_interface.write_modbus(parameter="CONTROL",
    #                                                 values=values)
    # print(f"CONTROL write output: {result['values']}")
    #
    # time.sleep(5)

    # READ
    parameters_to_poll = ["FREQ", "VA_RMS", "P", "Q", "VREF", "WREF"]
    for parameter in parameters_to_poll:
        print(f"poll parameter: {parameter}")
        modbus_result = opal_modbus_gen_interface.read_modbus(parameter=parameter)
        print(f"{parameter} output: {modbus_result['values']}")


def test_opal_bit_read(opal_modbus_relay_interface):
    # WRITE
    values = [2]  # Close relay
    result = opal_modbus_relay_interface.write_modbus(parameter="LOGIC",
                                                      values=values)

    time.sleep(5)
    # READ
    status = opal_modbus_relay_interface.read_modbus(parameter="STATUS")
    connected = opal_modbus_relay_interface.read_modbus(parameter="IS_GRID_CONNECTED_BIT")
    tripped = opal_modbus_relay_interface.read_modbus(parameter="IS_TRIPPED_BIT")
    fault = opal_modbus_relay_interface.read_modbus(parameter="HAVE_INTERNAL_FAULT_BIT")

    print(status)
    print(connected)
    print(tripped)
    print(fault)

    # WRITE
    values = [1]  # Open relay
    result = opal_modbus_relay_interface.write_modbus(parameter="LOGIC",
                                                      values=values)
    time.sleep(5)
    # READ
    status = opal_modbus_relay_interface.read_modbus(parameter="STATUS")
    connected = opal_modbus_relay_interface.read_modbus(parameter="IS_GRID_CONNECTED_BIT")
    tripped = opal_modbus_relay_interface.read_modbus(parameter="IS_TRIPPED_BIT")
    fault = opal_modbus_relay_interface.read_modbus(parameter="HAVE_INTERNAL_FAULT_BIT")
    print(status)
    print(connected)
    print(tripped)
    print(fault)

    # CHECK
    # print(f"input: {values} output: {result['values']}")
    # assert result['values'] == values
