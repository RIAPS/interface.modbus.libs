#!/usr/bin/env python
# -*- coding: utf_8 -*-
"""
 RIAPS Stand-alone modbus master application

 Modbus communication is based on Modbus-tk project

"""

import logging
import random
import string
import os
import threading
import time
import argparse
import struct
import yaml
import modbus_tk
import modbus_tk.defines as cst
from modbus_tk import modbus_tcp, hooks
from timeit import default_timer as elapsed_timer
from time import sleep
from datetime import datetime as dt
import queue
from queue import Queue
import socket
import sys
import select
import zmq 
from zmq import Context 

#import czmq




the_version = '1.0.0'
error_marker = ':Err='
error_string = error_marker + '{0}'

MODBUS_COMMAND_LENGTH = 4
MAX_CLIENTS = 10
ZMQ_PORT_BASE = 5000
MAX_SIGNED_INT = 32767

class MemoryBlocks:
    COILS = 0
    DISCRETE_INPUTS = 1
    ANALOG_INPUTS = 3
    HOLDING_REGISTERS = 4

class Timeouts:
    SECONDS_0_100 = 0.100
    SECONDS_0_250 = 0.250
    SECONDS_0_500 = 0.500
    SECONDS_1_000 = 1.000
    SECONDS_5_000 = 5.000
    MILLISECONDS_0500 = 500
    MILLISECONDS_1000 = 1000
    MILLISECONDS_2000 = 2000
    MILLISECONDS_5000 = 5000
    
class ModbusErrors:
    NO_MEMORY_MAP = -2
    NO_THREAD_COMM = -3
    BAD_COMMAND_LENGTH = -4
    DEVICE_COMM_FAILURE = -5
    WRITE_DATA_FAILURE = -6
    MEMORY_SECTION_NOT_WRITEABLE = -7
    INVALID_MEMORY_SECTION = -8
    INVALID_OUTPUT_VALUE = -9
    INVALID_ACCESS = -10
    EXCEPTION = -100
    


class DeviceMemoryMap:
    def __init__(self, data, dvc): 
        
        self.paramList = []
        
        """ list of elements in each defined parameter """
        elements = data[dvc]['ParameterDef']   
        
        """ the list of parameters for the slave identified by dvc """
        paramKeys = data[dvc]['MemoryMap'].keys()
        curStart = 0
#        print( 'Keys={0}'.format( paramKeys ) )
        for p in paramKeys:
            newParam = Parameter()
            newParam.parm_info = data[dvc]['MemoryMap'][p][elements[0]]    
            #print( 'parm_info={0}'.format( newParam.parm_info ) )
            newParam.parm_name = data[dvc]['MemoryMap'][p][elements[1]]    
            #print( 'parm_name={0}'.format( newParam.parm_name ) )
            newParam.parm_section = data[dvc]['MemoryMap'][p][elements[2]]    
            #print( 'parm_section={0}'.format( newParam.parm_section ) )

            """ if the start value is -1 then the address is assigned sequentially """
            """ based on the previous parameter's location and number of bytes    """ 
            if data[dvc]['MemoryMap'][p][elements[3]] != -1:
                newParam.parm_start = int( data[dvc]['MemoryMap'][p][elements[3]] )
                curStart = newParam.parm_start
            else:
                newParam.parm_start = curStart
            #print( 'Start={0}'.format( newParam.parm_start ) )
                      
            newParam.parm_bytes = int( data[dvc]['MemoryMap'][p][elements[4]] )
            #print( 'parm_bytes={0}'.format( newParam.parm_bytes ) )
            newParam.parm_type = data[dvc]['MemoryMap'][p][elements[5]]    
            #print( 'parm_type={0}'.format( newParam.parm_type ) )
            newParam.parm_order = data[dvc]['MemoryMap'][p][elements[6]]    
            #print( 'parm_order={0}'.format( newParam.parm_order ) )
            newParam.parm_value = data[dvc]['MemoryMap'][p][elements[7]]    
            #print( 'parm_value={0}'.format( newParam.parm_value ) )
            newParam.parm_units = data[dvc]['MemoryMap'][p][elements[8]]  
            #print( 'parm_units={0}'.format( newParam.parm_units ) )
            newParam.parm_access = data[dvc]['MemoryMap'][p][elements[9]]  
            #print( 'parm_access={0}'.format( newParam.parm_access ) )
            newParam.parm_functions = data[dvc]['MemoryMap'][p][elements[10]]  
            #print( 'parm_functions={0}'.format( newParam.parm_functions ) )
            """ Add the parameter to the list """    
            self.paramList.append( newParam )  
            """ Update the start location """
            curStart += int( newParam.parm_bytes/2 )    
    
    def __destroy__(self):
        for parm in self.paramList :
            pass
        self.paramList.clear()
            

class Parameter:
    def __init__(self):
        self.parm_info = '' 
        self.parm_name = ''    
        self.parm_section = ''    
        self.parm_start = 0    
        self.parm_bytes = 1    
        self.parm_type = ''    
        self.parm_order = ''    
        self.parm_value = ''    
        self.parm_units = []   
        self.parm_access = [] 
        self.parm_functions = []
   
    def __str__(self):
        return '{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10}'.format(   self.parm_info,
                                                                        self.parm_name,    
                                                                        self.parm_section,    
                                                                        self.parm_start,    
                                                                        self.parm_bytes,    
                                                                        self.parm_type,    
                                                                        self.parm_order,    
                                                                        self.parm_value,    
                                                                        self.parm_units,   
                                                                        self.parm_access, 
                                                                        self.parm_functions )

""" A modbus device object """
class ModbusDevice( threading.Thread ):
    def __init__(self, name, tcpaddr, tcpport, slvid, descr, index ): 
        threading.Thread.__init__(self)
        # 
        self.moniker = name
        self.addr = tcpaddr
        self.port = tcpport
        self.slave_id = slvid
        self.description = descr
        self.id = index
        # 
        self.active = threading.Event()
        self.active.clear()
        self.waiting = threading.Event()
        self.waiting.clear()
        self.device_name = '{0}:{1}:{2}'.format( self.addr, self.port, self.slave_id )
        self.pollcommand = ''  
        self.modfunc = ''
        self.modaddr = 1
        self.modlen = 1
        self.poll_period = 1000
        self.poll_func = 'None'
        self.is_polled = False
        self.memory_map = None
        self.device_thread_id = 0  # invalid thread ID
        self.master = None
        self.command_index = 0
        self.context = None
        self.socket = None
        
        
    """-----------------------------------------------------------------------------"""
            
    def __destroy__(self):
        for parm in self.paramList :
            pass
        self.paramList.clear()
    
    def AccessParameter(self, cmd ):
        response = ''
        strs = cmd.split( sep=',' )
        
        """ make sure there are the correct number of strings """            
        if len(strs) == MODBUS_COMMAND_LENGTH :
            
            newval = 'NONE'
            if strs[3].find('=') != -1 :
                vals = strs[3].split( sep='=' )
                if len(vals) == 2 and vals[1].isnumeric() : # TODO: Change this 
                    newval = vals[1]
                    strs[3] = vals[0]
                    
            if self.socket != None :
                """ remove any whitespace """
                strs[0] = strs[0].strip()
                strs[1] = strs[1].strip()
                strs[2] = strs[2].strip()
                strs[3] = strs[3].strip()
                """"look through the memory map for the parameter """
                if self.memory_map != None :
                    for m in self.memory_map.paramList :
                        if m.parm_name.upper() == strs[3].upper() :
                            operation = 'INVALID'
                            """ if the parameter is found process the modbus command """
                            if strs[2].upper() == 'WRITE' :  
                                if len( [s for s in m.parm_access if 'WRITE' in s] ) > 0 :
                                    operation = 'WRITE'
                            elif strs[2].upper() == 'RW' :  
                                if len( [s for s in m.parm_access if 'WRITE' in s] ) > 0 and len( [s for s in m.parm_access if 'READ' in s] ) > 0 :
                                    operation = 'RW'
                            elif strs[2].upper() == 'READ' :   # is a read command?
                                if len( [s for s in m.parm_access if 'READ' in s] ) > 0 :
                                    operation = 'READ'
                            else:
                                pass 
                                       
                            if operation != 'INVALID' :          
                                if m.parm_section.upper() == 'HOLDING_REGISTERS':
                                    section = cst.HOLDING_REGISTERS
                                elif m.parm_section.upper() == 'COILS':
                                    section = cst.COILS
                                elif m.parm_section.upper() == 'DISCRETE_INPUTS':
                                    section = cst.DISCRETE_INPUTS
                                elif m.parm_section.upper() == 'ANALOG_INPUTS':
                                    section = cst.ANALOG_INPUTS
                                else:
                                    section = -1
                                    
                                parmtype = m.parm_type.upper()  
                                  
                                if parmtype == 'FLOAT':
                                    if m.parm_order.upper() == 'BE':
                                        fmt = '>f'
                                    else:
                                        fmt = '<f'
                                elif parmtype == 'WORD' or parmtype == 'BIT':
                                    if m.parm_order.upper() == 'BE':
                                        fmt = '>H'
                                    else:
                                        fmt = '<H'
                                elif parmtype == 'DWORD' :
                                    if m.parm_order.upper() == 'BE':
                                        fmt = '>I'
                                    else:
                                        fmt = '<I'
                                else:
                                    fmt = 'h'
                                
                                scaling = float( m.parm_units[0] )
                                                            
                                if parmtype == 'BIT' :
                                    operation += ':'
                                    operation += str( m.parm_units[1] )                            
                                    units = 'NONE'
                                    #force no scaling if the type is BIT
                                    if scaling > 0.0 :
                                        scaling = 1.0
                                else:        
                                    units = m.parm_units[1]
                                      
                                start = m.parm_start
                                numints = int( m.parm_bytes/2 )
                                self.socket.send_string( '{0},{1},{2},{3},{4},{5}'.format( section, 
                                                                                           start, 
                                                                                           numints, 
                                                                                           fmt, 
                                                                                           operation, 
                                                                                           newval ) )
                                value_str = self.socket.recv_string()
                                
                                if numints == 1 :
                                    if value_str.isnumeric() : #""" TODO: Change this """
                                        the_value = int( value_str )
                                        if scaling != 0.0 : 
                                            # scale as requested
                                            if the_value > MAX_SIGNED_INT :
                                                ret_value = float( the_value - MAX_SIGNED_INT )
                                                ret_value = ret_value * -1
                                            else :
                                                ret_value = float( the_value )
                                                
                                            ret_value = ret_value * float( m.parm_units[0] )
                                                
                                            value_str = str( ret_value )
                                        else: # show as binary
                                            value_str = bin( the_value ) 
                                    
                                    #print( 'str3={0}, value_str={1}, units={2}'.format( strs[3], value_str, units ) )                                        
                                    response = strs[3] + '=' + value_str
                                    
                                    """ if no error, add the units """
                                    try :
                                        # will throw exception if value is not able to convert to float
                                        float( value_str )
                                        # otherwise add the units
                                        if units != 'NONE' :
                                            response += ' ' + units
                                    except :
                                        pass
                                else:
                                    response = strs[3] + '=' + value_str
                            else:
                                response = error_string.format( ModbusErrors.INVALID_ACCESS )
                else :
                    response = error_string.format( ModbusErrors.NO_MEMORY_MAP )
                            
            else :
                    response = error_string.format( ModbusErrors.NO_THREAD_COMM )
        else :
            response = error_string.format( ModbusErrors.BAD_COMMAND_LENGTH  )
                
        return response
            
    def AddParameter(self, parm ):
        self.paramList.append( parm )
        
    def SetPollCommand(self, func, addr, len ):
        self.modfunc = func
        self.modaddr = int( addr ) 
        self.modlen = int( len )
        self.pollcommand = 'master.execute( {0}, {1}, {2}, {3} )'.format( self.slave_id, self.modfunc, self.modaddr, self.modlen )   
           
    def IsPolling(self):
        return self.is_polled
    
    def GetDeviceName(self):
        return self.device_name
    
    def GetPollCommand(self):
        return self.pollcommand
    
    def SetPollingPeriod(self, period ):
        self.poll_period = period

    def GetPollingPeriod(self):
        return self.poll_period
    
    def SetPollFunction(self, func ):
        self.poll_func = func
        
    def GetPollFunction(self ):
        return self.poll_func
    
    def GetDeviceID(self):
        return self.device_thread_id
    
    def deactivate(self):
        if self.socket != None :
            try :
                self.socket.send_string( 'EXIT' )
            except Exception as ex :
                 self.active.clear()        
        else :
            self.active.clear()    
    
    def set_bit(self, value, bit ):
        return ( value | (1<<bit) )
    
    def clr_bit(self, value, bit ):
        return ( value & ~(1<<bit) )
     
    """ returns the device inner port number """
    def GetInnerPort(self):
        return (ZMQ_PORT_BASE + self.id)   
               
    def run(self): 
        print('ModbusDevice::run( {0} ) starting...'.format( self.device_name ) )
        RunTime = dt.now()
        self.name = self.device_name
        self.device_thread_id = self.ident
        time.sleep(Timeouts.SECONDS_0_100)
        
        """ Thread ZMQ pair connection for messaging to the device worker thread """
        con = zmq.Context()
        sock = con.socket( zmq.PAIR )
        sock.bind( 'tcp://*:%s' % self.GetInnerPort() )
        poller = zmq.Poller()
        poller.register( sock, zmq.POLLIN )
        
        self.context = zmq.Context()
        self.socket = self.context.socket( zmq.PAIR )
        self.socket.connect( 'tcp://localhost:%s' % self.GetInnerPort() )
        
        """ master modbus object """
        self.master = modbus_tcp.TcpMaster( self.addr, self.port )

        """ timer for various purposes """
        start_time = elapsed_timer()
        elapsed_time = 0.0       
        cnt = 1.0

        """ This is to allow handling a problem in the initialization of the master """
        try:
            """ Test READ to verify master connected and working correctly """
            val = self.master.execute( self.slave_id, cst.READ_HOLDING_REGISTERS, 0, 1 )
            """ Signal that the device thread loop should be running """
            self.active.set()
        except Exception as ex:
            print( 'Master exception {0}!'.format( ex ))
            """ do not enter the run loop if the master throws an exception """
            self.active.clear()

        """------------------------- Start of thread loop ---------------------------"""
        while self.active.is_set() :
            # read a command from the queue
            comms = dict( poller.poll( Timeouts.MILLISECONDS_5000 ) )
            if sock in comms and comms[sock] == zmq.POLLIN :
                cmd = sock.recv_string()
                """ format of cmd = '0,0,1,>H' """
                strs = cmd.split( sep=',')
                #print( strs )
                if len( strs ) == 6 :
                    section = int( strs[0] )    # the modbus memory section
                    start = int( strs[1] )      # the start address for the parameter
                    numregs = int( strs[2] )    # the number of 16Bit integers 
                    fmt = strs[3]               # the storage format
                    operation = strs[4]
                    outval = strs[5]
                    function = 0
                    #print( 'CMD: {0}, {1}, {2}, {3}, {4}, {5} )'.format( section, start, numregs, fmt, operation, outval ) )    
                    
                    """ Execute the Modbus Command """
                    try:
                        if operation.find( 'WRITE' ) != -1 :
                            if section == cst.COILS :
                                function = cst.WRITE_SINGLE_COIL
                            elif section == cst.HOLDING_REGISTERS :
                                function = cst.WRITE_SINGLE_REGISTER
                            else :
                                function = -1
                            #print( 'WRITE: {0}, {1}, {2}, )'.format( function, start, outval ) )    
                            if function != -1 : 
                                if outval.isnumeric() : #""" TODO: Change this """
                                    # bit set/clear operation
                                    if operation.find(':') != -1 :
                                        (op, msk) = operation.split(':')  
                                        # get the current flag settings
                                        if function == cst.WRITE_SINGLE_REGISTER :
                                            response = self.master.execute( self.slave_id, cst.READ_HOLDING_REGISTERS, start, numregs )
                                            
                                        bit = int( msk )  
                                        curval = int( response[0] )
                                        # set/clear the bit
                                        if outval == '0' :
                                            curval = self.clr_bit(curval, bit)
                                        elif outval == '1' :
                                            curval = self.set_bit(curval, bit)
                                        else:
                                            pass 
                                           
                                        outval = str( curval )
                                    #write the new value   
                                    self.master.execute( self.slave_id, function, start, output_value=int(outval) )
                                    #read the value back and return it as the response
                                    if function == cst.WRITE_SINGLE_COIL :
                                        response = self.master.execute( self.slave_id, cst.READ_COILS, start, numregs )
                                    else :
                                        response = self.master.execute( self.slave_id, cst.READ_HOLDING_REGISTERS, start, numregs )                                        
                                else :
                                    response = [error_string.format( ModbusErrors.INVALID_OUTPUT_VALUE ), ]  
                            else :
                                response = [error_string.format( ModbusErrors.MEMORY_SECTION_NOT_WRITEABLE ),]   
                                  
                        elif operation.find( 'READ' ) != -1 :   
                            if section == cst.COILS :
                                function = cst.READ_COILS
                            elif section == cst.ANALOG_INPUTS :
                                function = cst.READ_INPUT_REGISTERS
                            elif section == cst.DISCRETE_INPUTS :
                                function = cst.READ_DISCRETE_INPUTS
                            elif section == cst.HOLDING_REGISTERS :
                                function = cst.READ_HOLDING_REGISTERS
                            else:
                                function = -1
                                
                            if function != -1 : 
                                if numregs > 1 :   
                                    #print( 'READ RANGE: {0}, {1}, {2}, {3},{4}'.format( function, start, numregs, fmt, self.slave_id ) )    
                                    response = self.master.execute( self.slave_id, function, start, quantity_of_x=numregs )   
                                else:
                                    #print( 'READ SINGLE: {0}, {1}, {2}, {3}, {4}'.format( function, start, numregs, fmt, self.slave_id ) )    
                                    response = self.master.execute( self.slave_id, function, start, quantity_of_x=numregs )
                            else :
                                response = [error_string.format( ModbusErrors.INVALID_MEMORY_SECTION ),]   
                        
                        #print( response )        
                        if numregs > 1 :    
                            sock.send_string( '{0}'.format( response )  )
                        else:
                            sock.send_string( '{0}'.format( response[0] )  )
                            
                    except Exception as ex:
                        print( '{' +  'Exception sending request to Slave={0}->Message={1}'.format( self.device_name, ex ) + '}' )
                        print( 'Memory Section={0}, Function ID={1}, Address={2}, Length={3}, Operation={4}'.format(    section,
                                                                                                                        function,
                                                                                                                        start, 
                                                                                                                        numregs,
                                                                                                                        operation ) )
                        sock.send_string( error_string.format( ModbusErrors.EXCEPTION ) )
                elif cmd.upper() == 'EXIT':
                    print( 'Thread exit requested...')
                    self.active.clear()
                else :
                    sock.send_string( error_string.format( ModbusErrors.DEVICE_COMM_FAILURE ) )
                     
        """---------------------------- End of thread loop ------------------------------"""
        
        """ Calculate the thread's total running time """        
        RunTime = dt.now() - RunTime;                                                   

        sock.close()
        self.socket.close()
        
        self.context = None
        self.socket = None
        
        print( 'Thread with ID={0} and Name={1} exited normally.'.format( self.device_thread_id, self.name ) )
        print( 'Total run time: %03d days, %02d hours, %02d minutes, and %02d seconds' % 
                (RunTime.days, RunTime.seconds//3600, RunTime.seconds//60 % 60, RunTime.seconds % 60) )                

class Client(threading.Thread): 
    def __init__(self, connection, devices ):     
        threading.Thread.__init__(self)
        self.modbus_devices = devices
        self.connection = connection
        (self.client, self.address) = connection
        (self.ip, self.port) = self.address 
        self.active = threading.Event()
        self.active.set()
        self.commsactive = threading.Event()
        self.commsactive.set()
        
    def deactivate(self):
        self.SendString('EXIT')

    def SendString(self, reply ):
        if self.commsactive.is_set( ) :
            try:
                reply += '\n'
                self.client.sendall( bytearray( reply, 'utf-8' ) )
                if reply.find('EXIT') != -1 :
                    self.commsactive.clear()
            except socket.error as e:
                #print('Exception: {0}'.format( e ) )
                self.commsactive.clear()
                 
    def run(self):
        print( 'TCP Client {0} is connected and thread is running...'.format( self.address ) )
        self.name = '{0}:{1}'.format( self.ip, self.port )
        print( 'Thread.name = {0}'.format( self.name ) )
        inputs = [self.client]

        """------------------------- Start of thread loop ---------------------------"""
        while self.active.is_set( ) :
            if self.commsactive.is_set( )  :
                data = []
                """ wait for data from the socket """
                readable, writeable, except_state = select.select( inputs, [], [], 1.0 )
                """ if there are actions present then read the data """
                for c in readable :
                    data = c.recv(2048)
                    """ if data exists then process it """
                    if data :
                        data = data.decode( 'utf-8' )
                        cmdstr = data.strip()
                        strs = cmdstr.split( sep=',' ) 
                        if len( strs ) == 3 :                   # modbus command contains 3 fields
                            dest, access, param = strs                          
                            dest = dest.strip()
                            access = access.strip()
                            param = param.strip()
                            """ send the command to the correct Modbus device """
                            FoundDevice = False
                            for dvc in self.modbus_devices :
                                if dest == dvc.device_name or dest == dvc.moniker :
                                    FoundDevice = True
                                    response = dvc.AccessParameter( '{0},{1},{2},{3}'.format( self.ip, strs[0], strs[1], strs[2]) )
                                    if access == 'WRITE' :
                                        reply = '{0},{1} -> {2}'.format( self.ip, dest, response )
                                    else:
                                        reply = '{0},{1} : {2}'.format( self.ip, dest, response )
                                    self.SendString( reply )
                            """ if the device is not found then let the client know """        
                            if FoundDevice == False :
                                self.SendString( 'Device {0} is not configured!'.format( dvc.device_name ) )                    
                        else:                                   # informational and configuration type commands
                            strs = cmdstr.split( sep=' ' )
                            if len( strs ) == 2 :
                                cmd, dest = strs
                                if cmd.upper() == 'LS' and dest.find('-d') == -1 and dest.find('-D') == -1 and dest.find('-n') == -1:
                                    DeviceFound = False
                                    for dvc in self.modbus_devices :
                                        if dest == dvc.device_name or dest == dvc.moniker :
                                            DeviceFound = True
                                            reply = 'Parameter list for {0}({1}):\n'.format( dvc.moniker, dvc.device_name )                        
                                            self.SendString( reply )
                                            for p in dvc.memory_map.paramList :
                                                reply = (   '\033[33m Name:\033[0m{0}'   +
                                                            '\033[33m Access:\033[0m{1}' +
                                                            '\033[33m Type:\033[0m{2}'   +
                                                            '\033[33m Units:\033[0m{3}'  +
                                                            '\033[33m Addr:\033[0m{4}'+
                                                            '\033[33m Desc:\033[0m{5}'  ).format( p.parm_name, 
                                                                                                      p.parm_access, 
                                                                                                      p.parm_type, 
                                                                                                      p.parm_units,
                                                                                                      p.parm_start,
                                                                                                      p.parm_info )            
                                                self.SendString( reply )
#                                                 reply = '\tExample:\033[32m {0}, {1}, {2}\n\033[0m'.format( dvc.device_name, 
#                                                                                                             p.parm_access[0], 
#                                                                                                             p.parm_name       )            
#                                                 self.SendString( reply, False )
                                            self.SendString( 'Done.' )
                                    if not DeviceFound :
                                        reply = 'Modbus device {0} configuration not found.'.format( dest )            
                                        self.SendString( reply )
                                elif cmd.upper() == 'LS' and dest.find('-n') != -1 :
                                    dest = dest[2:]
                                    dest = dest.strip()
                                    DeviceFound = False
                                    for dvc in self.modbus_devices :
                                        if dest == dvc.device_name or dest == dvc.moniker :
                                            DeviceFound = True
                                            for p in dvc.memory_map.paramList :
                                                reply = (   '{0},' +
                                                            '{1},' +
                                                            '{2},' +
                                                            '{3},' +
                                                            '{4},' +
                                                            '{5},' +
                                                            '{6},' +
                                                            '{7}'   ).format(   p.parm_name, 
                                                                                p.parm_access, 
                                                                                p.parm_type, 
                                                                                p.parm_units,
                                                                                p.parm_start,
                                                                                p.parm_bytes,
                                                                                p.parm_section,
                                                                                p.parm_info )            
                                                self.SendString( reply )
                                            self.SendString( 'Done.' )
                                    if not DeviceFound :
                                        reply = 'Modbus device {0} configuration not found.'.format( dest )            
                                        self.SendString( reply )
                                elif cmd.upper() == 'LS' and dest == '-d' :
                                    self.SendString( 'List of configured slave devices:\n' )
                                    reply = ( '\033[33m{:<20}\033[0m' + 
                                              '\033[31m{:<15}\033[0m' + 
                                              '{:<10}' + 
                                              '{:<5}' + 
                                              '{:<15}' + 
                                              '{:<30}\n' ).format( 'Name','IP','Port', 'ID', 'State','Description')
                                    self.SendString( reply )
                                    for dvc in self.modbus_devices :
                                        if dvc.isAlive() :
                                            dvc_state = 'Running'
                                        else:
                                            dvc_state = 'Terminated'
                                        
                                        reply = ( '\033[33m{:<20}\033[0m' + 
                                                 '\033[31m{:<15}\033[0m' + 
                                                 '{:<10}' + 
                                                 '{:<5}' + 
                                                 '{:<15}' + 
                                                 '{:<30}' ).format( dvc.moniker, 
                                                                    dvc.addr, 
                                                                    dvc.port,
                                                                    dvc.slave_id, 
                                                                    dvc_state, 
                                                                    dvc.description )    
                                        self.SendString( reply )
                                    self.SendString( 'Done.' )
                                elif cmd.upper() == 'LS' and dest == '-D' :
                                    for dvc in self.modbus_devices :
                                        if dvc.isAlive() :
                                            dvc_state = 'Running'
                                        else:
                                            dvc_state = 'Terminated'
                                        
                                        reply = ( '{0},' + 
                                                  '{1},' + 
                                                  '{2},' + 
                                                  '{3},' + 
                                                  '{4},' + 
                                                  '{5}' ).format(   dvc.moniker, 
                                                                    dvc.addr, 
                                                                    dvc.port,
                                                                    dvc.slave_id, 
                                                                    dvc_state, 
                                                                    dvc.description )    
                                        self.SendString( reply )
                                    self.SendString( 'Done.' )
                                else:
                                    self.SendString( 'Unknown command: {0}'.format( cmdstr ) )
                            elif cmdstr.upper().find('EXIT') != -1 :
                                self.SendString('EXIT')
                            elif cmdstr == '$' :
                                self.SendString( 'RIAPS Modbus-TCP Master version: {0}\n'.format( the_version ) )
                            else:   
                                self.SendString( 'Error: malformed command: {0}!'.format( cmdstr ) )  

            else:
                self.client.close()        
                self.active.clear()
                print( 'TCP Client {0} connection closed.'.format( self.address ))

        """------------------------- End of thread loop ---------------------------"""
                
        print( 'TCP Client thread [ {0} ] exited normally.'.format( self.address ))
            
      
class InputWatcher( threading.Thread ):
    def __init__(self, devices ):     
        threading.Thread.__init__(self)
        self.modbus_devices = devices
        self.active = threading.Event()
        self.active.set()

    def deactivate(self):
        self.active.clear()

    def run(self):
        userinput = ''
        repeat = False
        show_all = False
        cnt = 0
        last_time = dt.now()
        last_time = last_time - last_time
        """------------------------- Start of thread loop ---------------------------"""
        while self.active.is_set():
            i,o,e = select.select( [sys.stdin], [], [], Timeouts.SECONDS_0_100 )
            if i :
                userinput = sys.stdin.readline().strip()
            else: 
                if repeat == False :
                    userinput = ''
            
            # commands for timing measurement    
            if userinput == '1' :
                mbcmd = [ '127.0.0.1', '10.0.3.100:502:1', 'READ', 'IA_PEAK' ]
            elif userinput == '2' :
                mbcmd = [ '127.0.0.1', '10.0.3.102:502:1', 'READ', 'IA_PEAK' ]
            elif userinput == '3' :
                mbcmd = [ '127.0.0.1', '10.0.3.100:502:1', 'READ', 'IB_PEAK' ]
            elif userinput == '4' :
                mbcmd = [ '127.0.0.1', '10.0.3.102:502:1', 'READ', 'IB_PEAK' ]
            elif userinput == '8' :
                repeat = True
                show_all = True
                cnt = 0
            elif userinput == '9' :
                repeat = True
                show_all = False
                last_time = last_time - last_time
                cnt = 0
            elif userinput == '0' :
                repeat = False
                show_all = False
            elif userinput == 'q'  or userinput == 'Q' :
                mbcmd = []
                self.active.clear() 
            else:
                clt = '127.0.0.1'
                s = userinput.split(sep=',', maxsplit=3)
                if len(s) == 3 :
                    mbcmd = [ clt, s[0], s[1], s[2] ]
                else :
                    mbcmd = []

            if mbcmd != [] :
                if repeat == False :    
                    print( 'User command Client={0} Slave={1} Command={2},{3}'.format( mbcmd[0], 
                                                                                       mbcmd[1], 
                                                                                       mbcmd[2], 
                                                                                       mbcmd[3] ) )
                for slv in self.modbus_devices :
                    if slv.device_name == mbcmd[1] or slv.moniker == mbcmd[1] :
                        time1 = dt.now()
                        response = slv.AccessParameter( '{0},{1},{2},{3}'.format(  mbcmd[0],
                                                                                    mbcmd[1],
                                                                                    mbcmd[2],
                                                                                    mbcmd[3] ) )
                        time2 = dt.now()
                        if repeat == False :    
                            print( 'Read command ToClient={0} FromSlave={1}, Response={2}'.format( mbcmd[0], 
                                                                                                   slv.device_name, 
                                                                                                   response )       )
                        """ print the elapsed time in the console """    
                        calc_time = time2 - time1    
                        if calc_time > last_time or show_all:
                            print( '{0},{1}'.format( cnt, calc_time ) )
                            last_time = calc_time
                        cnt = cnt + 1
                mbcmd =[]
        """------------------------- End of thread loop ---------------------------"""
                        
        print( 'Keyboard input thread exited!' )
    
    
def main():
    """main"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True )
    parser.add_argument('--address', required=True )
    parser.add_argument('--port', required=True )
    
    
    list_of_slaves = []
    list_of_clients = []
    input_thread = None
    
    try:
        """ read in configuration """
        args = parser.parse_args()
        print( 'Configuration file is: {0}'.format( args.config ) )     
        with open(args.config, 'r') as f:
            data = yaml.safe_load( f )
            modbusDevices = data.keys()
        """ Read in the devices setup in the configuration file """    
        for dvc in modbusDevices :
            mbdvc = ModbusDevice(   dvc, 
                                    data[dvc]['Address'], 
                                    data[dvc]['Port'], 
                                    data[dvc]['SlaveID'], 
                                    data[dvc]['Description'],
                                    len( list_of_slaves ) + 1    )
            
            mbdvc.memory_map = DeviceMemoryMap( data, dvc )
            list_of_slaves.append( mbdvc )                

        """ Connect to each slave device """    
        for slv in list_of_slaves :
            slv.start()        
            while( slv.name != slv.device_name ):
                sleep( Timeouts.SECONDS_0_100 )
        """ Start a thread to handle keyboard input """        
        input_thread = InputWatcher( list_of_slaves )
        input_thread.start()

        """ Start a server listening for remote clients """        
        try:
            svrsock = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
            svrsock.bind( ( args.address, int( args.port ) ) )
            svrsock.listen( MAX_CLIENTS ) 
            read_list = [svrsock]
            print('Server {0} on port {1} is listening for connections...'.format( args.address, int( args.port ) ) )
        except socket.error as e :
            read_list = []
            print( 'Server socket error {0}'.format( e ) )

        """ loop waiting for the keyboard input thread to end """     
        finished = False
        while not finished :
            finished = True
            """ closing the keyboard input thread shuts down everything """
            if input_thread.isAlive() :
                finished = False
                
            """ while waiting for key input, allow client connections """
            if( read_list != [] ) :    
                if not finished :
                    readable, writeable, excepted = select.select( read_list, [], [], Timeouts.SECONDS_0_250 )
                    if readable :
                        for s in readable :
                            if s is svrsock :
                                conn = svrsock.accept()
                                newClient = Client( conn, list_of_slaves )
                                newClient.start()
                                list_of_clients.append( newClient )
                                
            """ remove any abandoned clients from the list """                        
            for c in list_of_clients :
                if not c.isAlive() :
                    print( 'Discarding abandoned client object: {0}:{1}'.format( c.ip, c.port ))
                    list_of_clients.remove( c )   
                
        """ End of program loop """            
        
        """------------------ Shutdown everything --------------------------"""
    
        """ Send the deactivate signal to all TCP client threads """
        for clt in list_of_clients :
            clt.deactivate()        
                                   
        """ Send the deactivate signal to all Modbus device threads """
        for slv in list_of_slaves :
            slv.deactivate()
                                       
        """ wait for all threads to exit  """
        finished = False
        while( not finished ):
            finished = True
            for slv in list_of_slaves :
                if slv.isAlive() :
                    finished = False 
            for clt in list_of_clients :
                if clt.isAlive() :
                    finished = False
        
#        socket.socket( socket.AF_INET, socket.SOCK_STREAM ).connect( ( args.address, int(args.port) ) )            
        svrsock.close()   
                        
        print( 'Program exited normally.' )     
                            

    except modbus_tk.modbus.ModbusError as exc:
        print("%s- Code=%d", exc, exc.get_exception_code())

if __name__ == "__main__":
    main()
