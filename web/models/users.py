# -*- coding: utf-8 -*-


__author__ = 'douglasvinter'


from web import iotweb
from web.models.profiles import Profile
from sqlalchemy_utils import PasswordType
from sqlalchemy.orm import relationship, backref, validates
from sqlalchemy import Column, Integer, Unicode, String, ForeignKey
from itsdangerous import (TimedJSONWebSignatureSerializer
                          as Serializer, BadSignature, SignatureExpired)


class Users(iotweb.db.Model):
    """ORM Model for users
    
    Relationship:
        web.model.profile.Profiles.profile_id
    """

    __tablename__ = 'users'
    __table_args__ = {'extend_existing' : True,
                      'sqlite_autoincrement' : True}

    id = Column(Integer, primary_key=True)
    name = Column(Unicode(70))
    fullname = Column(Unicode(120))
    email = Column(Unicode(120), unique=True)
    username = Column(String(7), index=True, unique=True)
    password = Column(PasswordType(schemes=['pbkdf2_sha512']))
    profile_id = Column(Integer, ForeignKey('profile.profile_id'))
    profile = relationship(Profile, backref=backref('users', uselist=True))

    def __repr__(self):
        return '<User(Username: {})'.format(self.name)

    @validates('username')
    def validate_username(self, key, username):
        assert len(username) == 7
        return username 

    def generate_auth_token(self, expiration=600):
        """"""
        s = Serializer(iotweb.config['SECRET_KEY'], expires_in=expiration)
        return s.dumps({'id': self.id})
    
    @staticmethod
    def verify_password(password):
        pass

    @staticmethod
    def verify_auth_token(token):
        """"""
        s = Serializer(iotweb.config['SECRET_KEY'])
        try:
            data = s.loads(token)
        except SignatureExpired:
            return None
        except BadSignature:
            return None
        return Users.query \
            .join(Users.profile) \
            .filter(Users.id==data['id'], \
                    Profile.id==Users.profile_id)
