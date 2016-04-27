"""Controller to expose APIs to search for networked devices"""


__author__ = 'douglasvinter'


from web import iotweb, auth
from web.models.users import Users


class AuthService(object):
    """"""

    @auth.verify_password
    def validate_credcentials(username_or_token, password):
        """"""
        user = Users.verify_auth_token(username_or_token)
        if not user:
            # try to authenticate with username/password
            user = Users.query.filter_by(Users.username==username_or_token).first()
        if not user or not Users.verify_password(password):
            return False
        iotweb.g.user = user
        return True


class UserManagement(object):
    """"""
    
    def add_user(self): pass
    def del_user(self): pass
    def update_user(self): pass
