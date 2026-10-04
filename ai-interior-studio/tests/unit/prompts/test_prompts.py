import pytest

from services.core.domain import (
    CameraHint, CameraMeta, Opening, PromptSpec, ReferenceRole as R, ReferenceSlot, Room, Scene, StylePack,
)
from services.core.prompts import (
    build_prompt_spec, prompt_version, render_flux, render_gemini, spec_diff, text_diff,
)
from services.core.references import select_references

PACK = StylePack(name='Warm oak', palette=['#d8c3a5', '#8e8d8a'], style_prompt={
    'style': 'Japandi',
    'materials': {'floor': 'light oak planks', 'walls': 'warm white lime plaster'},
    'lighting': {'mood': 'soft afternoon daylight'},
    'constraints': ['no clutter'],
})
SCENE = Scene(project_id='p', name='Living room', rgb_artifact_id='a', camera=CameraMeta(
    eye=(1, 2, 1.5), target=(4, 5, 1.2), fov_deg=60, aspect_ratio='16:9', viewport_width=1920, viewport_height=1080))
ROOM = Room(project_id='p', name='Bedroom 1', room_type='bedroom', crop_artifact_id='c',
            width_mm=3600, length_mm=4200, ceiling_height_mm=2800, daylight_hint='east window, morning sun',
            openings=[Opening(kind='door', x_mm=0, y_mm=0, width_mm=900), Opening(kind='window', x_mm=1, y_mm=0, width_mm=1800)],
            camera_hint=CameraHint(x=0.2, y=0.9, dir_x=1, dir_y=-1, lens='24mm'))


def test_scene_spec_and_flux_text_are_deterministic():
    first = build_prompt_spec(scene=SCENE, style_pack=PACK, constraints=['no plants'])
    second = build_prompt_spec(scene=SCENE, style_pack=PACK, constraints=['no plants'])
    assert first == second
    text = render_flux(first)
    assert text == render_flux(second)
    assert prompt_version(first, text) == prompt_version(second, text)
    assert prompt_version(first, text).startswith('pv_')
    assert first.style == 'Japandi'
    assert first.materials['floor'] == 'light oak planks'
    assert first.materials['palette'] == ['#d8c3a5', '#8e8d8a']
    assert first.constraints == ['no people', 'no text or watermarks', 'no clutter', 'no plants']
    assert first.camera['fov_deg'] == 60
    assert 'Japandi' in text and 'light oak planks' in text and 'camera position' in text
    assert 'Avoid: people, text or watermarks, clutter, plants.' in text


def test_room_spec_uses_plan_metadata():
    spec = build_prompt_spec(room=ROOM, style_pack=PACK)
    assert spec.scene_facts == {'ceiling_height_mm': 2800, 'doors': 1, 'length_mm': 4200, 'room_name': 'Bedroom 1',
                                'room_type': 'bedroom', 'source': 'floor plan', 'width_mm': 3600, 'windows': 1}
    assert spec.lighting == {'daylight': 'east window, morning sun', 'mood': 'soft afternoon daylight'}
    assert spec.camera['lens'] == '24mm'
    assert 'floor plan' in spec.preservation[0]
    assert render_flux(spec).startswith('Photorealistic interior render of the bedroom in a Japandi style.')


def test_needs_exactly_one_source():
    with pytest.raises(ValueError):
        build_prompt_spec()
    with pytest.raises(ValueError):
        build_prompt_spec(scene=SCENE, room=ROOM)


def test_explicit_overrides_and_no_style_pack():
    spec = build_prompt_spec(scene=SCENE, style_pack=PACK, lighting={'mood': 'night, warm lamps'}, materials={'floor': 'terrazzo'})
    assert spec.lighting['mood'] == 'night, warm lamps' and spec.materials['floor'] == 'terrazzo'
    bare = build_prompt_spec(scene=SCENE)
    assert bare.style == '' and bare.materials == {}
    assert render_flux(bare).startswith('Photorealistic interior render of the Living room.')


def test_gemini_names_each_image_role_in_slot_order():
    slots = [ReferenceSlot(artifact_id='b', role=R.BASE_PLAN), ReferenceSlot(artifact_id='s', role=R.STYLE_MASTER),
             ReferenceSlot(artifact_id='v', role=R.APPROVED_VIEW), ReferenceSlot(artifact_id='f', role=R.FLOOR)]
    text = render_gemini(build_prompt_spec(scene=SCENE, style_pack=PACK), slots, extra='Also follow 2 decor references')
    lines = text.splitlines()
    assert lines[1].startswith('Image 1: the base view')
    assert lines[2].startswith('Image 2: the master style')
    assert lines[3].startswith('Image 3: an approved view')
    assert lines[4].startswith('Image 4: floor reference')
    assert lines[-1] == 'Also follow 2 decor references.'


def test_dropped_reference_summary_reaches_the_prompt():
    refs = [ReferenceSlot(artifact_id=str(i), role=role) for i, role in enumerate([R.STYLE_MASTER, R.WALL, R.DECOR])]
    selection = select_references(refs, 1)
    text = render_flux(build_prompt_spec(scene=SCENE, style_pack=PACK), extra=selection.summary)
    assert text.endswith('Also follow these references that could not be attached: 1 wall reference, 1 decor reference.')


def test_raw_text_is_used_verbatim():
    spec = build_prompt_spec(scene=SCENE, style_pack=PACK).model_copy(update={'raw_text': 'My own words'})
    assert render_flux(spec) == 'My own words'
    assert render_gemini(spec, []) == 'My own words'


def test_version_and_diff_between_edits():
    old = build_prompt_spec(scene=SCENE, style_pack=PACK)
    new = build_prompt_spec(scene=SCENE, style_pack=PACK, materials={'floor': 'dark walnut'})
    old_text, new_text = render_flux(old), render_flux(new)
    assert prompt_version(old, old_text) != prompt_version(new, new_text)
    assert prompt_version(old, old_text) != prompt_version(old, 'edited by hand')
    assert list(spec_diff(old, new)) == ['materials']
    assert spec_diff(old, new)['materials']['after']['floor'] == 'dark walnut'
    diff = text_diff(old_text, new_text)
    assert '-Materials: floor: light oak planks' in diff and '+Materials: floor: dark walnut' in diff
    assert text_diff(old_text, old_text) == ''
    assert spec_diff(old, PromptSpec.model_validate(old.model_dump())) == {}
