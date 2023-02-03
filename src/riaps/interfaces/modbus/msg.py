import capnp
msg_schema = capnp.load('device.capnp')


def get_schema():
    return msg_schema
