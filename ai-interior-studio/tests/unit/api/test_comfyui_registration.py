import json

import httpx
import pytest
from fastapi.testclient import TestClient

from services.api import create_app
from services.core.domain import RenderRequest
from services.providers.comfyui.provider import ComfyUIProvider
from services.providers.mock import MockProvider
from test_api import wait_state


def test_default_providers_offline_comfyui_and_storage_images(tmp_path, monkeypatch):
    calls = []
    def offline(request):
        calls.append(request.url.path)
        assert request.url.path == '/object_info'
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(ComfyUIProvider, '_client', lambda self: httpx.AsyncClient(
        base_url=self.config.url, transport=httpx.MockTransport(offline)))
    path = tmp_path / 'comfy.json'
    path.write_text(json.dumps({'url': 'http://comfy.invalid:9999'}))
    monkeypatch.setenv('AI_STUDIO_COMFYUI_CONFIG', str(path))
    monkeypatch.setenv('AI_STUDIO_ENABLE_MOCK', '1')
    app = create_app(tmp_path / 'data', poll_interval=.001)
    with TestClient(app) as client:
        response = client.get('/providers')
        assert response.status_code == 200
        assert [p['id'] for p in response.json()] == ['comfyui', 'mock']
        assert response.json()[0]['health']['status'] == 'unavailable'
        comfy = app.state.manager.providers[0]
        assert comfy.config.url == 'http://comfy.invalid:9999'
        project = client.post('/projects', json={'name': 'Test'}).json()
        scene = client.post(f"/projects/{project['id']}/scenes/import",
                            files={'file': ('base.png', b'base', 'image/png')}).json()
        body = {'project_id': project['id'], 'mode': 'sketchup_render', 'source': {'scene_id': scene['id']}}
        assert comfy.images.base_image(RenderRequest(**body))[1:] == (b'base', 'image/png')
        assert comfy.images.image(scene['rgb_artifact_id']) == (b'base', 'image/png')
        job = client.post('/render/jobs', json=body)
        assert job.status_code == 201
        wait_state(client, job.json()['id'], 'REVIEW')
        assert calls == ['/object_info']


@pytest.mark.parametrize('env,explicit,expected', [(None, None, 600), ('720', None, 720), ('720', 15, 15)])
def test_job_timeout_configuration(tmp_path, monkeypatch, env, explicit, expected):
    monkeypatch.delenv('AI_STUDIO_JOB_TIMEOUT_S', raising=False)
    if env is not None:
        monkeypatch.setenv('AI_STUDIO_JOB_TIMEOUT_S', env)
    kwargs = {} if explicit is None else {'timeout': explicit}
    app = create_app(tmp_path, providers=[MockProvider()], **kwargs)
    with TestClient(app):
        assert app.state.manager.timeout == expected
