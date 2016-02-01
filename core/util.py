# -*- coding: utf-8 -*-
"""Utility module for core functions

This module contains the enum mapping for components and
the hearth of application, which is the components that will be
managed by the core on start() signal.
"""


__author__ = 'douglasvinter'


import json
import collections


class ComponentEnum(object):
    """Enum class to map managed components"""

    WORKER_POOL = 0x01
    SOCKET_POOL = 0x02
    THREAD_POOL = 0x03
    STANDALONE_PROCESS = 0x4


class PoolComponent(collections.namedtuple('poolComponent', ('main_event_loop'), verbose=False)):
    """Skeleton Class to add new worker pool components to manager"""
    workers = []

# processComponent - Skeleton Class to add parallel components working
# i.e Web RESTful API
ProcessComponent = collections.namedtuple('ProcessComponent', ('pid', 'process'), verbose=False)


# IoT Component mapping - Main dictionary containing all process/threads that will be used
# and managed by appManager.
# Keep in mind that WebApi is a independent WSGI Container that provides a friendly debug
# for development, so if you're intended to use debug mode, use the script debug_run.py
# or you will force the whole application to reload, including appManager.
COMPONENTS = {'webApi': \
                {'enum': ComponentEnum.STANDALONE_PROCESS, 'name': 'IoT Simple REST API', \
                 'importPath': 'web.webrun', 'start': 'start_app', \
                 'kwargs': {'logger_name': 'IoT REST API', 'host': '0.0.0.0', 'port': 5000}
                },
            }

class Serializer(object):
    """Simple JSON Serialization class

    This class provides simple data serialization by just inheriting it
    and calling the serialize() method.

    Example:
        Class NetworkResponse(Serializer):
            def __init__(self):
                self.ip = '192.168.0.1'
                self.port = '192.168.0.1'

        a = NetworkResponse()
        a.serialize()
        '{"ip": "192.168.0.1", "port": "2020"}'
    """

    def serialize(self):
        """Serialization method that expects a class with __init__ containing
        the values to be serialized
        """
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True)
