# -*- coding: utf-8 -*-
"""Manager module

Manager to start components, open sockets, manage the scheduler,
register new tasks and etc.
"""


__author__ = 'douglasvinter'


import os
import sys
import utils
import threading
import importlib
import multiprocessing
from logging import getLogger
from .backend import BackendServerMQ


class ContextManager(threading.Thread, BackendServerMQ):
    """Components manager, semaphores and data sharing.

    This class is a singleton instance which provides data sharing
    between the components, and manage it.

    The Manager will also provide a WatchDog method for alerting in case
    any component may become zombie/defunct.
    """

    _instance = None
    __isrunning = True

    def __new__(cls):
        """Avoids another core to be initialized."""
        if not cls._instance:
            cls._instance = super(ContextManager, cls).__new__(cls)
        return cls._instance

    def __repr__(self):
        return '<{} ContextManager instance at {}>'.format(self.__class__.__name__,
            id(self))

    def __str__(self):
        return '<{} ContextManager instance at {}>'.format(self.__class__.__name__,
            id(self))

    def __init__(self):
        """"""
        self.config = utils.parse_config()
        self.components = {}
        self.logging = getLogger(self.config.core.get('logger_name'))
        self.manager_event = lambda: self.__isrunning
        threading.Thread.__init__(self)
        BackendServerMQ.__init__(self, **self.config.core.get('kwargs'))
        self.logging.info('IoT Manager started at pid: {}'.format(os.getpid()))
        self.logging.info('Starting components...')
        self.start_framework()

    @staticmethod
    def get_instance():
        """Gets class instance."""
        if not ContextManager._instance:
            ContextManager._instance = ContextManager()
        return ContextManager._instance

    def run(self):
        """Core management and engine-start."""
        while self.manager_event():
            identity = msg = ''
            try:
                identity, msg = self.recv().next()
            except StopIteration:
                self.logging.info('No data on MQ:{}'.format(self.mq_uri))
            if identity and msg:
                self.logging.info('Received: {} from {}'.format(identity, msg))
                self.send([identity, msg])
        self.shutdown()

    def shutdown(self):
        """Stop components"""
        for component in self.config.components.keys():
            if self.config.components[component].type == util.ComponentEnum.STANDALONE_PROCESS:
                self.stop_process(component)
        self.logging.info('All done, bye')

    def start_framework(self):
        """Start all registered / non - started workers.

        Check core.util.COMPONENTS to add new components.
        """
        try:
            self.listen()
        except zmq.ZMQError as e:
            self.logging.warning('Error registering channel{}:\n{}' \
                .format(self.mq_uri, e))

        for component in self.config.components.keys():
            if component != 'core':
                if component[component].type == util.ComponentEnum.STANDALONE_PROCESS:
                    self.start_process(component)

    def start_process(self, component_name):
        """Starts a child process component and update component mapping object."""
        method = self.config.component[component]['start']
        kwargs = self.config.component[component]['kwargs']
        path = self.config.component[component]['path']

        try:
            imp = importlib.import_module(path)
            proc = multiprocessing.Process(target=getattr(imp, method),
                                           kwargs=kwargs)
            proc.start()
        except (ImportError, multiprocessing.ProcessError) as err:
            self.logging.critical('Error starting {}'.format(name))
            self.logging.critical(err)
        else:
            self.logging.info('{} started with pid: {} (child)'.format(name, proc.pid))
            self.components[component_name] = utils.ProcessComponent(pid=proc.pid, process=proc)

    def stop_process(self, process_name):
        """"""
        if process_name in self.components.keys() and \
            isinstance(self.components[process_name], utils.ProcessComponent):
            if self.components[process_name].process.is_alive():
                self.components[process_name].process.join()
                self.logging.info('Component {} pid {} stopped'.format(process_name
                self.components[process_name].pid))
                del self.components[process_name]
        else:
            self.logging.info('Unknown process {}'.format(process_name))

    def stop_worker(self, worker_name):
        raise NotImplementedError

    def stop_pool(self, worker_name):
        raise NotImplementedError
