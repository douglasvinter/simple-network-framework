# -*- coding: utf-8 -*-
"""MQ to interface with backend ZeroMQ based.

Done:
    - Base factory.
    - XREQ factory (Dealer).
    - Singleton ClientMQ (expect to integrate with flask app).
    - Threading semaphore (Sockets are not thread-safe!).
    - Base skeleton for communication (BaseMQResponse & HTTP Codes).

TO-DO:
    - Documentation.
    - Create constants.
    - Define serialization ( for standard api requests).
    - Create access to time-out (define before & after connect).
    - Create access to threads time-out for each instance.
    - Get leverage of flask auth to control MQ channels.
    - Do a MQ Server on core in order to define a base message mechanism.
        (i.e: now if there's an operation requested instead of returning 202 and etc).
"""


__author__ = 'douglasvinter'
__version__ = '0.1'


import zmq
import time
import logging
import threading
from collections import namedtuple
#from ..resource import iotApp
BaseMQResponse = namedtuple('BaseMQResponse', ('status', 'data'))


class ClientFactory(object):
    """"""
    # Poll timeout in msec
    POLL_TIMEOUT = 5

    def __init__(self, user_auth, mq_type, context, mq_uri):
        """"""
        self._user_auth = user_auth
        self.mq_type = mq_type
        self.transport = context.socket(mq_type)
        self.mq_uri = mq_uri
        self.timeout = 5
        self.poll = zmq.Poller()
        self.poll.register(self.transport)
        self.lock = threading.Lock()
        self.cond = threading.Condition(threading.RLock())

    def acquire(self):
        """"""
        self.cond.acquire()
        current_time = start_time = time.time()
        while current_time < start_time + self.timeout:
            if self.lock.acquire(False):
                return True
            else:
                self.cond.wait(self.timeout - current_time + start_time)
                current_time = time.time()
        return False

    def release(self):
        """"""
        self.lock.release()
        self.cond.notify()
        self.cond.release()

    def connect(self):
        """"""
        self.transport.setsockopt(zmq.IDENTITY, self.identity)
        self.transport.connect(self.mq_uri)

    def identity(self):
        """"""
        raise NotImplementedError

    def send(self):
        """"""
        raise NotImplementedError

    def recv(self):
        """"""
        raise NotImplementedError

    def close(self):
        """"""
        raise NotImplementedError


class ClientSUBFactory(ClientFactory):
    """"""
    
    MQ_TYPE = 'sub'

    def __init__(self, user_auth, mq_uri, context):
        """"""
        ClientFactory.__init__(self, user_auth=user_auth, \
            mq_type=zmq.SUB, context=context, mq_uri=mq_uri)
        self.connect()

    def __exit__(self):
        """"""
        self.transport.close(linger=True)

    @property
    def identity(self):
        """"""
        return u'IoT-FE-{}'.format(self._user_auth).encode('ascii')

    def send(self, json_data):
        """"""
        status = msg = ''
        if self.acquire():
            self.transport.send_json(json_data)
            self.release()
            status, msg = 200, 'OK'
        else:
            # 412 - Precondition Failed
            status, msg = 412, 'Resource busy, try later'
        
        return BaseMQResponse(status=status, data=msg)

    def recv(self):
        """"""
        status = msg = ''
        if self.acquire():
            sockets = dict(self.poll.poll(self.POLL_TIMEOUT))
            if self.transport in sockets:
                status, msg = 200, self.transport.recv_json()
            else:
                # 202 - Accepted, but not done yet
                status, msg = 202, 'Request accepted but, processing has not been completed'
            self.release()
        else:
            # 412 - Precondition Failed
            status, msg = 412, 'Resource busy, try later'
        return BaseMQResponse(status=status, data=msg)

    def close(self):
        """"""
        self.transport.close(linger=True)


class ClientXREQFactory(ClientFactory):
    """"""

    MQ_TYPE = 'xreq'

    def __init__(self, user_auth, mq_uri, context):
        """"""
        ClientFactory.__init__(self, user_auth=user_auth, \
            mq_type=zmq.XREQ, context=context, mq_uri=mq_uri)
        self.connect()

    def __exit__(self):
        """"""
        self.transport.close(linger=True)

    @property
    def identity(self):
        """"""
        return u'IoT-FE-{}'.format(self._user_auth).encode('ascii')

    def send(self, json_data):
        """"""
        status = msg = ''
        if self.acquire():
            self.transport.send_json(json_data)
            self.release()
            status, msg = 200, 'OK'
        else:
            # 412 - Precondition Failed
            status, msg = 412, 'Resource busy, try later'
        
        return BaseMQResponse(status=status, data=msg)

    def recv(self):
        """"""
        status = msg = ''
        if self.acquire():
            sockets = dict(self.poll.poll(self.POLL_TIMEOUT))
            if self.transport in sockets:
                status, msg = 200, self.transport.recv_json()
            else:
                # 202 - Accepted, but not done yet
                status, msg = 202, 'Request accepted but, processing has not been completed'
            self.release()
        else:
            # 412 - Precondition Failed
            status, msg = 412, 'Resource busy, try later'
        return BaseMQResponse(status=status, data=msg)

    def close(self):
        """"""
        self.transport.close(linger=True)


class ClientMQ(object):
    """"""

    _mqs = {}
    _instance = None
    context = zmq.Context(io_threads=1)

    def __new__(cls):
        """"""

        if cls._instance is None:
            cls._instance = super(ClientMQ, cls).__new__(cls)
        return cls._instance


    def get_instance_for(self, user_auth, mq_uri = '', mq_type =''):
        """"""

        if user_auth not in self._mqs.keys():
            self._mqs[user_auth] = []
        for c in self._mqs[user_auth]:
            if c.mq_uri == mq_uri:
                return c
        for instance in ClientFactory.__subclasses__():
            if instance.MQ_TYPE == mq_type or instance.mq_uri == mq_uri:
                klss = instance(user_auth=user_auth,
                    mq_uri=mq_uri, context=self.context)
                self._mqs[user_auth].append(klss)
                return klss
        raise ValueError
