"""Run the golden set through one provider via the HTTP API and write a side-by-side HTML report.

Usage (backend already running):
    python -m tests.integration.run_golden --provider comfyui
    python -m tests.integration.run_golden --provider comfyui --api http://127.0.0.1:8000 --size 1536

Each run goes to data/golden-runs/<timestamp>-<provider>/ with the outputs, run.json and report.html.
The report puts every scene's source, this run and the previous run of the same provider side by side.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import sys
import time

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = PROJECT_ROOT / 'tests' / 'fixtures' / 'golden' / 'golden.json'
TERMINAL = {'REVIEW', 'FAILED', 'CANCELLED'}
MEDIA = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}


class GoldenError(Exception):
    pass


def load_manifest(golden_dir: Path, manifest_path: Path = MANIFEST) -> tuple[dict, list[dict]]:
    """Return the manifest and the scenes whose file is present. A present file with the wrong hash is an error."""
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for entry in [*manifest['style_pack']['references'], *manifest['scenes']]:
        path = golden_dir / entry['file']
        entry['present'] = path.is_file()
        if entry['present'] and hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise GoldenError(f"Golden file changed: {entry['file']} (sha256 does not match golden.json)")
    missing_refs = [r['file'] for r in manifest['style_pack']['references'] if not r['present']]
    if missing_refs:
        raise GoldenError(f'Missing Style Pack files: {", ".join(missing_refs)}')
    return manifest, [s for s in manifest['scenes'] if s['present']]


def previous_run(out_root: Path, provider: str, current: Path) -> Path | None:
    runs = []  # (started_at, run_dir): ISO timestamps sort in time order
    for run_json in out_root.glob('*/run.json'):
        run_dir = run_json.parent
        if run_dir == current:
            continue
        try:
            run = json.loads(run_json.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if run.get('provider') == provider:
            runs.append((run.get('started_at', ''), run_dir))
    return max(runs, key=lambda item: item[0])[1] if runs else None


def _upload(path: Path) -> tuple[str, bytes, str]:
    media = MEDIA.get(path.suffix.lower())
    if not media:
        raise GoldenError(f'Unsupported image type: {path.name}')
    return path.name, path.read_bytes(), media


def _check(response: httpx.Response) -> dict:
    if response.status_code >= 400:
        raise GoldenError(f'{response.request.method} {response.request.url.path} -> {response.status_code}: {response.text[:300]}')
    return response.json()


def wait_job(client: httpx.Client, job_id: str, timeout_s: float, poll_s: float = 1.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        job = _check(client.get(f'/render/jobs/{job_id}'))
        if job['state'] in TERMINAL:
            return job
        if time.monotonic() > deadline:
            client.post(f'/render/jobs/{job_id}/cancel')
            job['state'], job['error'] = 'TIMEOUT', {'code': 'GOLDEN_TIMEOUT', 'message': f'No result after {timeout_s:.0f} s'}
            return job
        time.sleep(poll_s)


def run_golden(client: httpx.Client, *, provider: str, golden_dir: Path, out_root: Path, size: str | None = None,
               timeout_s: float = 900, poll_s: float = 1.0, manifest_path: Path = MANIFEST, log=print) -> Path:
    manifest, scenes = load_manifest(golden_dir, manifest_path)
    if not scenes:
        raise GoldenError(f'No golden scene images found under {golden_dir}')
    providers = {p['id']: p for p in _check(client.get('/providers'))}
    if provider not in providers:
        raise GoldenError(f'Provider {provider!r} is not registered; have: {", ".join(providers)}')
    started = datetime.now(timezone.utc)
    stamp = started.astimezone().strftime('%Y%m%d-%H%M%S')
    run_dir = out_root / f'{stamp}-{provider}'
    for n in range(2, 100):
        try:
            run_dir.mkdir(parents=True)
            break
        except FileExistsError:
            run_dir = out_root / f'{stamp}-{n}-{provider}'

    project = _check(client.post('/projects', json={'name': f"Golden {started.astimezone():%Y-%m-%d %H:%M} {provider}"}))
    pack_spec = manifest['style_pack']
    pack = _check(client.post('/style-packs', json={'name': pack_spec['name'], 'project_id': project['id'], 'palette': pack_spec.get('palette', [])}))
    for ref in pack_spec['references']:
        pack = _check(client.post(f"/style-packs/{pack['id']}/references", data={'role': ref['role'], 'source_note': ref.get('source_note', '')},
                                  files={'file': _upload(golden_dir / ref['file'])}))

    rows = []
    for scene_spec in scenes:
        source = golden_dir / scene_spec['file']
        shutil.copyfile(source, run_dir / f"{scene_spec['id']}_source{source.suffix.lower()}")
        scene = _check(client.post(f"/projects/{project['id']}/scenes/import", data={'name': scene_spec['name']}, files={'file': _upload(source)}))
        request = {'project_id': project['id'], 'mode': 'sketchup_render', 'source': {'scene_id': scene['id']}, 'provider_id': provider,
                   'style_pack_id': pack['id'], 'seed': manifest.get('seed')}
        if size:
            request['image_size'] = size
        t0 = time.monotonic()
        job = _check(client.post('/render/jobs', json=request))
        log(f"[{scene_spec['id']}] job {job['id']} submitted")
        job = wait_job(client, job['id'], timeout_s, poll_s)
        row = {'id': scene_spec['id'], 'name': scene_spec['name'], 'source': f"{scene_spec['id']}_source{source.suffix.lower()}",
               'must_keep': scene_spec.get('must_keep', []), 'job_id': job['id'], 'state': job['state'],
               'seconds': round(time.monotonic() - t0, 1), 'error': job.get('error'), 'output': None, 'metrics': None}
        result = job.get('result') or {}
        if job['state'] == 'REVIEW' and result.get('artifact_ids'):
            response = client.get(f"/artifacts/{result['artifact_ids'][0]}/file")
            suffix = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}.get(response.headers.get('content-type', '').split(';')[0], '.png')
            row['output'] = f"{scene_spec['id']}{suffix}"
            (run_dir / row['output']).write_bytes(response.content)
            row['metrics'] = result.get('metrics')
        log(f"[{scene_spec['id']}] {row['state']} in {row['seconds']} s")
        rows.append(row)

    run = {'provider': provider, 'started_at': started.isoformat(), 'size': size, 'seed': manifest.get('seed'),
           'golden_version': manifest['version'], 'required_scenes': manifest['required_scenes'],
           'missing_scenes': [s['id'] for s in manifest['scenes'] if not s['present']],
           'project_id': project['id'], 'style_pack_id': pack['id'], 'scenes': rows}
    (run_dir / 'run.json').write_text(json.dumps(run, indent=2, ensure_ascii=False), encoding='utf-8')
    previous = previous_run(out_root, provider, run_dir)
    (run_dir / 'report.html').write_text(render_report(run, run_dir, previous), encoding='utf-8')
    return run_dir


def render_report(run: dict, run_dir: Path, previous: Path | None) -> str:
    prev_rows = {}
    if previous:
        prev = json.loads((previous / 'run.json').read_text(encoding='utf-8'))
        prev_rows = {r['id']: r for r in prev['scenes']}
    e = html.escape

    def cell(row, base: str, label: str) -> str:
        if not row:
            return '<td class="empty">Không có</td>'
        img = f'<img src="{e(base + row["output"])}" alt="{e(label)}">' if row.get('output') else f'<div class="fail">{e(row["state"])}<br>{e((row.get("error") or {}).get("code", ""))}</div>'
        return f'<td>{img}<div class="meta">{e(row["state"])} · {row["seconds"]} s</div></td>'

    body = []
    for row in run['scenes']:
        prev_base = f'../{previous.name}/' if previous else ''
        keep = ''.join(f'<li>{e(item)}</li>' for item in row['must_keep'])
        body.append(f'<tr><th>{e(row["name"])}<ul>{keep}</ul></th><td><img src="{e(row["source"])}" alt="source"></td>'
                    f'{cell(row, "", "this run")}{cell(prev_rows.get(row["id"]), prev_base, "previous run")}</tr>')
    done = sum(r['state'] == 'REVIEW' for r in run['scenes'])
    missing = ', '.join(run['missing_scenes']) or 'không'
    prev_label = e(previous.name) if previous else 'chưa có'
    return f'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Golden {e(run["provider"])}</title>
<style>
:root {{ --bg: #faf8f5; --fg: #2b2622; --muted: #7a7068; --line: #e2dbd2; --bad: #b3261e; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #1d1b19; --fg: #eee8e1; --muted: #a59a90; --line: #3a3530; --bad: #f2b8b5; }} }}
body {{ margin: 0; padding: 16px; background: var(--bg); color: var(--fg); font: 14px/1.4 system-ui, sans-serif; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-top: 1px solid var(--line); padding: 8px; vertical-align: top; text-align: left; }}
thead th {{ color: var(--muted); font-weight: 600; }}
tbody th {{ width: 14rem; }} ul {{ margin: 6px 0 0; padding-left: 18px; color: var(--muted); font-weight: 400; }}
img {{ width: 100%; max-height: 60vh; object-fit: contain; display: block; }}
.meta {{ color: var(--muted); font-size: 12px; margin-top: 4px; }} .fail {{ color: var(--bad); padding: 24px 0; }} .empty {{ color: var(--muted); }}
</style></head><body>
<h1>Bộ ảnh chuẩn · {e(run["provider"])}</h1>
<p>{e(run["started_at"])} · cỡ {e(str(run["size"] or "mặc định"))} · seed {run["seed"]} · đạt REVIEW {done}/{len(run["scenes"])} · cần {run["required_scenes"]} cảnh, thiếu: {e(missing)} · so với lần trước: {prev_label}</p>
<p>Chấm mỗi ảnh theo danh sách “phải giữ” bên trái: camera, bố cục, vật thể không được thêm hay mất.</p>
<table><thead><tr><th>Cảnh</th><th>SketchUp</th><th>Lần này</th><th>Lần trước</th></tr></thead><tbody>
{''.join(body)}
</tbody></table></body></html>
'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--provider', required=True)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--golden-dir', type=Path, default=PROJECT_ROOT / 'data' / 'golden')
    parser.add_argument('--out', type=Path, default=PROJECT_ROOT / 'data' / 'golden-runs')
    parser.add_argument('--size', default=None, help='provider image size, e.g. 1024/1536 (ComfyUI) or 1K/2K (Gemini)')
    parser.add_argument('--timeout', type=float, default=900, help='seconds per scene')
    args = parser.parse_args(argv)
    try:
        with httpx.Client(base_url=args.api, timeout=60, trust_env=False) as client:
            run_dir = run_golden(client, provider=args.provider, golden_dir=args.golden_dir, out_root=args.out, size=args.size, timeout_s=args.timeout)
    except (GoldenError, httpx.HTTPError) as exc:
        print(f'run_golden: {exc}', file=sys.stderr)
        return 2
    run = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
    print(f"Report: {run_dir / 'report.html'}")
    ok = all(r['state'] == 'REVIEW' for r in run['scenes'])
    complete = len(run['scenes']) >= run['required_scenes']
    if not complete:
        print(f"Incomplete golden set: {len(run['scenes'])}/{run['required_scenes']} scenes")
    return 0 if ok and complete else 1


if __name__ == '__main__':
    sys.exit(main())
