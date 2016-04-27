# -*- coding: utf-8 -*-
"""Configuration object for flask"""


__author__ = 'douglasvinter'


import os
basedir = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = 'Dummy Secret key in case you forgot to set on config.yml'
SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'iot.db')
