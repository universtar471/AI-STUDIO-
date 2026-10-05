"""Local provider configuration; workflow-specific settings belong in the manifest."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ComfyUIConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    url: str = 'http://127.0.0.1:8188'
    manifest_dir: Path = PROJECT_ROOT / 'workflows/manifests'
    workflow_dir: Path = PROJECT_ROOT / 'workflows/comfyui'
    manifest: str | None = 'flux2_klein_4b_preview.json'
    models_dir: Path | None = None
    timeout_s: float = Field(default=600, gt=0)
    health_cache_ttl_s: float = Field(default=30, ge=0)

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('ComfyUI URL must be HTTP(S), without credentials, query or fragment')
        return value.rstrip('/')


def load_config(path: Path | str | None = None) -> ComfyUIConfig:
    source = path or os.environ.get('AI_STUDIO_COMFYUI_CONFIG')
    return ComfyUIConfig.model_validate_json(Path(source).read_text(encoding='utf-8')) if source else ComfyUIConfig()
