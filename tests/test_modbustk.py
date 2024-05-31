def test_modbustk_execute():
    from modbus_tk import modbus_tcp
    import modbus_tk.defines as cst

    addr = "192.168.0.161"
    port = 502
    master = modbus_tcp.TcpMaster(addr, port)

    starting_address = 22
    length = 1
    data_fmt = ""

    result: tuple = master.execute(
        slave=1,
        function_code=cst.READ_INPUT_REGISTERS,
        starting_address=starting_address,
        quantity_of_x=length,
        data_format=data_fmt,
    )

    print(f"result: {result}")
