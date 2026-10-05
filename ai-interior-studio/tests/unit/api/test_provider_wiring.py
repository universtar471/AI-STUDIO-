import time

import httpx
import pytest
from fastapi.testclient import TestClient

from services.api import create_app
from services.core.domain import RenderRequest
from services.providers.gemini import provider as gemini_module
from services.providers.comfyui.provider import ComfyUIProvider


@pytest.fixture(autouse=True)
def offline_comfyui(monkeypatch):
    def offline(request):
        assert request.url.path == '/object_info'
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(ComfyUIProvider, '_client', lambda self: httpx.AsyncClient(
        base_url=self.config.url, transport=httpx.MockTransport(offline)))


@pytest.mark.parametrize('flag,expected', [(None, ['comfyui', 'gemini']), ('0', ['comfyui', 'gemini']),
                                           ('1', ['comfyui', 'gemini', 'mock'])])
def test_mock_provider_only_with_flag(tmp_path, monkeypatch, flag, expected):
    # Synthetic images must never answer a real AUTO request unless a developer asks for them.
    monkeypatch.delenv('AI_STUDIO_ENABLE_MOCK', raising=False)
    if flag is not None:
        monkeypatch.setenv('AI_STUDIO_ENABLE_MOCK', flag)
    with TestClient(create_app(tmp_path)) as client:
        assert [p['id'] for p in client.get('/providers').json()] == expected


def test_default_app_lists_comfyui_and_gemini(tmp_path, monkeypatch):
    monkeypatch.delenv('AI_STUDIO_ENABLE_MOCK', raising=False)
    monkeypatch.setattr(gemini_module, 'get_secret', lambda name: None)
    with TestClient(create_app(tmp_path)) as client:
        providers = {p['id']: p for p in client.get('/providers').json()}
        assert list(providers) == ['comfyui', 'gemini']
        assert providers['gemini']['health']['status'] == 'unavailable'
        assert providers['gemini']['capabilities']['has_usage_cost'] is True
        project = client.post('/projects', json={'name': 'P'}).json()
        scene = client.post(f"/projects/{project['id']}/scenes/import", files={'file': ('v.png', b'img', 'image/png')}).json()
        # Cloud-only with no key: no eligible provider, clear failure instead of a crash.
        job = client.post('/render/jobs', json={'project_id': project['id'], 'mode': 'sketchup_render',
                                                'source': {'scene_id': scene['id']}, 'provider_policy': 'cloud_only'}).json()
        for _ in range(200):
            state = client.get(f"/render/jobs/{job['id']}").json()
            if state['state'] == 'FAILED':
                break
            time.sleep(.01)
        assert state['error']['code'] == 'NO_ELIGIBLE_PROVIDER'


def test_gemini_reads_images_through_running_app(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini_module, 'get_secret', lambda name: 'k' * 20)
    app = create_app(tmp_path)
    with TestClient(app) as client:
        gemini = next(p for p in app.state.manager.providers if p.id == 'gemini')
        providers = {p['id']: p for p in client.get('/providers').json()}
        assert providers['gemini']['health']['status'] == 'ok'
        project = client.post('/projects', json={'name': 'P'}).json()
        scene = client.post(f"/projects/{project['id']}/scenes/import", files={'file': ('v.png', b'scene-bytes', 'image/png')}).json()
        request = RenderRequest(project_id=project['id'], mode='sketchup_render', source={'scene_id': scene['id']})
        artifact_id, data, mime = gemini.images.base_image(request)
        assert artifact_id == scene['rgb_artifact_id'] and data == b'scene-bytes' and mime == 'image/png'
