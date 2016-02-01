# -*- coding: utf-8 -*-
"""IoT REST API Configuration"""


__author__ = 'douglasvinter'


from flask import Flask
from flask import make_response
from types import MethodType
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy


# Flask Application
iotApp = Flask('IoT REST API')

# restful api wrapper for flask
iotApi = Api(iotApp)

# Base api request Uri
baseApiUri = '/iot/api/v0.1/'

# App database, sqlite database
iotDb = SQLAlchemy(iotApp)

# Database config file, check config.py
# for further information
# Im using sqlite3 for this application
iotApp.config.from_object('web.config')

def route(self, addNewUri):
    """Wrapper for flask api.route"""
    def wrapper(cls):
        registerUri = baseApiUri + addNewUri
        self.add_resource(cls, registerUri)
        return cls
    return wrapper

# Add route wrapper to api object
iotApi.route = MethodType(route, iotApi)

@iotApp.errorhandler(400)
def bad_request(errcode):
    """Wrapper to set a default error handler for bad request."""
    return make_response(errcode, 400)


@iotApp.errorhandler(404)
def not_found(errcode):
    """Wrapper to set a default error handler for resources not found."""
    return make_response(errcode, 404)

@iotApp.after_request
def after_request(response):
    """wrapper for HTTP headers - Enable CORS"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response

import controllers.discovery