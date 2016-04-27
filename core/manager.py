# -*- coding: utf-8 -*-
"""Manager module

Manager to start components, open sockets, manage the scheduler,
register new tasks and etc.
"""


__author__ = 'douglasvinter'


import os
import zmq
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
        return '<{} instance at {}>'.format(self.__class__.__name__,
            id(self))

    def __str__(self):
        return '<{} instance at {}>'.format(self.__class__.__name__,
            id(self))

    def __init__(self):
        """"""
        utils.parse_config()
        self.logging = getLogger(ContextManager.__class__.__name__)
        self.manager_loop = lambda: self.__isrunning
        utils.Cache(components={})
        utils.Cache(storage={})
        BackendServerMQ.__init__(self, **utils.Cache().get('config.core.backend.kwargs'))
        self.logging.info('IoT Manager started at pid: {}'.format(os.getpid()))
        self.logging.info('Starting components...')
        self.start_framework()
        threading.Thread.__init__(self)

    @staticmethod
    def get_instance():
        """Gets class instance."""
        if not ContextManager._instance:
            ContextManager._instance = ContextManager()
        return ContextManager._instance

    def run(self):
        """Core management and engine-start."""
        while self.manager_loop():
            for identity, msg in self.recv():
                self.logging.info('Received: {} from {}'.format(msg, identity))
                self.send(identity, msg)
        self.shutdown()

    def shutdown(self):
        """Stop components"""
        for component in utils.Cache().get('components').keys():
            if utils.Cache().get([component, 'type']) == utils.Constants.PROCESS:
                self.stop_process(component)
        self.logging.info('All done, bye')

    def start_framework(self):
        """Start all registered / non - started workers.

        Check core.util.COMPONENTS to add new components.
        """
        try:
            self.listen()
        except zmq.ZMQError as e:
            self.logging.warning('Error registering channel: {} - {}' \
                .format(self.mq_uri, e))

        for component in utils.Cache().get('config.components').keys():
            if utils.Cache().get(['config', 'components', component, 'type']) \
            == utils.Constants.PROCESS:
                self.start_process(component)

    def start_process(self, component_name):
        """Starts a child process component and update component mapping object."""
        comp = utils.Cache().get(['config', 'components', component_name])
        method = comp.get('start')
        kwargs = comp.get('kwargs')
        path = comp.get('path')

        try:
            imp = importlib.import_module(path)
            proc = multiprocessing.Process(target=getattr(imp, method),
                                           kwargs=kwargs)
            proc.start()
        except (ImportError, multiprocessing.ProcessError) as err:
            self.logging.critical('Error starting {}: {}'.format(component_name, err))
        else:
            self.logging.info('{} started with pid: {} (child)'.format(component_name, proc.pid))
            self.components[component_name] = utils.Cache().set(['components', component_name], \
                                                                {'pid': proc.pid, 'process': proc, 'type': utils.Constants.PROCESS})

    def stop_process(self, process_name):
        """"""

        proc = utils.Cache().get(['components', process_name])
        if proc:
            if proc['process'].is_alive():
                proc['process'].join()
                self.logging.info('Component {} stopped'.format(process_name))
                utils.Cache().delete(['components', process_name])
        else:
            self.logging.info('Unknown process {}'.format(process_name))
