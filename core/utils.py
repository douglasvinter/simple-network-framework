# -*- coding: utf-8 -*-
"""Utility module for core functions

This module contains the enum mapping for components and
the hearth of application, which is the components that will be
managed by the core on start() signal.
"""


__author__ = 'douglasvinter'


import json
import yaml
import collections


class ComponentEnum(object):
    """Enum class to map managed components"""
    STANDALONE_PROCESS = 0x01

class PoolComponent(collections.namedtuple('poolComponent', ('main_event_loop'), verbose=False)):
    """Skeleton Class to add new worker pool components to manager"""
    workers = []

# processComponent - Skeleton Class to add parallel components working
# i.e Web RESTful API
ProcessComponent = collections.namedtuple('ProcessComponent', ('pid', 'process'), verbose=False)

def parse_config():
    cfg = None
    with open('config.yml') as f:
        cfg = yaml.safe_load(f)
    return ConfigAttributes(cfg)

class ConfigAttributes(dict):
    """"""

    def __init__(self, *args, **kwargs):
        """"""
        super(ConfigAttributes, self).__init__(*args, **kwargs)
        self.__dict__ = self

    def __repr__(self):
        """"""
        return '<{} IoT Configuration at {}>'.format(self.__class__.__name__,
                                                      id(self))

    def __str__(self):
        """"""
        return '<{} IoT Configuration at {}>'.format(self.__class__.__name__,
                                                      id(self))