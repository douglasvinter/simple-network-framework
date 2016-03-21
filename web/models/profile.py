# -*- coding: utf-8 -*-
"""ORM Entity model for Users"""


__author__ = 'douglasvinter'


from web.iotweb import db


class Permissions(db.Model):
    __tablename__ = 'permissions'

    id = db.Column(db.Integer, primary_key=True)
    hash_key = db.Column(db.String(256))
    authority = db.Column(db.Integer)
    authority_desc = db.Column(db.String(256))
    
    
