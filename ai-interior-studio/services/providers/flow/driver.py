"""Runs one Flow render through the TB Gemini Render driver (`node run.js <jobDir>`).

The app writes an approved job v3 folder exactly as the SketchUp plugin does (request.json, source.png,
prompt.txt, optional STYLE_REF), the driver uploads, generates once and downloads into that folder, and the
app reads status.json / results.json back. See the driver's adapters/contract.md for the folder contract.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import time
from typing import Callable, Protocol
import uuid

from PIL import Image

# Mirror of the driver's SIZES table (driver/lib/job.js, Frames::EXPORT_SIZES in Ruby).
EXPORT_SIZES = {'16:9': (2560, 1440), '4:3': (2400, 1800), '1:1': (2048, 2048), '3:4': (1800, 2400), '9:16': (1440, 2560)}
_STEP_PROGRESS = {'opening-browser': .05, 'uploading': .2, 'prompting': .4, 'waiting-render': .5, 'downloading': .9}
_EXT = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}


class FlowError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = True):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


class FlowDriver(Protocol):
    def render(self, job: dict, progress: Callable[[str, float], None]) -> tuple[bytes, str, dict]:
        """job: id, base (bytes, mime), style (bytes, mime) or None, prompt, scene_name.
        Returns (image bytes, media type, info with ratio, resolution, flow project url)."""


def nearest_ratio(width: int, height: int, ratios) -> str:
    return min(ratios, key=lambda r: abs(EXPORT_SIZES[r][0] / EXPORT_SIZES[r][1] - width / height))


def crop_to_ratio(data: bytes, ratio: str) -> bytes:
    """Centre-crop to the exact Flow ratio (the driver rejects > 0.5 % off) and encode as PNG."""
    image = Image.open(io.BytesIO(data)).convert('RGB')
    w, h = image.size
    tw, th = EXPORT_SIZES[ratio]
    if w * th > h * tw:
        new_w = round(h * tw / th)
        image = image.crop(((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h))
    elif w * th < h * tw:
        new_h = round(w * th / tw)
        image = image.crop((0, (h - new_h) // 2, w, (h - new_h) // 2 + new_h))
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


def _uuid(identifier: str) -> str:
    return str(uuid.UUID(hex=identifier[:32].ljust(32, '0')))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class NodeFlowDriver:
    def __init__(self, *, node: str, driver: Path, jobs_dir: Path, project_id: str, project_name: str, ratios,
                 project_url: str | None = None, download_resolution: str = '2K', timeout_s: float = 900):
        self.node, self.driver, self.jobs_dir, self.project_url = node, Path(driver), Path(jobs_dir), project_url
        self.project_id, self.project_name, self.ratios = project_id, project_name, list(ratios)
        self.download_resolution, self.timeout_s = download_resolution, timeout_s

    def write_job(self, job: dict) -> tuple[Path, str]:
        base, base_mime = job['base']
        width, height = Image.open(io.BytesIO(base)).size
        ratio = nearest_ratio(width, height, self.ratios)
        source = crop_to_ratio(base, ratio)
        sw, sh = Image.open(io.BytesIO(source)).size
        directory = self.jobs_dir / job['id']
        directory.mkdir(parents=True, exist_ok=False)
        (directory / 'source.png').write_bytes(source)
        references = []
        if job.get('style'):
            data, mime = job['style']
            name = f"style.{_EXT.get(mime, 'png')}"
            (directory / name).write_bytes(data)
            references.append({'role': 'STYLE_REF', 'path': name, 'sha256': _sha(data), 'order': 2})
        now = datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
        request = {
            'version': 3, 'project_id': self.project_id, 'project_name': self.project_name, 'scene_id': 'view',
            'scene_name': job.get('scene_name') or 'view', 'job_id': _uuid(job['id']), 'attempt': 1,
            'created_at': now, 'approved_at': now,  # the user approved by pressing Generate in the app
            'aspect_ratio': ratio, 'export_width': EXPORT_SIZES[ratio][0], 'export_height': EXPORT_SIZES[ratio][1],
            'output_count': 1, 'provider': 'flow-web', 'download_resolution': self.download_resolution,
            # No SketchUp camera here; the driver only checks the shape and the image aspect.
            'camera': {'projection': 'perspective', 'eye': [0, 0, 0], 'target': [0, 1, 0], 'up': [0, 0, 1], 'fov': 60,
                       'image_width': sw, 'image_height': sh},
            'source': {'path': 'source.png', 'sha256': _sha(source), 'model_path': '', 'model_modified_at': None,
                       'exported_at': now},
            'render_config': {'style': '', 'photo_preset': '', 'lighting': '', 'space_type': '', 'materials': ''},
            'constraints': {'preserve_geometry': True, 'lock_camera': True, 'keep_materials': False},
            'prompt_addition': '', 'references': references, 'prompt_final': job['prompt'],
        }
        if self.project_url:
            # Opt-in only. Like the plugin's default, each job otherwise gets a fresh Flow project: in a reused
            # project the previous result stays attached to the prompt box and the driver's image check fails.
            request['flowProjectUrl'] = self.project_url
        # prompt.txt first, request.json last (as the plugin does): a half-written folder is never a valid job.
        (directory / 'prompt.txt').write_bytes(job['prompt'].encode('utf-8'))
        (directory / 'request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
        return directory, ratio

    def _status(self, directory: Path) -> dict:
        try:
            return json.loads((directory / 'status.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def render(self, job, progress):
        if not self.driver.is_file():
            raise FlowError('FLOW_DRIVER_MISSING', f'TB Gemini Render driver not found: {self.driver}', retryable=False)
        directory, ratio = self.write_job(job)
        with open(directory / 'driver-stdio.log', 'ab') as log:
            try:
                process = subprocess.Popen([self.node, str(self.driver), str(directory)], cwd=str(self.driver.parent),
                                           stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except OSError:
                raise FlowError('FLOW_NODE_MISSING', f'Cannot start Node ({self.node}); install Node.js 24', retryable=False) from None
            deadline, last = time.monotonic() + self.timeout_s, None
            while process.poll() is None:
                step = self._status(directory).get('step')
                if step and step != last:
                    progress(step, _STEP_PROGRESS.get(step, .5))
                    last = step
                if time.monotonic() > deadline:
                    process.kill()
                    raise FlowError('FLOW_TIMEOUT', f'Flow driver gave no result within {self.timeout_s:.0f} s')
                time.sleep(.5)
        status = self._status(directory)
        message = status.get('message') or 'no status.json'  # the driver redacts its own messages
        if process.returncode != 0:
            if status.get('state') in ('needs_human', 'needs_review'):
                raise FlowError('FLOW_NEEDS_ATTENTION', f'Flow needs you: {message}')
            raise FlowError('FLOW_FAILED', f'Flow driver failed: {message}')
        try:
            results = json.loads((directory / 'results.json').read_text(encoding='utf-8'))
            entry = sorted(results['results'], key=lambda r: r['result_index'])[0]
            data = (directory / entry['path']).read_bytes()
        except (OSError, ValueError, KeyError, IndexError):
            raise FlowError('FLOW_NO_RESULT', 'Flow driver finished but left no readable result') from None
        media = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(Path(entry['path']).suffix.lower(), 'image/png')
        return data, media, {'ratio': ratio, 'resolution': entry.get('resolution'), 'job_dir': directory.name,
                             'flow_project_url': results.get('flow_project_url')}
