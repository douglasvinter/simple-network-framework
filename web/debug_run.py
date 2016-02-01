# -*- coding: utf-8 -*-
"""Simple debug for flask development"""


__author__ = 'douglasvinter@gmail.com'


import logging
from .resource import iotApp


if __name__ == '__main__':
    iotApp.logger.setLevel(logging.DEBUG)
    iotApp.run(host='0.0.0.0', debug=True, use_reloader=True)
