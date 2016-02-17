""""""


__author__ = 'douglasvinter'
__version__ = '0.1'


import zmq
from logging import getLogger

class BackendServerMQ(object):
    """"""

    channels = lambda: object
    context = zmq.Context(io_threads=1)

    def __init__(self, timeout, mq_uri, logger_name):
        """"""
        self.timeout = timeout
        self.mq_uri = mq_uri
        self.__running = True
        self.main_loop = lambda: self.__running
        self.logging = getLogger(logger_name)

    def recv(self):
    """"""
        while self.main_loop():
            sockets = dict(self.poll.poll(self.timeout))
            if self.channels.backend in sockets:
                if sockets[self.channels.backend] == zmq.POLLIN:
                   yield self.channels.backend.recv_multipart()

    def send(self, identity, data):
        self.channels.frontend.send_multipart([identity, data])

    def listen(self):
        """"""
        self.poll = zmq.Poller()
        setattr(self.channels, 'backend', self.context.socket(zmq.XREP))
        self.channels.backend.bind(self.mq_uri)
        self.poll.register(self.channels.backend, zmq.POLLIN)

    def shutdown_streams(self):
        """"""
        self.__running = False
        self.channels.backend.close()
        self.context.term()
        self.logging.warning('MQ has been shutdown successfully')

    def __exit__(self):
        """"""
        self.shutdown_streams()
