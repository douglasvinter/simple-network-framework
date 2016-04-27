# -*- coding: utf-8 -*-
"""Controller to expose APIs to search for networked devices"""


__author__ = 'douglasvinter'


from web import iotweb, auth
from flask_restful import Resource, request
from web.services.users import AuthService


@iotweb.router('token', methods=['GET', 'POST'])
@auth.login_required
class Auth(Resource):
    """"""
    
    def get(self):
        token = iotweb.g.user.generate_auth_token(600)
        return {'token': token.decode('ascii'), 'duration': 600}


@iotweb.router(('users/<int:id>', 'users/'), methods=['GET', 'POST', 'PUT', 'DELETE'])
@auth.login_required
class Users(Resource):
    """"""

    def get(self, user_id=None):
        return {'status': 'ok'}, 200

    def post(self):
        return {'status': 'ok'}, 200
    
    def put(self, user_id):
        return {'status': 'ok'}, 200

    def delete(self, user_id):
        return {'status': 'ok'}, 200
