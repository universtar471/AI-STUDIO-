"""Google Flow settings. The browser work is done by the TB Gemini Render driver (Node + Playwright),
the same one the SketchUp plugin uses, so fixes to the Flow automation land in one place."""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

CONFIG_ENV = 'AI_STUDIO_FLOW_CONFIG'
_APPDATA = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
_LOCALAPPDATA = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
# Where the SketchUp plugin records its driver and Node paths (written by its installer).
PLUGIN_INSTALLATION = _APPDATA / 'SketchUp' / 'SketchUp 2026' / 'SketchUp' / 'Plugins' / 'tb_gemini_render' / 'installation.json'
# The driver's signed-in Chrome profile (driver/lib/profile.js profilePath()).
DRIVER_PROFILE = _LOCALAPPDATA / 'TBGeminiRender' / 'chrome-profile'


class FlowConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    driver_path: Path | None = None  # run.js; None: from the plugin's installation.json
    node_path: str | None = None  # node.exe; None: from installation.json, else "node" on PATH
    project_url: str | None = None  # pin one Flow project; None: a new project per job (the plugin's default)
    project_name: str = 'AI Interior Studio'  # Flow upload names: 01_SKETCHUP_<project>_<scene>.png
    supported_ratios: list[str] = Field(default_factory=lambda: ['16:9', '4:3', '1:1', '3:4', '9:16'])
    download_resolution: str = Field(default='2K', pattern='^(1K|2K)$')
    timeout_s: float = Field(default=900, gt=0)  # whole driver run: browser, uploads, render (<= 300 s), 2K download


def load_config(path: Path | str | None = None) -> FlowConfig:
    """Explicit path, else $AI_STUDIO_FLOW_CONFIG, else defaults. The file may set any subset of fields."""
    source = path or os.environ.get(CONFIG_ENV)
    if not source:
        return FlowConfig()
    return FlowConfig.model_validate(json.loads(Path(source).read_text(encoding='utf-8')))


def _installation() -> dict:
    try:
        return json.loads(PLUGIN_INSTALLATION.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}


def resolve_driver(config: FlowConfig) -> tuple[str, Path | None]:
    """(node executable, run.js path or None when unknown)."""
    installed = _installation()
    node = config.node_path or installed.get('nodePath') or 'node'
    driver = config.driver_path or (Path(installed['driverPath']) if installed.get('driverPath') else None)
    return node, driver
