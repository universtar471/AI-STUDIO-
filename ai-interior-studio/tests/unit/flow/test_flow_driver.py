"""NodeFlowDriver against a stand-in run.js: the real driver (and the user's Flow account) is never touched."""
import io
import json
import shutil

from PIL import Image
import pytest

from services.providers.flow import FlowError, NodeFlowDriver
from services.providers.flow.driver import EXPORT_SIZES, crop_to_ratio, nearest_ratio

NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node is not installed')

# Checks what the real driver checks that this app controls, then plays the driver's outputs.
FAKE_RUN = r"""
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const dir = process.argv[2];
const job = JSON.parse(fs.readFileSync(path.join(dir, 'request.json'), 'utf8'));
const sha = f => crypto.createHash('sha256').update(fs.readFileSync(path.join(dir, f))).digest('hex');
const ok = job.version === 3 && job.provider === 'flow-web' && job.approved_at && job.source.sha256 === sha('source.png')
  && fs.readFileSync(path.join(dir, 'prompt.txt'), 'utf8') === job.prompt_final
  && job.references.every(r => r.sha256 === sha(r.path))
  && Math.abs(job.camera.image_width / job.camera.image_height / (job.export_width / job.export_height) - 1) <= 0.005;
const mode = fs.readFileSync(path.join(__dirname, 'mode.txt'), 'utf8');
fs.writeFileSync(path.join(__dirname, 'seen.json'), JSON.stringify(job));
if (!ok || mode === 'fail') {
  fs.writeFileSync(path.join(dir, 'status.json'), JSON.stringify({ state: 'failed', message: ok ? 'boom' : 'bad job' }));
  process.exit(1);
}
if (mode === 'login') {
  fs.writeFileSync(path.join(dir, 'status.json'), JSON.stringify({ state: 'needs_human', message: 'sign in' }));
  process.exit(2);
}
fs.writeFileSync(path.join(dir, 'status.json'), JSON.stringify({ state: 'running', step: 'uploading' }));
fs.writeFileSync(path.join(dir, 'result_01.png'), 'RESULT');
fs.writeFileSync(path.join(dir, 'results.json'), JSON.stringify({ version: 1, flow_project_url: 'https://flow.example/p/1',
  results: [{ result_index: 1, path: 'result_01.png', resolution: '2K' }] }));
fs.writeFileSync(path.join(dir, 'status.json'), JSON.stringify({ state: 'completed', step: 'downloading' }));
"""


def jpeg(width, height):
    out = io.BytesIO()
    Image.new('RGB', (width, height), 'white').save(out, 'JPEG')
    return out.getvalue()


@pytest.fixture
def driver(tmp_path):
    (tmp_path / 'drv').mkdir()
    (tmp_path / 'drv' / 'run.js').write_text(FAKE_RUN, encoding='utf-8')

    def make(mode='ok', project_url=None):
        (tmp_path / 'drv' / 'mode.txt').write_text(mode, encoding='utf-8')
        return NodeFlowDriver(node=NODE, driver=tmp_path / 'drv' / 'run.js', jobs_dir=tmp_path / 'jobs',
                              project_id='5a4d1c4e-0000-4000-8000-000000000001', project_name='AIS',
                              ratios=list(EXPORT_SIZES), project_url=project_url, timeout_s=30)
    return make


def job(identifier='a' * 32, style=True):
    return {'id': identifier, 'base': (jpeg(1920, 1080), 'image/jpeg'), 'style': (b'STYLE', 'image/png') if style else None,
            'prompt': 'Ảnh 1: giữ nguyên camera.', 'scene_name': 'ais-1'}


@needs_node
def test_writes_a_valid_job_and_returns_the_result(driver, tmp_path):
    progress = []
    data, media, info = driver().render(job(), lambda step, value: progress.append(step))
    assert (data, media) == (b'RESULT', 'image/png')
    assert info['ratio'] == '16:9' and info['resolution'] == '2K'
    seen = json.loads((tmp_path / 'drv' / 'seen.json').read_text(encoding='utf-8'))
    assert [(r['role'], r['path'], r['order']) for r in seen['references']] == [('STYLE_REF', 'style.png', 2)]
    assert info['flow_project_url'] == 'https://flow.example/p/1'
    # A new Flow project per job unless one is pinned (a reused project keeps the last result attached).
    assert 'flowProjectUrl' not in seen
    driver(project_url='https://flow.example/p/pinned').render(job('b' * 32, style=False), lambda *_: None)
    seen = json.loads((tmp_path / 'drv' / 'seen.json').read_text(encoding='utf-8'))
    assert seen['flowProjectUrl'] == 'https://flow.example/p/pinned' and seen['references'] == []


@needs_node
@pytest.mark.parametrize('mode,code', [('fail', 'FLOW_FAILED'), ('login', 'FLOW_NEEDS_ATTENTION')])
def test_driver_failures_map_to_flow_errors(driver, mode, code):
    with pytest.raises(FlowError) as caught:
        driver(mode).render(job(), lambda *_: None)
    assert caught.value.code == code


def test_missing_driver_is_not_retryable(tmp_path):
    d = NodeFlowDriver(node='node', driver=tmp_path / 'none.js', jobs_dir=tmp_path, project_id='x',
                       project_name='AIS', ratios=['16:9'])
    with pytest.raises(FlowError) as caught:
        d.render(job(), lambda *_: None)
    assert caught.value.code == 'FLOW_DRIVER_MISSING' and not caught.value.retryable


def test_crop_matches_flow_ratio_within_driver_tolerance():
    for width, height in [(1920, 1080), (1000, 1000), (1200, 1700), (3000, 1000)]:
        ratio = nearest_ratio(width, height, list(EXPORT_SIZES))
        w, h = Image.open(io.BytesIO(crop_to_ratio(jpeg(width, height), ratio))).size
        tw, th = EXPORT_SIZES[ratio]
        assert abs((w / h) / (tw / th) - 1) <= 0.005
