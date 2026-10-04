"""Fill a PromptSpec from scene/room metadata, Style Pack and constraints (brief A5, item 1).

Deterministic: the same inputs always give an equal PromptSpec (no clocks, ids or set ordering).
"""
from __future__ import annotations

from typing import Any, Iterable

from services.core.domain import PromptSpec, Room, Scene, StylePack

SCENE_PRESERVATION = [
    'keep the exact camera position, framing and perspective',
    'keep walls, ceiling, windows and doors where they are',
    'keep the furniture layout and object sizes',
]
ROOM_PRESERVATION = [
    'keep the room proportions from the floor plan',
    'keep door and window positions from the floor plan',
]
DEFAULT_QUALITY = ['photorealistic interior photograph', 'true-to-life colours', 'clean, sharp detail']
DEFAULT_CONSTRAINTS = ['no people', 'no text or watermarks']


def _clean(value: Any) -> Any:
    """Drop empty values and sort mapping keys so equal inputs serialise equally."""
    if isinstance(value, dict):
        return {k: _clean(value[k]) for k in sorted(value) if value[k] not in (None, '', [], {})}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _unique(items: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        text = item.strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _scene_facts(scene: Scene) -> dict[str, Any]:
    facts: dict[str, Any] = {'source': 'SketchUp view', 'scene_name': scene.name}
    if scene.camera:
        facts['aspect_ratio'] = scene.camera.aspect_ratio
    return facts


def _scene_camera(scene: Scene) -> dict[str, Any]:
    if not scene.camera:
        return {}
    cam = scene.camera
    return {'eye': list(cam.eye), 'target': list(cam.target), 'fov_deg': cam.fov_deg,
            'focal_length_mm': cam.focal_length_mm, 'aspect_ratio': cam.aspect_ratio}


def _room_facts(room: Room) -> dict[str, Any]:
    doors = sum(1 for o in room.openings if o.kind == 'door')
    windows = sum(1 for o in room.openings if o.kind == 'window')
    return {'source': 'floor plan', 'room_name': room.name, 'room_type': room.room_type,
            'width_mm': room.width_mm, 'length_mm': room.length_mm,
            'ceiling_height_mm': room.ceiling_height_mm, 'doors': doors or None, 'windows': windows or None}


def _room_camera(room: Room) -> dict[str, Any]:
    if not room.camera_hint:
        return {}
    hint = room.camera_hint
    return {'position': [hint.x, hint.y], 'direction': [hint.dir_x, hint.dir_y], 'lens': hint.lens, 'note': hint.note}


def build_prompt_spec(
    *,
    scene: Scene | None = None,
    room: Room | None = None,
    style_pack: StylePack | None = None,
    constraints: Iterable[str] = (),
    lighting: dict[str, Any] | None = None,
    materials: dict[str, Any] | None = None,
) -> PromptSpec:
    """Exactly one of `scene` or `room`. Explicit `lighting`/`materials` override the Style Pack's."""
    if (scene is None) == (room is None):
        raise ValueError('Pass exactly one of scene or room')
    style_prompt = style_pack.style_prompt if style_pack else {}

    if scene is not None:
        facts, preservation, camera = _scene_facts(scene), SCENE_PRESERVATION, _scene_camera(scene)
    else:
        facts, preservation, camera = _room_facts(room), ROOM_PRESERVATION, _room_camera(room)

    style = str(style_prompt.get('style') or (style_pack.name if style_pack else ''))
    pack_materials = dict(style_prompt.get('materials') or {})
    pack_lighting = dict(style_prompt.get('lighting') or {})
    if room is not None and room.daylight_hint and 'daylight' not in pack_lighting:
        pack_lighting['daylight'] = room.daylight_hint
    if style_pack and style_pack.palette:
        pack_materials.setdefault('palette', list(style_pack.palette))

    return PromptSpec(
        scene_facts=_clean(facts),
        preservation=list(preservation),
        style=style,
        materials=_clean({**pack_materials, **(materials or {})}),
        lighting=_clean({**pack_lighting, **(lighting or {})}),
        camera=_clean(camera),
        quality=list(DEFAULT_QUALITY),
        constraints=_unique([*DEFAULT_CONSTRAINTS, *style_prompt.get('constraints', []), *constraints]),
    )
