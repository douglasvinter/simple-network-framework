""""""


__author__ = 'douglasvinter'
__version__ = '0.1'


import zmq
import threading
from logging import getLogger


class BackendServerMQ(threading.Thread):
    """"""
    SERVER_TYPE = 'REST_API'

    def __init__(self, context, logger_name='REST MQ Integration', max_workers = 2\
        mq_backend_uri='inproc://iot/rest', mq_frontend_uri='tcp://localhost:5015'):
        """"""
        self.context = context
        self.workers = []
        self.max_workers = max_workers
        self.channels = None
        self.__running = True
        self.main_loop = lambda: self.__running       
        self.logging = getLogger(logger_name)
        self.mq_backend_uri = mq_backend_uri
        self.mq_frontend_uri = mq_frontend_uri
        threading.Thread.__init__(self)

    def run(self):
    """"""
        while self.main_loop():
            sockets = dict(poll.poll())
            if self.channels.frontend in sockets:
                if sockets[self.channels.frontend] == zmq.POLLIN:
                    identity, data = self.channels.frontend.recv_multipart()
                    self.logging.debug('Received {} from {}'.format(data, identity))
                    self.channels.backend.send_multipart([identity, data])
            if self.channels.backend in sockets:
                if sockets[self.channels.backend] == zmq.POLLIN:
                    identity, data = self.channels.backend.recv_multipart()
                    self.logging.debug('Sendint {} to {}'.format(data, identity))
                    self.channels.frontend.send_multipart([identity, data])
        self.shutdown_streams()

    def stop_loop(self):
        """"""
        self.__running = True

    def start_workers(self):
        """"""
        for _ in xrange(self.max_workers):
            worker = BackendWorkers(mq_uri=self.mq_backend_uri,
                context=self.context)
            worker.start()
            self.workers.append(worker)

    def stop_workers(self):
        """"""
        for worker in self.workers:
            worker.stop_loop()
            worker.join()
        self.workers = []
        
    def start_server(self):
        """"""
        self.poll = zmq.Poller()
        self.channels = lambda: object
        setattr(self.channels, 'backend', self.context.socket(zmq.XREP))
        setattr(self.channels, 'frontend', self.context.socket(zmq.XREQ))
        self.poll.register(self.channels.backend, zmq.POLLIN)
        self.poll.register(self.channels.frontend, zmq.POLLIN)

    def shutdown_streams(self):
        """"""
        self.channels.backend.close()
        self.channels.frontend.close()
        self.context.term()

    def __exit__(self):
        """"""
        if len(self.max_workers):
            self.stop_workers()
        self.shutdown_streams()

    def join(self, timeout=None):
        """"""
        if self.__running:
            self.stop_loop()
        super(BackendServerMQ, self).join()
        self.logging.info('Server stopped')


class BackendWorkers(threading.Thread):
    """"""

    def __init__(self, mq_uri, context, logger_name='REST MQ Worker'):
        """"""
        self.channel = context.socket(zmq.XREQ)
        self.channel.connect(mq_uri)
        self.logging = getLogger(logger_name)
        self.__running = True
        self.main_loop = lambda: self.__running
        threading.Thread.__init__(self)

    def run(self):
        """"""
        while self.main_loop():
            ident, msg = self.channel.recv_multipart()
            self.logging.debug('Received {} from {}'.format(data, identity))
            self.channel.send_multipart([ident, msg])

    def stop_loop(self):
        """"""
        self.__running = False

    def __exit__(self):
        """"""
        self.channel.close()

    def join(self, timeout=None):
        """"""
        if self.__running:
            self.stop_loop()
        super(BackendWorkers, self).join()
        self.logging.info('worker stopped')
