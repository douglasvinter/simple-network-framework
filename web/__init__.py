from types import MethodType
from flask import Flask
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy


class IotApp(Flask):
    """"""

    _instance = None
    _BASE_API_URI = '/iot/api/v0.1/'

    def __new__(cls, *args, **kwargs):
        """"""
        if not cls._instance:
            cls._instance = super(IotApp, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __repr__(self):
        return '<{} instance at {}>'.format(self.__class__.__name__,
            id(self))

    def __str__(self):
        return '<{} instance at {}>'.format(self.__class__.__name__,
            id(self))
    
    def __init__(self, app_name='IoT REST API', cfg_from_object='web.config', api_uri='/iot/api/v0.1/'):
        Flask.__init__(self, import_name = app_name, static_path=None, 
                       static_url_path=None, static_folder=None,
                       template_folder=None, instance_path=None,
                       instance_relative_config=False)
        self._BASE_API_URI = api_uri
        self.config.from_object(cfg_from_object)
        self.db = SQLAlchemy(self)
        self.api = Api(self)
        self.router = MethodType(self.route, self.api)

    @staticmethod
    def route(api, uris, **options):
        def decorate(resource):
            if isinstance(uris, (tuple, list)):
                uri = lambda uri: IotApp._BASE_API_URI + uri
                urls = map(uri, uris)
            else:
                urls = [IotApp._BASE_API_URI+uris]
            api.add_resource(resource, *urls, **options)
        return decorate


iotweb = IotApp()
