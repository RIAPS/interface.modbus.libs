import json
import multiprocessing
import watchdog
import watchdog.events
import watchdog.observers
import os
import pytest
import queue
import time

from riaps.ctrl.ctrl import Controller
from riaps.utils.config import Config

import example.simulator.tcpslave_sim as tcpslave_sim


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


@pytest.mark.skip
def test_sanity():
    assert True


class FileHandler(watchdog.events.FileSystemEventHandler):
    def __init__(self, event_q):
        self.event_q = event_q

    def on_any_event(self, event):
        pass
        # print(f"{event.event_type}, {event.src_path}")

    def on_modified(self, event):
        # print(f"on_modified: {event.src_path}")
        self.event_q.put(f"{event.src_path}")


def test_cli(tcp_slave):
    the_config = Config()
    c = Controller(port=8888, script="-")

    # event_q = multiprocessing.Queue
    event_q = queue.Queue()
    file_event_handler = FileHandler(event_q=event_q)
    observer = watchdog.observers.Observer()
    hardcoded_path = "/home/riaps/projects/RIAPS/riaps-pycom/src/scripts"
    observer.schedule(file_event_handler, path=hardcoded_path, recursive=False)
    observer.start()

    if True:
        required_clients = ['172.21.20.51']
        app_folder = "/home/riaps/projects/RIAPS/interface.modbus.libs/example/Minimal"
        c.setAppFolder(app_folder)
        app_name = c.compileApplication("MinimalModbusApp.riaps", app_folder)
        depl_file = "MinimalModbusApp.depl"
        also_app_name = c.compileDeployment(depl_file)

        # start
        # c.startRedis()
        c.startDht()
        c.startService()

        # wait for clients to be discovered
        known_clients = []
        while not set(required_clients).issubset(set(known_clients)):
            known_clients = c.getClients()
            print(f"known clients: {known_clients}")
            time.sleep(1)

        # load application
        app_loaded = c.loadByName(app_name)
        print(f"app loaded? {app_loaded}")
        # launch application
        print("launch app")
        is_app_launched = c.launchByName(app_name)
        # downloadApp (line 512). Does the 'I' mean 'installed'?
        # launchByName (line 746)
        print(f"app launched? {is_app_launched}")

        # TODO: get events from the queue.
        #  Include a timeout perhaps?
        #  open file and read new lines when there
        #  has been a change, and do any testing.

        files = {}
        active_senders = []
        not_done = False

        while not_done:
            event_source = event_q.get()
            if ".log" in event_source:
                print(f"Event source: {event_source}")
                file_name = os.path.basename(event_source)
                if file_name not in files:
                    file = open(event_source, "r")
                    files[file_name] = {"file": file,
                                        "peers": [],
                                        "peers_known": False}

                file_data = files[file_name]

                for line in file_data["file"]:
                    print(f"file: {file_name}, line: {line}")
                    parts = line.split("::")
                    # print(f"file: {file_name}, last part: {parts[-2]}")

                    if "peer" in line:
                        name = line.split(" ")[1]
                        file_data["peers"].append(name)
                        # if active_senders in file_data["peers"]:
                        #     print(f"RECEIVE ALL ACTIVE: TRUE")
                        # else:
                        #     print(f"RECEIVE ALL ACTIVE: FALSE")

                    # TODO: at some point make check that peers matches up with required clients

                    if "uuid" in line:
                        msg = json.loads(parts[-2])
                        sender = msg["uuid"]
                        active_senders.append(sender)

                    if "known_senders" in line:
                        try:
                            known_senders = json.loads(parts[-2])
                        except NameError as e:
                            print(f"Exception: {e}")
                        num_senders = len(known_senders["known_senders"])

                        if num_senders == 5:
                            file_data["peers_known"] = True

                            for f in files:
                                if files[f]["peers_known"]:
                                    done = True
                                else:
                                    break

        print(f"All nodes have all subscriptions active")

        manual_run = True
        if manual_run:
            done = input("Provide input when ready to stop")
        else:
            for i in range(20):
                print(f"App is running: {i}")
                time.sleep(1)

        # Halt application
        print("Halt app")
        is_app_halted = c.haltByName(app_name)
        # haltByName (line 799).
        print(f"app halted? {is_app_halted}")

        # Remove application
        print("remove app")
        c.removeAppByName(app_name)  # has no return value.
        # removeAppByName (line 914).
        print("app removed")

        # Stop controller
        print("Stop controller")
        c.stop()
        print("controller stopped")

        observer.stop()

        assert True
