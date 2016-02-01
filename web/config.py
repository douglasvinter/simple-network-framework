# -*- coding: utf-8 -*-
"""Configuration object for flask, database only"""


__author__ = 'douglasvinter'


import os
basedir = os.path.abspath(os.path.dirname(__file__))

SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'iot.db')
