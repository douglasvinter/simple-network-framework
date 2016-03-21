# -*- coding: utf-8 -*-
"""ORM Entity model for Users"""


__author__ = 'douglasvinter'


from web.iotweb import db


class Users(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode(70), index=True)
    lastname = db.Column(db.Unicode(70), index=True)
    email = db.Column(db.String(120), index=True)
    username = db.Column(db.String(32), index=True)
    password_hash = db.Column(db.String(128))
    permissions_id = db.Column(Integer, ForeignKey('permissions.id'))