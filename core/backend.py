""""""


__author__ = 'douglasvinter'
__version__ = '0.1'


import zmq
from logging import getLogger


class Channels(object): pass


class BackendServerMQ(object):
    """""" 
    channels = Channels()
    poll = zmq.Poller()
    context = zmq.Context(io_threads=1)

    def __init__(self, timeout, mq_uri, logger_name):
        """"""
        self.timeout = timeout
        self.mq_uri = mq_uri.get('xreq')
        self.logging = getLogger(logger_name)

    def recv(self):
        """"""
        sockets = dict(self.poll.poll(self.timeout))
        if self.channels.backend in sockets:
            if self.channels.backend in sockets:
                yield self.channels.backend.recv_multipart()

    def send(self, identity, data):
        self.channels.backend.send_multipart([identity, data])

    def listen(self):
        """"""
        setattr(self.channels, 'backend', self.context.socket(zmq.XREP))
        self.channels.backend.bind(self.mq_uri)
        self.poll.register(self.channels.backend)
        self.logging.debug('Listen at: {}'.format(self.mq_uri))

    def add_channel(self, channel_name, mq_uri, mq_type):
        """"""
        setattr(self.channels, channel_name, self.context.socket(mq_type))
        self.channels.backend.bind(mq_uri)
        self.poll.register(self.channels.__dict__.get(channel_name))
        self.logging.debug('New channel at: {}'.format(mq_uri))

    def shutdown_streams(self):
        """"""
        self.__running = False
        self.channels.backend.close()
        self.context.term()
        self.logging.warning('MQ has been shutdown successfully')

    def __exit__(self):
        """"""
        self.shutdown_streams()
        
