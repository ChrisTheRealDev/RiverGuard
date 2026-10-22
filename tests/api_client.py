"""Provision actual credentials for legacy sensor API regression fixtures.

No authentication dependency is bypassed. New security tests use the plain
TestClient and assert that missing, revoked and mismatched credentials fail.
"""
import re
from fastapi.testclient import TestClient
import core
import security


class AuthenticatedClient(TestClient):
    def __init__(self, app, **kwargs):
        security.initialize()
        super().__init__(app, base_url='http://localhost', client=('127.0.0.1',50000), **kwargs)
        self.tokens = {}
        with core.connect() as con:
            token, session = security.new_session(con,'Regression fixture')
        self.cookies.set(security.COOKIE,token)
        self.headers.update({'Origin':'http://localhost','X-CSRF-Token':session['csrf']})

    def request(self, method, url, **kwargs):
        if str(url).startswith('/api/v1/') and method.upper()!='PUT':
            device = (kwargs.get('json') or {}).get('device_id') or (kwargs.get('params') or {}).get('device_id') or 'test'
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',str(device)):
                device = 'test'
            if device not in self.tokens:
                self.tokens[device] = security.register_device(device)['token']
            headers = dict(kwargs.pop('headers',{}) or {})
            headers.setdefault('Authorization','Bearer '+self.tokens[device])
            kwargs['headers'] = headers
        return super().request(method,url,**kwargs)
