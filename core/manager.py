# -*- coding: utf-8 -*-
"""Manager module

Manager to start components, open sockets, manage the scheduler,
register new tasks and etc.
"""


__author__ = 'douglasvinter'


import os
import gc
import sys
import time
import signal
import logging
import threading
import importlib
import multiprocessing
from .util import PoolComponent
from .util import ComponentEnum
from .util import ProcessComponent
from .util import COMPONENTS


class AppManager(threading.Thread):
    """Components manager, semaphores and data sharing.

    This class is a singleton instance which provides data sharing
    between the components, and manage it.

    The Manager will also provide a WatchDog method for alerting in case
    any component may become zombie/defunct.
    """

    _instance = None

    def __new__(cls):
        """Avoids another core to be initialized."""
        if not cls._instance:
            cls._instance = super(AppManager, cls).__new__(cls)
        return cls._instance

    def __repr__(self):
        return '<{} Singleton instance at {}>'.format(self.__class__.__name__,
                                                      id(self))

    def __str__(self):
        return 'appManager Class'

    def __init__(self):
        self.components = {}
        self.logging = logging.getLogger('AppManager')
        self.manager_event = threading.Event()
        self.manager_event.set()
        threading.Thread.__init__(self)

    @staticmethod
    def get_instance():
        """Gets class instance."""
        if not AppManager._instance:
            AppManager._instance = AppManager()
        return AppManager._instance

    def run(self):
        """Core management and engine-start."""
        self.logging.info('IoT Manager started at pid: {}'.format(os.getpid()))
        self.logging.info('Starting components...')
        self.start_framework()
        
        while self.manager_event.isSet():
            # Do Manager Stuff
            # Force Garbage Collector to clean tracked garbage from this
            # part of the python runtime (PVM)
            gc.collect()
            time.sleep(5)
        self.shutdown()
        sys.exit(1)

    def shutdown(self):
        """ Shutdown application gracefully providing exit signal."""
        for component in self.components.keys():
            if component.name == ComponentEnum.WORKER_POOL:
                # stop threading event
                component.main_event_loop.clear()
            elif component.name == ComponentEnum.SOCKET_POOL:
                component.shutdown_streams()
                component.main_event_loop.clear()
            elif comp_type == ComponentEnum.STANDALONE_PROCESS:
                os.killpg(os.getpgid(pro.pid), signal.SIGTERM)

    def start_framework(self):
        """Start all registered / non - started workers.

        Check core.util.COMPONENTS to add new components.
        """
        for components in COMPONENTS.keys():
            comp_type = COMPONENTS[components]['enum']
            if comp_type == ComponentEnum.STANDALONE_PROCESS:
                self.start_process(components)
            elif comp_type == ComponentEnum.WORKER_POOL:
                pass
            elif comp_type == ComponentEnum.SOCKET_POOL:
                pass
            elif comp_type == ComponentEnum.THREAD_POOL:
                pass

    def start_process(self, component_name):
        """Starts a child process component and update component mapping object."""
        name = COMPONENTS[component_name]['name']
        method = COMPONENTS[component_name]['start']
        kwargs = COMPONENTS[component_name]['kwargs']
        importPath = COMPONENTS[component_name]['importPath']
        try:
            imp = importlib.import_module(importPath)
            proc = multiprocessing.Process(target=getattr(imp, method),
                                           kwargs=kwargs)
            proc.start()
        except (ImportError, multiprocessing.ProcessError) as err:
            self.logging.critical('Error starting {}'.format(name))
            self.logging.critical(err)
        else:
            self.logging.info('{} started with pid: {} (child)'.format(name, proc.pid))
            self.components[component_name] = ProcessComponent(pid=proc.pid, process=proc)

    def stop_process(self, process_name):
        raise NotImplementedError

    def stop_worker(self, worker_name):
        raise NotImplementedError

    def stop_pool(self, worker_name):
        raise NotImplementedError