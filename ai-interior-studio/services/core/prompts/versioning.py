"""prompt_version and diffs between prompt edits (brief A5, item 3)."""
from __future__ import annotations

import difflib
import hashlib
import json
from typing import Any

from services.core.domain import PromptSpec

VERSION_PREFIX = 'pv_'


def prompt_version(spec: PromptSpec, rendered: str) -> str:
    """Content address of the structured spec plus the text actually sent. Same input -> same version."""
    payload = json.dumps({'spec': spec.model_dump(mode='json'), 'text': rendered}, sort_keys=True, ensure_ascii=False)
    return VERSION_PREFIX + hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def text_diff(old: str, new: str, old_label: str = 'before', new_label: str = 'after') -> str:
    """Unified diff split on sentences/lines, readable in the History screen."""
    def chunks(text: str) -> list[str]:
        return [line + '\n' for line in text.replace('. ', '.\n').splitlines()]
    return ''.join(difflib.unified_diff(chunks(old), chunks(new), old_label, new_label))


def spec_diff(old: PromptSpec, new: PromptSpec) -> dict[str, dict[str, Any]]:
    """Fields of PromptSpec that changed, with their before/after values."""
    before, after = old.model_dump(mode='json'), new.model_dump(mode='json')
    return {key: {'before': before[key], 'after': after[key]} for key in before if before[key] != after[key]}
