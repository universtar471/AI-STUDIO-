import hashlib
import io
import json

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from services.api import create_app
from services.providers.mock import MockProvider
from tests.integration.run_golden import MANIFEST, GoldenError, load_manifest, main, run_golden


def png(color) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (64, 36), color).save(buffer, 'PNG')
    return buffer.getvalue()


@pytest.fixture
def golden(tmp_path):
    """A two-scene golden set (one scene file missing) with its own manifest."""
    root = tmp_path / 'golden'
    files = {'style/master.png': png('tan'), 'style/floor.png': png('brown'), 'scenes/a.png': png('white'), 'scenes/b.png': png('gray')}
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    sha = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    manifest = {
        'version': 1, 'required_scenes': 3, 'seed': 7,
        'style_pack': {'name': 'Japandi', 'palette': ['#E8DFD3'], 'references': [
            {'file': 'style/master.png', 'role': 'STYLE_MASTER', 'sha256': sha['style/master.png']},
            {'file': 'style/floor.png', 'role': 'FLOOR', 'sha256': sha['style/floor.png']}]},
        'scenes': [
            {'id': 'a', 'name': 'Scene A', 'file': 'scenes/a.png', 'sha256': sha['scenes/a.png'], 'must_keep': ['camera']},
            {'id': 'b', 'name': 'Scene B', 'file': 'scenes/b.png', 'sha256': sha['scenes/b.png']},
            {'id': 'c', 'name': 'Scene C', 'file': 'scenes/c.png', 'sha256': '0' * 64}],
    }
    path = tmp_path / 'golden.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    return root, path


def test_committed_manifest_is_well_formed():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    assert manifest['required_scenes'] == 5
    roles = [r['role'] for r in manifest['style_pack']['references']]
    assert 'STYLE_MASTER' in roles and 4 <= len(roles) <= 6
    for entry in [*manifest['style_pack']['references'], *manifest['scenes']]:
        assert len(entry['sha256']) == 64 and not entry['file'].startswith(('/', '..'))
    assert len({s['id'] for s in manifest['scenes']}) == len(manifest['scenes'])


def test_changed_golden_file_is_rejected(golden):
    root, manifest = golden
    (root / 'scenes/a.png').write_bytes(png('red'))
    with pytest.raises(GoldenError, match='scenes/a.png'):
        load_manifest(root, manifest)


def test_two_runs_write_report_against_previous_run(golden, tmp_path):
    root, manifest = golden
    out = tmp_path / 'runs'
    app = create_app(tmp_path / 'data', providers=[MockProvider(delay=.01)], poll_interval=.001)
    with TestClient(app) as client:
        first = run_golden(client, provider='mock', golden_dir=root, out_root=out, timeout_s=10, poll_s=.01, manifest_path=manifest, log=lambda _: None)
        second = run_golden(client, provider='mock', golden_dir=root, out_root=out, timeout_s=10, poll_s=.01, manifest_path=manifest, log=lambda _: None)
        jobs = client.get('/render/jobs').json()

    assert first != second
    run = json.loads((second / 'run.json').read_text(encoding='utf-8'))
    assert [s['id'] for s in run['scenes']] == ['a', 'b'] and run['missing_scenes'] == ['c']
    assert all(s['state'] == 'REVIEW' and (second / s['output']).is_file() for s in run['scenes'])
    # Every job used the Style Pack, the fixed seed and the requested provider.
    assert len(jobs) == 4 and all(j['provider_id'] == 'mock' and j['request']['seed'] == 7 and j['request']['style_pack_id'] for j in jobs)
    report = (second / 'report.html').read_text(encoding='utf-8')
    assert f'../{first.name}/a.png' in report and 'a_source.png' in report and '<li>camera</li>' in report
    first_report = (first / 'report.html').read_text(encoding='utf-8')
    assert 'chưa có' in first_report


def test_unknown_provider_fails_before_creating_anything(golden, tmp_path):
    root, manifest = golden
    app = create_app(tmp_path / 'data', providers=[MockProvider(delay=.01)], poll_interval=.001)
    with TestClient(app) as client:
        with pytest.raises(GoldenError, match='comfyui'):
            run_golden(client, provider='comfyui', golden_dir=root, out_root=tmp_path / 'runs', manifest_path=manifest, log=lambda _: None)
        assert client.get('/projects').json() == []


def test_cli_reports_missing_golden_images(tmp_path, capsys):
    assert main(['--provider', 'mock', '--golden-dir', str(tmp_path / 'none'), '--api', 'http://127.0.0.1:9']) == 2
    assert 'run_golden:' in capsys.readouterr().err
