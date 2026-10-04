import sys
from types import SimpleNamespace

from services.core import secrets
from services.core.secrets import get_secret, redact, set_secret


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get_password(self, service, name):
        return self.store.get((service, name))

    def set_password(self, service, name, value):
        self.store[(service, name)] = value


def test_env_wins_then_keyring(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setitem(sys.modules, 'keyring', fake)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    assert get_secret('gemini') is None
    set_secret('gemini', ' from-keyring ')
    assert fake.store[(secrets.KEYRING_SERVICE, 'gemini')] == 'from-keyring'
    assert get_secret('gemini') == 'from-keyring'
    monkeypatch.setenv('GOOGLE_API_KEY', 'from-google-env')
    assert get_secret('gemini') == 'from-google-env'
    monkeypatch.setenv('GEMINI_API_KEY', 'from-gemini-env')
    assert get_secret('gemini') == 'from-gemini-env'


def test_broken_keyring_means_no_key(monkeypatch):
    def boom(*_):
        raise RuntimeError('no backend')
    monkeypatch.setitem(sys.modules, 'keyring', SimpleNamespace(get_password=boom))
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    assert get_secret('gemini') is None


def test_redact():
    assert redact('key=supersecret123 again supersecret123', ['supersecret123', None]) == 'key=[REDACTED] again [REDACTED]'
    assert redact('short abc', ['abc']) == 'short abc'  # too short to be a real key; avoid mangling text
