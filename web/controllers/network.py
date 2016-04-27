# -*- coding: utf-8 -*-
"""Controller to expose APIs to search for networked devices"""


__author__ = 'douglasvinter'


from web import iotweb, auth
from flask_restful import Resource

@iotweb.router(('network/discovery', 'network/discovery/<string:serviceName>'), methods=['GET', 'POST'])
@auth.login_required
class NetworkDiscovery(Resource):
    """Simple GET to return all devices on a local network"""
            
    def get(self, serviceName=None):
        return {'status': 'ok'}, 200
    
    def post(self):
        return {'status': 'ok'}, 200
