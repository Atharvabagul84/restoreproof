"""TLS-verified app requests and real email OTP through a local SMTP sink."""
from http.cookies import SimpleCookie
import json
import re
import time

from .services import APP_ORIGIN
from ..process import ProcessError


class DependencyUnavailable(RuntimeError):
    """The application could not complete authentication or another dependency."""
    def __init__(self, message, *, http_status=None):
        super().__init__(message)
        self.http_status = http_status


class AppClient:
    def __init__(self, stack):
        self.stack, self.ca = stack, None
        self.cookies = {}

    def clone(self):
        other = AppClient(self.stack)
        other.ca = self.ca
        return other

    def load_certificate(self):
        self.ca = self.stack.db._run('exec', self.stack.owned('gateway'), 'cat', '/tmp/tls.crt').decode()
        if not self.ca.startswith('-----BEGIN CERTIFICATE-----'):
            raise RuntimeError('Gateway certificate unavailable.')

    def request(self, method, path, body=None, *, target='app'):
        if target not in {'app', 'mail', 'auth', 'rest'} or not re.fullmatch(r'/(?!/)[^\r\n]*', path):
            raise ValueError('Only fixed local service requests are allowed.')
        headers = {}
        if target == 'app':
            if not self.ca:
                raise RuntimeError('TLS certificate must be verified before application requests.')
            headers = {'Origin': APP_ORIGIN, 'Cookie': '; '.join(f'{k}={v}' for k, v in self.cookies.items())}
        payload = {'target': target, 'method': method, 'path': path, 'headers': headers, 'ca': self.ca}
        if body is not None:
            payload['body'] = body
        raw = self.stack.db._run('exec', '-i', self.stack.owned('app'), 'node', '/opt/restoreproof/probe.cjs',
                                 input_data=json.dumps(payload, allow_nan=False).encode(), timeout=20)
        response = json.loads(raw)
        if target == 'app':
            for value in response['cookies']:
                cookie = SimpleCookie()
                cookie.load(value)
                for key, morsel in cookie.items():
                    if not morsel['secure'] or not morsel['httponly'] or morsel['path'] != '/':
                        raise RuntimeError('Application returned cookies outside the expected security boundary.')
                    if morsel['max-age'] == '0':
                        self.cookies.pop(key, None)
                    else:
                        self.cookies[key] = morsel.value
        return response

    def wait_ready(self, target, path, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                response = self.request('GET', path, target=target)
                if response['status'] == 200:
                    return
            except (ProcessError, ValueError):
                pass
            time.sleep(0.5)
        raise DependencyUnavailable('Local service readiness deadline exceeded.')

    def login(self, email):
        if email not in {'owner@restoreproof.test', 'outsider@restoreproof.test'}:
            raise ValueError('Only disposable test identities are supported.')
        old_messages = self.request('GET', '/api/v1/messages', target='mail')['body']['messages']
        old_ids = {message['ID'] for message in old_messages}
        try:
            response = self.request('POST', '/api/auth/send-code', {'email': email})
        except ProcessError:
            raise DependencyUnavailable('Application sign-in request could not complete.') from None
        if response['status'] != 200:
            raise DependencyUnavailable('Application sign-in dependency rejected the request.', http_status=response['status'])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            messages = self.request('GET', '/api/v1/messages', target='mail')['body']['messages']
            for message in messages:
                if message['ID'] in old_ids or not any(person['Address'] == email for person in message['To']):
                    continue
                detail = self.request('GET', '/api/v1/message/' + message['ID'], target='mail')['body']
                token = re.search(r'\b(\d{6,10})\b', detail.get('Text', '') or detail.get('HTML', ''))
                if token:
                    verified = self.request('POST', '/api/auth/verify-code', {'email': email, 'token': token[1]})
                    if verified['status'] != 200 or not self.cookies:
                        raise DependencyUnavailable('Application did not establish an authenticated session.')
                    return
            time.sleep(0.25)
        raise DependencyUnavailable('No sign-in code arrived in the isolated email sink.')
