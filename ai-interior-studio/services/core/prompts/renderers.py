"""Turn a PromptSpec into provider text (brief A5, item 2).

FLUX: one prose paragraph. Gemini: numbered instructions that name the role of every attached image,
in the same order the images are sent. `raw_text` (the user's own edit) always wins, verbatim.
"""
from __future__ import annotations

from typing import Any, Sequence

from services.core.domain import PromptSpec, ReferenceRole, ReferenceSlot

ROLE_INSTRUCTIONS: dict[ReferenceRole, str] = {
    ReferenceRole.BASE_PLAN: 'the base view: keep its geometry, camera and layout exactly',
    ReferenceRole.STYLE_MASTER: 'the master style: match its overall mood, palette and material language',
    ReferenceRole.APPROVED_VIEW: 'an approved view of this project: keep materials, colours and lighting consistent with it',
    ReferenceRole.CEILING: 'ceiling reference: use its ceiling design and finish',
    ReferenceRole.WALL: 'wall reference: use its wall finish',
    ReferenceRole.FLOOR: 'floor reference: use its floor material and pattern',
    ReferenceRole.CABINET: 'cabinetry reference: use its joinery style and finish',
    ReferenceRole.FURNITURE: 'furniture reference: use similar loose furniture',
    ReferenceRole.LIGHTING: 'lighting reference: use similar fixtures and light quality',
    ReferenceRole.DECOR: 'decor reference: use similar accessories, sparingly',
}


def _words(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ', '.join(_words(v) for v in value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _pairs(mapping: dict[str, Any]) -> str:
    return '; '.join(f"{key.replace('_', ' ')}: {_words(value)}" for key, value in mapping.items())


def _sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text.endswith('.') else text + '.'


def render_flux(spec: PromptSpec, extra: str = '') -> str:
    """Prose for FLUX.2 Klein. `extra` is e.g. the summary of references that did not fit a slot."""
    if spec.raw_text:
        return spec.raw_text
    facts = spec.scene_facts
    subject = facts.get('room_type') or facts.get('scene_name') or 'interior'
    parts = [f'Photorealistic interior render of the {subject}']
    if spec.style:
        parts[0] += f' in a {spec.style} style'
    parts[0] = _sentence(parts[0])
    if spec.materials:
        parts.append(_sentence('Materials: ' + _pairs(spec.materials)))
    if spec.lighting:
        parts.append(_sentence('Lighting: ' + _pairs(spec.lighting)))
    if spec.preservation:
        parts.append(_sentence('Keep the source image exactly: ' + '; '.join(spec.preservation)))
    if spec.quality:
        parts.append(_sentence(', '.join(spec.quality).capitalize()))
    if spec.constraints:
        parts.append(_sentence('Avoid: ' + ', '.join(c.removeprefix('no ') for c in spec.constraints)))
    if extra:
        parts.append(_sentence(extra))
    return ' '.join(parts)


def render_gemini(spec: PromptSpec, slots: Sequence[ReferenceSlot], extra: str = '') -> str:
    """Instructions for a multi-image Gemini call. `slots` must be in the order the images are attached."""
    if spec.raw_text:
        return spec.raw_text
    lines = ['You are editing an interior visualisation. The attached images are, in order:']
    for index, slot in enumerate(slots, 1):
        lines.append(f'Image {index}: {ROLE_INSTRUCTIONS[slot.role]}.')
    lines.append('')
    lines.append('Task: produce one photorealistic interior image of the base view'
                 + (f' in a {spec.style} style.' if spec.style else '.'))
    if spec.scene_facts:
        lines.append('Scene: ' + _pairs(spec.scene_facts) + '.')
    if spec.preservation:
        lines.append('Must keep: ' + '; '.join(spec.preservation) + '.')
    if spec.materials:
        lines.append('Materials: ' + _pairs(spec.materials) + '.')
    if spec.lighting:
        lines.append('Lighting: ' + _pairs(spec.lighting) + '.')
    if spec.camera:
        lines.append('Camera: ' + _pairs(spec.camera) + '.')
    if spec.quality:
        lines.append('Quality: ' + ', '.join(spec.quality) + '.')
    if spec.constraints:
        lines.append('Do not add: ' + ', '.join(c.removeprefix('no ') for c in spec.constraints) + '.')
    if extra:
        lines.append(_sentence(extra))
    return '\n'.join(lines)
