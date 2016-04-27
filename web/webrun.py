# -*- coding: utf-8 -*-
"""Start Flask WSGI Container"""


__author__ = 'douglasvinter'

from web import iotweb
from controllers import *

def start_app(**kwargs):
    """Base Werkzeug WSGI server start up"""

    iotweb.logger.info('Registered URIs:')
    for rule in iotweb.url_map.iter_rules():
        if rule.endpoint != 'static':
            iotweb.logger.info('URI->{}'.format(rule))
    # Do not change debug/use_reloader to true.
    # For development/debbuging purprose use debug_run.py instead.
    iotweb.run(host=kwargs.get('host'), port=kwargs.get('port'),
               debug=True, use_reloader=False)

start_app(**{'host': '127.0.0.1', 'port': 5000})