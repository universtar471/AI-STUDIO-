"""Run the real backend as a separate uvicorn process and talk to it over HTTP/WebSocket."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Planted in the server environment; it must never show up in logs or data.
FAKE_GEMINI_KEY = 'AIza' + 'IntegrationFakeKeyDoNotLeak_000000'[:35].ljust(35, '0')


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _offline_comfyui_config(data_root: Path) -> Path:
    path = data_root.parent / 'comfyui-offline.json'
    path.write_text('{"url": "http://127.0.0.1:9"}', encoding='utf-8')
    return path


class Backend:
    def __init__(self, data_root: Path, log_path: Path):
        self.data_root, self.log_path = data_root, log_path
        self.port = _free_port()
        self.url = f'http://127.0.0.1:{self.port}'
        env = {**os.environ, 'AI_STUDIO_DATA_ROOT': str(data_root), 'GEMINI_API_KEY': FAKE_GEMINI_KEY, 'GOOGLE_API_KEY': FAKE_GEMINI_KEY,
               # Jobs run on the mock; ComfyUI points at a closed port so a real local ComfyUI is never used.
               'AI_STUDIO_ENABLE_MOCK': '1', 'AI_STUDIO_COMFYUI_CONFIG': str(_offline_comfyui_config(data_root))}
        self._log = open(log_path, 'ab')
        self.process = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'services.api:create_app', '--factory', '--host', '127.0.0.1', '--port', str(self.port)],
            cwd=PROJECT_ROOT, env=env, stdout=self._log, stderr=subprocess.STDOUT,
        )
        self.client = httpx.Client(base_url=self.url, timeout=10)
        deadline = time.monotonic() + 30
        while True:
            if self.process.poll() is not None:
                raise RuntimeError(f'Backend exited early, see {log_path}')
            try:
                if self.client.get('/health').status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if time.monotonic() > deadline:
                self.kill()
                raise RuntimeError(f'Backend did not become healthy, see {log_path}')
            time.sleep(.1)

    def wait_state(self, job_id: str, *states: str, timeout: float = 20) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            job = self.client.get(f'/render/jobs/{job_id}').json()
            if job['state'] in states:
                return job
            if time.monotonic() > deadline:
                raise AssertionError(f'Job {job_id} stuck in {job["state"]}, expected {states}')
            time.sleep(.05)

    def kill(self) -> None:
        """Hard kill (TerminateProcess on Windows): no graceful shutdown, like a crash or power loss."""
        self.client.close()
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(10)
        self._log.close()


@pytest.fixture
def backend_factory(tmp_path):
    started: list[Backend] = []
    data_root = tmp_path / 'data'

    def start() -> Backend:
        backend = Backend(data_root, tmp_path / 'server.log')
        started.append(backend)
        return backend

    yield start
    for backend in started:
        backend.kill()
