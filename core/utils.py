# -*- coding: utf-8 -*-
"""Utility module for core functions

This module contains the enum mapping for components and
the hearth of application, which is the components that will be
managed by the core on start() signal.
"""


__author__ = 'douglasvinter'


import yaml
import pdb
from collections import MutableMapping


class Constants(object):
    THREAD = 'THREAD'
    PROCESS = 'PROCESS'
    THREAD_POOL = 'THREAD_POOL'
    PROCESS_POOL = 'PROCESS_POOL'
 
 
class Cache(MutableMapping):
    """Super set"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        """Singleton cache"""
        if not cls._instance:
            cls._instance = super(Cache, cls).__new__(cls, *args, **kwargs)
        else:
            super(Cache, cls).__init__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, *args, **kwargs):
        self.__dict__.update(*args, **kwargs)

    def __setitem__(self, key, value):
        self.__dict__[key] = value

    def get(self, key):
        if '.' in key:
            key = key.split('.')
        elif '.' not in key and isinstance(key, (str, unicode)):
            key = [key]
        return self.__getitem__(key)

    def set(self, key, value):
        if '.' in key:
            key = key.split('.')
        elif '.' not in key and isinstance(key, (str, unicode)):
            key = [key]
        self.__getitem__(key[:-1])[key[-1]] = value

    def delete(self, key):
        if '.' in key:
            key = key.split('.')
        elif '.' not in key and isinstance(key, (str, unicode)):
            key = [key]
        del self.__getitem__(key[:-1])[key[-1]]

    def __getitem__(self, key):
        return reduce(lambda d, k: d[k], key, self.__dict__)
            
    def __delitem__(self, key):
        return

    def __iter__(self):
        return iter(self.__dict__)

    def __len__(self):
        return len(self.__dict__)

    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        return '{}, Cache({})'.format(super(Cache, self).__repr__(), 
                                  self.__dict__)

def parse_config():
    with open('config.yml') as f:
        return Cache(config=yaml.safe_load(f))
