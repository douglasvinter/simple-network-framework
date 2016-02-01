# -*- coding: utf-8 -*-
"""Controller to expose APIs to search for networked devices"""


__author__ = 'douglasvinter'


from flask import jsonify
from ..resource import iotApp
from ..resource import iotApi
from flask import make_response
from flask_restful import Resource


@iotApi.route('network/discovery/<string:protocol>')
class DiscoveryAPI(Resource):
    """Simple GET to return all devices on a local network"""

    def get(self, protocol):
        return make_response(jsonify({protocol: protocol}), 200)

@iotApi.route('network/discovery/debug')
class DebugAPI(Resource):
    """Debug to test the REST API while developing a new network protocol"""
    
    def get (self):
        return make_response(jsonify({protocol: protocol}), 200)