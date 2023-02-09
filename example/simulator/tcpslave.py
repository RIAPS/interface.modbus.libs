#!/usr/bin/env python
# -*- coding: utf_8 -*-
"""
Requires Modbus-tk 

This slave implements the 4 main memory blocks of a Modbus device.

Creates a local master to allow active update of some modbus parameters as needed 

"""

from ctypes.wintypes import BYTE, INT
import modbus_tk.defines as cst
from modbus_tk import modbus_tcp
from modbus_tk import modbus_rtu
import time
import argparse
import struct
import yaml
import os
import platform
import threading
import time
from random import random
import serial
import Terminal as tc

print(f"Platform is {tc.LightRed}{platform.system()}{tc.RESET}")


class MemoryBlocks:
    Coils = 0
    DiscreteInputs = 1
    AnalogInputs = 3
    HoldingRegisters = 4


class Parameter:
    def __init__(self):
        self.Name = ''
        self.Start = 0
        self.Bytes = 1
        self.BlockId = 4
        self.Type = ''
        self.Order = 'BE'
        self.Value = 0
        self.Units = []


def main():
    last_holding = []
    paramList = []
    parser = argparse.ArgumentParser()
    parser.add_argument('--address', required=False, help="IP Address. Default:127.0.0.1", default="127.0.0.1")
    parser.add_argument('--port', required=False, help="Modbus TCP Port (1-65535). Default:501", default=501)
    parser.add_argument('--name', required=False, default="Modbus-Slave",
                        help="Modbus slave name shown in terminal title bar. Default:Modbus-Slave")
    parser.add_argument('--config', required=False, default="config.yaml",
                        help="Default configuration file:config.yaml")
    parser.add_argument('--blocksize', required=False, default=10000, type=int,
                        help="Modbus memory size. Default:10000")

    if platform.system().upper() == 'WINDOWS':
        parser.add_argument('--commsettings', required=False,
                            help="\'Port:Baud:Databits:Parity:Stopbits:XonXoff\' Example: \'COM1:57600:8:N:1:0\'")
    elif platform.system().upper() == 'LINUX':
        parser.add_argument('--commsettings', required=False,
                            help="\'Port:Baud:Databits:Parity:Stopbits:XonXoff\' Example: \'ttys1:57600:8:N:1:0\'")

    args = parser.parse_args()

    if args.commsettings is None:
        is_tcp_slave = True
        new_name = f"{args.name}->{args.address}:{args.port}"
        print("TCP Server={0}:{1} Name={2}".format(args.address, args.port, args.name))
    else:
        is_tcp_slave = False
        strs = args.commsettings.split(":", 5)
        # COM1:57600:8:N:1:0
        if len(strs) < 6:
            print("Bad communication setting, cannot continue!")
            print(strs)
            input()
            exit()
        else:
            port = strs[0]
            baudrate = int(strs[1])
            bytesize = int(strs[2])
            parity = strs[3]
            stopbits = int(strs[4])
            xonxoff = int(strs[5])
            new_name = f"{args.name}->{args.commsettings}"
            print(f"RTU Server={port}:{baudrate}:{bytesize}:{parity}:{stopbits}:{xonxoff} Name={args.name}")

    print(f"Configuration file: {args.config}")

    print(f'\033]2;{new_name}\a')

    print(f"Memory block size: {args.blocksize} words")

    active = threading.Event()

    with open(args.config) as f:
        data = yaml.safe_load(f)

    parms = data.keys()

    next_address = 0
    """ setup the parameters and calculate addresses if needed """
    for p in parms:
        newparm = Parameter()
        newparm.Name = data[p]['Name']
        newparm.Start = int(data[p]['Start'])
        if newparm.Start == -1:
            newparm.Start = next_address

        newparm.Bytes = int(data[p]['Bytes'])
        newparm.BlockId = int(data[p]['BlockId'])
        newparm.Type = data[p]['Type']
        newparm.Order = data[p]['Order']
        newparm.Value = data[p]['Value']
        newparm.Units = data[p]['Units']
        next_address = newparm.Start + int(newparm.Bytes / 2)
        paramList.append(newparm)

    slave_id = 1
    try:
        # Create the server
        if is_tcp_slave:
            server = modbus_tcp.TcpServer(int(args.port), args.address)
        else:
            server = modbus_rtu.RtuServer(serial.Serial(port=port,
                                                        baudrate=baudrate,
                                                        bytesize=bytesize,
                                                        parity=parity,
                                                        stopbits=stopbits,
                                                        xonxoff=xonxoff))

        server.start()
        """ update this to allow graceful exit """
        print("running... Crtl-C to quit the server")

        print(f'Creating slave with  ID={slave_id}')
        slave_1 = server.add_slave(slave_id)

        print(f'Adding memory COILS block {cst.COILS} with size of {args.blocksize}')
        slave_1.add_block(str(cst.COILS), cst.COILS, 0, args.blocksize)  # boolean

        print(f'Adding memory DISCRETE_INPUTS block {cst.DISCRETE_INPUTS} with size of {args.blocksize}')
        slave_1.add_block(str(cst.DISCRETE_INPUTS), cst.DISCRETE_INPUTS, 0, args.blocksize)  # boolean

        print(f'Adding memory HOLDING_REGISTERS block {cst.HOLDING_REGISTERS} with size of {args.blocksize}')
        slave_1.add_block(str(cst.HOLDING_REGISTERS), cst.HOLDING_REGISTERS, 0, args.blocksize)  # unsigned UInt16

        print(f'Adding memory ANALOG_INPUTS block {cst.ANALOG_INPUTS} with size of {args.blocksize}')
        slave_1.add_block(str(cst.ANALOG_INPUTS), cst.ANALOG_INPUTS, 0, args.blocksize)  # unsigned UInt16

        modelinfo = args.name
        # slave_info = bytearray( modelinfo, 'ascii' )     
        # print(f'{tc.LightRed}Setting Device Info:Length={len(slave_info)},Data={slave_info}{tc.RESET}' ) 
        # slave_1.set_values( str( cst.ANALOG_INPUTS ), 4000, slave_info )

        # print( f'Initializing  float( Memory Block={1} ) : {pm.Name:30}({pm.Start:0>5}) to {tc.Orange}{pm.Value:12}{tc.RESET} ({msb:04x}{lsb:04x})' )
        print(f' ')
        Yellow = "\033[93m"
        Cyan = "\033[96m"
        print(
            f'{Yellow}Initialization info                     : {"Variable Name":30}{"Address":<14}{"Order":<8}{"Value":<10}{"Raw data":<10}{tc.RESET}')
        try:
            for pm in paramList:
                if pm.Type.upper() == 'FLOAT':
                    if pm.Order.upper() == 'BE':
                        float_frame = struct.pack('>f', pm.Value)
                        integer_data = struct.unpack('>HH', float_frame)
                    else:
                        float_frame = struct.pack('<f', pm.Value)
                        integer_data = struct.unpack('<HH', float_frame)
                    msb = integer_data[0]
                    lsb = integer_data[1]
                    slave_1.set_values(str(pm.BlockId), pm.Start, integer_data)
                elif pm.Type.upper() == 'WORD':
                    if pm.Order.upper() == 'BE':
                        word_frame = struct.pack('>I', pm.Value)
                        integer_data = struct.unpack('>HH', word_frame)
                    else:
                        word_frame = struct.pack('<I', pm.Value)
                        integer_data = struct.unpack('<HH', word_frame)
                    msb = integer_data[0]
                    lsb = integer_data[1]
                    print(
                        f'Initializing {"UInt32":<8}( Memory Block={pm.BlockId} ) : {Cyan}{pm.Name:30}{tc.RESET}({pm.Start:0>5}) {pm.Order:>10} {tc.Orange}{pm.Value:12}{tc.RESET} ({msb:04x}{lsb:04x})')
                    slave_1.set_values(str(pm.BlockId), pm.Start, integer_data)
                elif pm.Type.upper() == 'INT':
                    if pm.Value < 0:
                        displayvalue = pm.Value
                        pm.Value = 2 ** 16 + pm.Value
                    elif pm.Value >= 2 ** 15:
                        displayvalue = -(2 ** 16 - pm.Value)
                    else:
                        displayvalue = pm.Value

                    if pm.Order.upper() == "BE":
                        newdata = int(0)
                        msb = int(pm.Value / 256)
                        lsb = int(pm.Value - (msb * 256))
                        newdata = int(msb * 256 + lsb)
                    else:
                        newdata = int(0)
                        lsb = int(pm.Value / 256)
                        msb = int(pm.Value - (lsb * 256))
                        newdata = int(msb * 256 + lsb)
                    print(
                        f'Initializing {"Int16":<8}( Memory Block={pm.BlockId} ) : {Cyan}{pm.Name:30}{tc.RESET}({pm.Start:0>5}) {pm.Order:>10} {tc.Orange}{displayvalue:12}{tc.RESET} ({msb:02x}{lsb:02x})')
                    slave_1.set_values(str(pm.BlockId), pm.Start, [newdata])
                elif pm.Type.upper() == 'UINT':
                    if pm.Value >= 0:
                        displayvalue = pm.Value
                    elif pm.Value < 0:
                        displayvalue = 2 ** 16 + pm.Value
                        pm.Value = int(displayvalue)

                    if pm.Order.upper() == "BE":
                        newdata = int(0)
                        msb = int(pm.Value / 256)
                        lsb = int(pm.Value - (msb * 256))
                        newdata = int(msb * 256 + lsb)
                    else:
                        newdata = int(0)
                        lsb = int(pm.Value / 256)
                        msb = int(pm.Value - (lsb * 256))
                        newdata = int(msb * 256 + lsb)
                    print(
                        f'Initializing {"UInt16":<8}( Memory Block={pm.BlockId} ) : {Cyan}{pm.Name:30}{tc.RESET}({pm.Start:0>5}) {pm.Order:>10} {tc.Orange}{displayvalue:12}{tc.RESET} ({msb:02x}{lsb:02x})')
                    slave_1.set_values(str(pm.BlockId), pm.Start, [newdata])

                elif pm.Type.upper() == 'DWORD':
                    print('Type specifier [{0}] not implemented!'.format(pm.Type))
                else:
                    print('Unknown type specifier [{0}]!'.format(pm.Type))
        except Exception as ex:
            print('Parameter initialization exception {0}!'.format(ex))
            active.set()

        while not active.wait(timeout=0.5):
            """ provide active parameter update here if required """
            """ otherwise the values are all static and set by the configuration file """
            # simulate( slave_1, paramList, 'IA_PEAK' )

            # list any values in the holding register bank that are modified
            # holding_memory = slave_1.get_values( str(cst.HOLDING_REGISTERS), 0, block_size-1 )
            # if holding_memory != last_holding :
            #   print( list( set( holding_memory) - set( last_holding  ) ) ) 
            # last_holding = holding_memory

    finally:
        server.stop()


def simulate(slv, list_of_params, parmName, max=100, min=0):
    for pm in list_of_params:
        if pm.Name == parmName:
            response = slv.get_values(str(pm.BlockId), pm.Start)
            value = int(response[0])
            value += 1
            if value > max:
                value = min
            slv.set_values(str(pm.BlockId), pm.Start, value)
            break


if __name__ == "__main__":
    main()
