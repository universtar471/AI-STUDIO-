import time

from fastapi.testclient import TestClient

from services.api import create_app
from services.core.domain import JobProgressEvent
from services.providers.mock import MockProvider


def wait_state(client, job_id, state):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = client.get(f'/render/jobs/{job_id}').json()
        if job['state'] == state:
            return job
        time.sleep(.005)
    raise AssertionError(job)


def test_full_api_lifecycle(tmp_path):
    app = create_app(tmp_path, providers=[MockProvider(delay=.01)], poll_interval=.001)
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        project = client.post('/projects', json={'name': 'Apartment'}).json()
        scene_response = client.post(f"/projects/{project['id']}/scenes/import", data={'name': 'Living'}, files={'file': ('view.png', b'source', 'image/png')})
        assert scene_response.status_code == 201, scene_response.text
        scene = scene_response.json()
        pack = client.post('/style-packs', json={'name': 'Warm', 'project_id': project['id']}).json()
        updated = client.post(f"/style-packs/{pack['id']}/references", data={'role': 'STYLE_MASTER'}, files={'file': ('ref.png', b'reference', 'image/png')})
        assert updated.status_code == 201, updated.text
        assert updated.json()['version'] == 2
        body = {'project_id': project['id'], 'mode': 'sketchup_render', 'source': {'scene_id': scene['id']}, 'style_pack_id': pack['id'], 'prompt': {'raw_text': 'Warm interior'}}
        with client.websocket_connect('/ws/jobs') as ws:
            response = client.post('/render/jobs', json=body)
            assert response.status_code == 201, response.text
            job = response.json()
            event = JobProgressEvent.model_validate(ws.receive_json())
            assert event.job_id == job['id']
        review = wait_state(client, job['id'], 'REVIEW')
        assert client.post(f"/render/jobs/{job['id']}/finalize", json={}).status_code == 409
        assert client.post(f"/render/jobs/{job['id']}/cancel").status_code == 409
        assert review['request']['style_pack_version'] == 2
        assert len(review['request']['references']) == 1
        artifact = review['result']['artifact_ids'][0]
        assert client.get(f'/artifacts/{artifact}').status_code == 200
        assert client.get(f'/artifacts/{artifact}/file').content.startswith(b'\x89PNG')
        child = client.post(f"/render/jobs/{job['id']}/retry").json()
        assert child['retry_of'] == job['id']
        assert client.get(f"/render/jobs/{job['id']}").json()['state'] == 'RETRY'
        wait_state(client, child['id'], 'REVIEW')
        assert client.post(f"/render/jobs/{child['id']}/approve").json()['state'] == 'APPROVED'
        final = client.post(f"/render/jobs/{child['id']}/finalize", json={})
        assert final.status_code == 201, final.text
        wait_state(client, final.json()['id'], 'REVIEW')
        assert client.get('/providers').json()[0]['id'] == 'mock'
        assert client.get('/openapi.json').status_code == 200
        assert client.get('/projects/missing').status_code == 404


def test_invalid_request_and_finalize_guard(tmp_path):
    with TestClient(create_app(tmp_path, providers=[MockProvider(delay=10)])) as client:
        assert client.post('/projects', json={'name': '', 'unknown': True}).status_code == 422
        assert client.post('/render/jobs', json={}).status_code == 422
        assert client.post('/render/jobs/missing/cancel').status_code == 404


def test_cross_project_inputs_and_bad_uploads(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        first = client.post('/projects', json={'name': 'First'}).json()['id']
        second = client.post('/projects', json={'name': 'Second'}).json()['id']
        scene = client.post(f'/projects/{first}/scenes/import', files={'file': ('view.png', b'image', 'image/png')}).json()
        response = client.post('/render/jobs', json={'project_id': second, 'mode': 'sketchup_render', 'source': {'scene_id': scene['id']}})
        assert response.status_code == 422
        assert response.json()['code'] == 'PROJECT_MISMATCH'
        assert client.post(f'/projects/{first}/scenes/import', files={'file': ('bad.txt', b'data', 'text/plain')}).status_code == 422
        assert client.post(f'/projects/{first}/scenes/import', data={'camera': '{bad'}, files={'file': ('a.png', b'data', 'image/png')}).status_code == 422


def test_websocket_disconnect_releases_subscription(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app) as client:
        for _ in range(5):
            with client.websocket_connect('/ws/jobs'):
                pass
        assert not app.state.manager.subscribers
