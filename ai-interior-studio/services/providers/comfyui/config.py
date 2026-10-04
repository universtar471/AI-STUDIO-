"""Local provider configuration; workflow-specific settings belong in the manifest."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ComfyUIConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    url: str = 'http://127.0.0.1:8188'
    manifest_dir: Path = Path('workflows/manifests')
    workflow_dir: Path = Path('workflows/comfyui')
    manifest: str | None = None
    models_dir: Path | None = None
    timeout_s: float = Field(default=300, gt=0)

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
