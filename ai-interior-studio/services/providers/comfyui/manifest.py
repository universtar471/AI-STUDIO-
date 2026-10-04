"""Validated API-template bindings. Never synthesize or rewire a graph."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path, PureWindowsPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .config import ComfyUIConfig

MISSING_WORKFLOW = 'chưa có workflow từ Đợt 0'


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


def relative_path(value: str) -> str:
    path = PureWindowsPath(value)
    if not value or path.is_absolute() or path.drive or path.root or '..' in path.parts or ':' in value:
        raise ValueError(f'Expected a relative path within its configured directory: {value}')
    return value.replace('\\', '/')


def contained_path(root: Path, name: str) -> Path:
    path = (root / relative_path(name)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'Path escapes configured directory: {name}')
    return path


class Binding(StrictModel):
    node_id: str = Field(min_length=1)
    input: str = Field(min_length=1)


class Bindings(StrictModel):
    source_image: Binding
    reference_image: list[Binding]
    prompt: Binding
    long_edge: Binding
    seed: Binding
    filename_prefix: Binding
    steps: Binding
    cfg: Binding

    def all(self):
        return [self.source_image, *self.reference_image, self.prompt, self.long_edge,
                self.seed, self.filename_prefix, self.steps, self.cfg]


class ModelLookup(StrictModel):
    class_type: str = Field(min_length=1)
    input: str = Field(min_length=1)


class ModelFile(StrictModel):
    path: str
    sha256: str | None = Field(default=None, pattern=r'^[a-fA-F0-9]{64}$')
    object_info: ModelLookup | None = None

    _relative = field_validator('path')(relative_path)


class CustomNode(StrictModel):
    class_type: str = Field(min_length=1)
    version: str = Field(min_length=1)


class Preset(StrictModel):
    long_edge: int = Field(gt=0)
    steps: int = Field(gt=0)
    cfg: float = Field(ge=0, allow_inf_nan=False)


class Manifest(StrictModel):
    name: str = Field(min_length=1)
    template: str
    models: list[ModelFile]
    custom_nodes: list[CustomNode]
    bindings: Bindings
    presets: dict[str, Preset]
    max_reference_images: int = Field(ge=0)
    license_note: str = Field(min_length=1)

    _relative = field_validator('template')(relative_path)

    @model_validator(mode='after')
    def consistent(self):
        if set(self.presets) != {'PREVIEW_FAST', 'PREVIEW_QUALITY'}:
            raise ValueError('Both PREVIEW_FAST and PREVIEW_QUALITY presets are required')
        if self.presets['PREVIEW_FAST'].long_edge != 1024 or self.presets['PREVIEW_QUALITY'].long_edge != 1536:
            raise ValueError('Preview edges must be 1024 (FAST) and 1536 (QUALITY)')
        if self.max_reference_images != len(self.bindings.reference_image):
            raise ValueError('max_reference_images must equal reference_image slot count')
        points = [(b.node_id, b.input) for b in self.bindings.all()]
        if len(points) != len(set(points)):
            raise ValueError('Bindings must not overlap')
        return self


def check_bindings(template: dict, manifest: Manifest) -> None:
    for binding in manifest.bindings.all():
        node = template.get(binding.node_id)
        if not isinstance(node, dict) or not isinstance(node.get('inputs'), dict) or binding.input not in node['inputs']:
            raise ValueError(f'Missing template node/input: {binding.node_id}.{binding.input}')


def load_workflow(config: ComfyUIConfig) -> tuple[Manifest, dict, str]:
    if not config.manifest:
        raise FileNotFoundError(MISSING_WORKFLOW)
    path = contained_path(config.manifest_dir, config.manifest)
    if not path.is_file():
        raise FileNotFoundError(f'{MISSING_WORKFLOW}: {path}')
    manifest = Manifest.model_validate_json(path.read_text(encoding='utf-8'))
    template_path = contained_path(config.workflow_dir, manifest.template)
    if not template_path.is_file():
        raise FileNotFoundError(f'{MISSING_WORKFLOW}: {template_path}')
    raw = template_path.read_bytes()
    template = json.loads(raw)
    if not isinstance(template, dict):
        raise ValueError('Template must be an API graph object')
    check_bindings(template, manifest)
    return manifest, template, hashlib.sha256(raw).hexdigest()


def inject(template: dict, manifest: Manifest, *, source_image: str, reference_image: list[str],
           prompt: str, seed: int, filename_prefix: str, preset: str) -> dict:
    check_bindings(template, manifest)
    if len(reference_image) > manifest.max_reference_images:
        raise ValueError('Too many reference images')
    graph = deepcopy(template)
    values = dict(source_image=source_image, prompt=prompt, seed=seed, filename_prefix=filename_prefix,
                  **manifest.presets[preset].model_dump())
    for name, value in values.items():
        binding = getattr(manifest.bindings, name)
        graph[binding.node_id]['inputs'][binding.input] = value
    for binding, value in zip(manifest.bindings.reference_image, reference_image):
        graph[binding.node_id]['inputs'][binding.input] = value
    return graph
