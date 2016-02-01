# -*- coding: utf-8 -*-
"""Start Flask WSGI Container"""


__author__ = 'douglasvinter'


from .resource import iotApp


def start_app(**kwargs):
    """Base Werkzeug WSGI server start up"""
    iotApp.logger.info('Registered URIs:')
    for rule in iotApp.url_map.iter_rules():
        if rule.endpoint != 'static':
            iotApp.logger.info('URI->{}'.format(rule))
    # Do not change debug/use_reloader to true.
    # For development/debbuging purprose use debug_run.py instead.
    iotApp.run(host=kwargs.get('host'), port=kwargs.get('port'),
               debug=False, use_reloader=False)
