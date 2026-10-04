"""API keys come from the environment or the OS keyring, never from files in the repo or project folder."""
from __future__ import annotations

import os
from typing import Iterable

KEYRING_SERVICE = 'ai-interior-studio'

# name -> environment variables checked in order
ENV_VARS: dict[str, tuple[str, ...]] = {
    'gemini': ('GEMINI_API_KEY', 'GOOGLE_API_KEY'),
}


def _keyring():
    try:
        import keyring  # optional at runtime: missing backend just means "no key"
        return keyring
    except Exception:
        return None


def get_secret(name: str) -> str | None:
    """Environment first (easy to override per session), then the Windows Credential Manager via keyring."""
    for var in ENV_VARS.get(name, (name.upper(),)):
        value = os.environ.get(var, '').strip()
        if value:
            return value
    backend = _keyring()
    if backend is None:
        return None
    try:
        value = backend.get_password(KEYRING_SERVICE, name)
    except Exception:
        return None
    return value.strip() if value else None


def set_secret(name: str, value: str) -> None:
    backend = _keyring()
    if backend is None:
        raise RuntimeError('keyring is not available on this system')
    backend.set_password(KEYRING_SERVICE, name, value.strip())


def redact(text: str, secrets: Iterable[str | None]) -> str:
    """Remove secret values from text before it reaches a log, error or snapshot."""
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, '[REDACTED]')
    return text
