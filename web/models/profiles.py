# -*- coding: utf-8 -*-


__author__ = 'douglasvinter'


from web import iotweb
from sqlalchemy import Column, Integer, Unicode


class Profile(iotweb.db.Model):
    """ORM Model for users profiles

    Relationship:
        web.model.users.User.profile_id
    """

    __tablename__ = 'permissions'
    __table_args__ = {'extend_existing' : True,
                      'sqlite_autoincrement' : True}

    def __repr__(self):
        return '<Profile(name: {})'.format(self.name)

    id = Column(Integer, primary_key=True)
    name = Column(Unicode(25))
    desc = Column(Unicode(255))
    profile_id = Column(Integer, unique=True)
