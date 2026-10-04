"""Gate G1 against a real backend process (uvicorn + MockProvider, default 2 s delay)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from websockets.sync.client import connect

from tests.integration.conftest import FAKE_GEMINI_KEY, PROJECT_ROOT
from tests.integration.secret_scan import scan

FULL_PATH = ['DRAFT', 'QUEUED', 'RUNNING', 'REVIEW', 'APPROVED']


def _states(job: dict) -> list[str]:
    history = job['history']
    return [history[0]['from_state'], *(change['to_state'] for change in history)]


def _setup_project(backend) -> tuple[str, str, str]:
    project = backend.client.post('/projects', json={'name': 'G1 apartment'}).json()
    scene = backend.client.post(
        f"/projects/{project['id']}/scenes/import", data={'name': 'Living room'},
        files={'file': ('living.png', b'\x89PNG fake scene', 'image/png')},
    )
    assert scene.status_code == 201, scene.text
    pack = backend.client.post('/style-packs', json={'name': 'Warm oak', 'project_id': project['id']}).json()
    ref = backend.client.post(
        f"/style-packs/{pack['id']}/references", data={'role': 'STYLE_MASTER'},
        files={'file': ('oak.png', b'\x89PNG fake reference', 'image/png')},
    )
    assert ref.status_code == 201, ref.text
    return project['id'], scene.json()['id'], pack['id']


def _job_body(project_id, scene_id, pack_id):
    return {'project_id': project_id, 'mode': 'sketchup_render', 'source': {'scene_id': scene_id},
            'style_pack_id': pack_id, 'prompt': {'raw_text': 'Warm oak living room'}}


def _artifact_bytes(backend, artifact_id) -> bytes:
    response = backend.client.get(f'/artifacts/{artifact_id}/file')
    assert response.status_code == 200, response.text
    return response.content


def test_g1_lifecycle_retry_and_events(backend_factory, tmp_path):
    backend = backend_factory()
    project_id, scene_id, pack_id = _setup_project(backend)

    events = []
    with connect(f'ws://127.0.0.1:{backend.port}/ws/jobs', open_timeout=10) as ws:
        job = backend.client.post('/render/jobs', json=_job_body(project_id, scene_id, pack_id)).json()
        while True:
            event = json.loads(ws.recv(timeout=20))
            if event['job_id'] == job['id']:
                events.append(event)
                if event['state'] == 'REVIEW':
                    break
    assert {e['type'] for e in events} == {'job.progress'}
    assert [e['state'] for e in events][-1] == 'REVIEW'
    assert 'RUNNING' in {e['state'] for e in events}

    first = backend.wait_state(job['id'], 'REVIEW')
    first_artifact = first['result']['artifact_ids'][0]
    first_bytes = _artifact_bytes(backend, first_artifact)
    meta = backend.client.get(f'/artifacts/{first_artifact}').json()
    assert hashlib.sha256(first_bytes).hexdigest() == meta['sha256']

    # Retry: new job linked to the old one; old job closed in RETRY.
    child = backend.client.post(f"/render/jobs/{job['id']}/retry").json()
    assert child['id'] != job['id']
    assert child['retry_of'] == job['id']
    assert child['revision'] == first['revision'] + 1
    assert backend.client.get(f"/render/jobs/{job['id']}").json()['state'] == 'RETRY'

    backend.wait_state(child['id'], 'REVIEW')
    approved = backend.client.post(f"/render/jobs/{child['id']}/approve").json()
    assert approved['state'] == 'APPROVED'
    assert _states(approved) == FULL_PATH

    # Old artifact is immutable: same bytes, same checksum, old job still points at it.
    old = backend.client.get(f"/render/jobs/{job['id']}").json()
    assert old['result']['artifact_ids'] == [first_artifact]
    assert _artifact_bytes(backend, first_artifact) == first_bytes

    # Snapshots for both jobs on disk.
    for job_id in (job['id'], child['id']):
        folder = backend.data_root / 'projects' / project_id / 'jobs' / job_id
        assert sorted(p.name for p in folder.iterdir()) == sorted(
            ['request.json', 'provider_request.json', 'prompt.txt', 'refs.json', 'metrics.json'])

    backend.kill()
    leaks = scan([backend.data_root, backend.log_path], extra_secrets=(FAKE_GEMINI_KEY,))
    assert not leaks, leaks


def test_g1_hard_restart_loses_no_job(backend_factory):
    backend = backend_factory()
    project_id, scene_id, pack_id = _setup_project(backend)
    body = _job_body(project_id, scene_id, pack_id)

    done = backend.client.post('/render/jobs', json=body).json()
    backend.wait_state(done['id'], 'REVIEW')
    running = backend.client.post('/render/jobs', json=body).json()
    queued = backend.client.post('/render/jobs', json=body).json()
    backend.wait_state(running['id'], 'RUNNING')
    assert backend.client.get(f"/render/jobs/{queued['id']}").json()['state'] == 'QUEUED'
    before = {j['id'] for j in backend.client.get('/render/jobs', params={'project_id': project_id}).json()}
    backend.kill()  # crash mid-run

    restarted = backend_factory()
    after = {j['id'] for j in restarted.client.get('/render/jobs', params={'project_id': project_id}).json()}
    assert before <= after

    assert restarted.client.get(f"/render/jobs/{done['id']}").json()['state'] == 'REVIEW'
    failed = restarted.wait_state(running['id'], 'FAILED')
    assert failed['error']['code'] == 'PROCESS_RESTARTED'
    restarted.wait_state(queued['id'], 'REVIEW')

    # The interrupted job is recoverable through retry.
    child = restarted.client.post(f"/render/jobs/{running['id']}/retry").json()
    assert child['retry_of'] == running['id']
    restarted.wait_state(child['id'], 'REVIEW')
    assert restarted.client.post(f"/render/jobs/{child['id']}/approve").json()['state'] == 'APPROVED'


def test_contracts_marked_approved():
    text = (PROJECT_ROOT / 'docs' / 'contracts.md').read_text(encoding='utf-8')
    assert '**đã duyệt' in text


def test_secret_scanner_detects_samples(tmp_path):
    sample = tmp_path / 'log.txt'
    sample.write_text('\n'.join([
        'ok line',
        'key=' + 'AIza' + 'A' * 35,
        'Authorization: Bearer ' + 'x' * 30,
        'token sk-' + 'b' * 24,
        'gemini AQ.' + 'c' * 24,
    ]), encoding='utf-8')
    kinds = sorted(f.kind for f in scan([sample]))
    assert kinds == ['bearer_token', 'google_api_key', 'google_aq_key', 'openai_key']
    assert all(f.line > 1 for f in scan([sample]))


def test_repo_has_no_leaked_keys():
    assert not scan([PROJECT_ROOT]), scan([PROJECT_ROOT])
