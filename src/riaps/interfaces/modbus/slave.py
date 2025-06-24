from modbus_tk import modbus_tcp, defines
import yaml


class Slave:
    def __init__(self):
        self.slaves = {}

    def load_cfg(self, config_path):
        try:
            with open(config_path, "r") as f:
                device_config = yaml.safe_load(f)
                return device_config
        except FileNotFoundError:
            print(f"Error: Configuration file not found at {config_path}")
            exit(1)
        except yaml.YAMLError as e:
            print(f"Error parsing YAML file: {e}")
            exit(1)

    def setup_from_cfg(self, cfg):
        port = cfg["DEVICE"]["TCP"]["Port"]
        address = cfg["DEVICE"]["TCP"]["Address"]
        self.setup_server(port, address)

        slave_id = cfg["DEVICE"]["SlaveID"]
        self.add_slave(slave_id)

        for block_name in cfg["BLOCKS"]:
            blk = cfg["BLOCKS"][block_name]
            block_type = blk["type"]
            starting_address = blk["starting_address"]
            size = blk["num_registers"]
            self.add_block(slave_id, block_name, block_type, starting_address, size)

        reg_cfg = cfg["REGISTERS"]
        self.init_values(slave_id, reg_cfg)

    def setup_server(self, port, address):
        self.server = modbus_tcp.TcpServer(port, address)

    def start(self):
        self.server.start()

    def stop(self):
        self.server.stop()

    def add_slave(self, slave_id):
        self.slaves[slave_id] = self.server.add_slave(slave_id)

    def get_slave(self, slave_id):
        return self.server.get_slave(slave_id)

    def add_block(self, slave_id, block_name, block_type, starting_address, size):
        slave = self.slaves[slave_id]
        slave.add_block(
            block_name=block_name,
            block_type=getattr(defines, block_type),
            starting_address=starting_address,
            size=size,
        )

    def init_values(self, slave_id, reg_cfg):
        slave = self.slaves[slave_id]

        for parameter in reg_cfg:
            block_name = reg_cfg[parameter]["block_name"]
            reg_address = reg_cfg[parameter]["starting_address"]
            value = reg_cfg[parameter]["initial_value"]

            slave.set_values(block_name=block_name, address=reg_address, values=value)

    def format_value(data_format, scale_factor, value):
        pass


if __name__ == "__main__":
    device_config = {
        "DEVICE": {
            "SlaveID": 0,
            "Protocol": "TCP",
            "TCP": {"Address": "127.0.0.1", "Port": 5020},
        },
        "BLOCKS": {
            "c0-100": {"type": "COILS", "starting_address": 0, "num_registers": 100},
            "di0-100": {
                "type": "DISCRETE_INPUTS",
                "starting_address": 0,
                "num_registers": 100,
            },
            "hr0-10000": {
                "type": "HOLDING_REGISTERS",
                "starting_address": 0,
                "num_registers": 10000,
            },
            "ai0-100": {
                "type": "ANALOG_INPUTS",
                "starting_address": 0,
                "num_registers": 100,
            },
        },
        "REGISTERS": {
            "CMD": {
                "block_name": "hr0-10000",
                "starting_address": 8501,
                "initial_value": 8,
                "data_format": ">H",
                "scale_factor": 1,
            },
            "LFRD": {
                "block_name": "hr0-10000",
                "starting_address": 8602,
                "initial_value": 0,
                "data_format": ">h",
                "scale_factor": 1,
            },
            "RFRD": {
                "block_name": "hr0-10000",
                "starting_address": 8604,
                "initial_value": 0,
                "data_format": ">h",
                "scale_factor": 1,
            },
        },
    }

    server = Slave()
    server.setup_from_cfg(device_config)
    server.start()
    input("Press Enter to stop the server...")
    server.stop()


#  3 CMD	DrivecomCmdReg	16#2135 = 8501	16#2037/2	16#8B/01/66 = 139/01/102		Control parameters	R/W	WORD (BitString16)	-			[Cmd value] (CMD)	[COMMUNICATION MAP] (CMM)
#  5 LFRD	Speed setpoint	16#219A = 8602	16#2038/3	16#8C/01/03 = 140/01/03		Setpoint parameters	R/W	INT (Signed16)	1 rpm	0 rpm	-32767 rpm ... 32767 rpm
# 20 RFRD	Output velocity	16#219C = 8604	16#2038/5	16#8C/01/05 = 140/01/05		Actual values parameters	R	INT (Signed16)	1 rpm		-32767 rpm ... 32767 rpm
