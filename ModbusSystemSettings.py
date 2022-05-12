# define any bus setup constants for the Modbus communication here


class ModbusSystem:
    class Timeouts:
        TCPComm = 2000      # milliseconds
        TTYSComm = 2000     # milliseconds
        RetriesTCP = -1        
        RetriesTTYS = -1     
    class Errors:
        Unknown = -1
        AppPollExit = -2
        CommError = -3
        PollTimerOverrun = -4
        InvalidOperation = -5
    class Debugging:
        Verbose = True      # modbus communication informational message level
        Diagnostics = False
        DebugLevel = 0
    class DataRanges:
        MAX_FLT32 = 3.402e38
        MIN_FLT32 = 1.401e-45
        
           
