"""Gemini settings. Model id, limits and prices live here (or in a JSON override), not in calling code.

Defaults checked against ai.google.dev on 05/10/2026: gemini-3.1-flash-image (Nano Banana 2),
up to 14 reference images, 1K/2K/4K output, about USD 0.067 / 0.101 / 0.151 per image.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

CONFIG_ENV = 'AI_STUDIO_GEMINI_CONFIG'


class GeminiConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    model: str = 'gemini-3.1-flash-image'
    max_reference_images: int = Field(default=14, ge=1)  # includes the base image
    supported_sizes: list[str] = Field(default_factory=lambda: ['1K', '2K', '4K'])
    supported_ratios: list[str] = Field(default_factory=lambda: ['1:1', '3:2', '2:3', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9'])
    default_size: str = '1K'
    high_cost_sizes: list[str] = Field(default_factory=lambda: ['4K'])  # need confirm_high_cost
    cost_per_image_usd: dict[str, float] = Field(default_factory=lambda: {'1K': 0.067, '2K': 0.101, '4K': 0.151})
    daily_call_limit: int = Field(default=30, ge=0)  # API attempts per local day, retries included
    timeout_s: float = Field(default=120, gt=0)
    max_attempts: int = Field(default=2, ge=1)  # attempts per request on timeout


def load_config(path: Path | str | None = None) -> GeminiConfig:
    """Explicit path, else $AI_STUDIO_GEMINI_CONFIG, else defaults. The file may set any subset of fields."""
    source = path or os.environ.get(CONFIG_ENV)
    if not source:
        return GeminiConfig()
    return GeminiConfig.model_validate(json.loads(Path(source).read_text(encoding='utf-8')))
