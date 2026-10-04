from services.core.domain import Reference, ReferenceRole as R, ReferenceSlot
from services.core.references import select_references

TWELVE = [
    R.DECOR, R.FURNITURE, R.FLOOR, R.WALL, R.LIGHTING, R.APPROVED_VIEW,
    R.CABINET, R.CEILING, R.STYLE_MASTER, R.DECOR, R.BASE_PLAN, R.FURNITURE,
]


def refs(roles):
    return [ReferenceSlot(artifact_id=f'a{i}', role=role) for i, role in enumerate(roles)]


def test_twelve_refs_four_slots_keeps_anchors_and_focus():
    selection = select_references(refs(TWELVE), 4, focus_roles=[R.FLOOR])
    assert [s.role for s in selection.selected] == [R.BASE_PLAN, R.STYLE_MASTER, R.APPROVED_VIEW, R.FLOOR]
    assert len(selection.dropped) == 8
    assert {s.artifact_id for s in selection.selected} | {s.artifact_id for s in selection.dropped} == {f'a{i}' for i in range(12)}
    summary = selection.summary
    for label in ('wall', 'cabinet', 'ceiling', 'furniture', 'lighting', 'decor'):
        assert label in summary
    assert '2 furniture references' in summary and '2 decor references' in summary


def test_without_focus_uses_priority_then_input_order():
    selection = select_references(refs(TWELVE), 6)
    roles = [s.role for s in selection.selected]
    assert roles[:3] == [R.BASE_PLAN, R.STYLE_MASTER, R.APPROVED_VIEW]
    # Three P1 (75) slots left: first three P1 roles in input order are FLOOR, WALL, CABINET.
    assert roles[3:] == [R.FLOOR, R.WALL, R.CABINET]


def test_explicit_priority_beats_role_default():
    items = [ReferenceSlot(artifact_id='low', role=R.FLOOR, priority=10),
             ReferenceSlot(artifact_id='high', role=R.DECOR, priority=90)]
    assert [s.artifact_id for s in select_references(items, 1).selected] == ['high']


def test_zero_slots_and_deterministic():
    items = refs(TWELVE)
    none = select_references(items, 0)
    assert none.selected == [] and len(none.dropped) == 12
    assert select_references(items, 4, [R.WALL]) == select_references(items, 4, [R.WALL])


def test_summary_uses_tags_and_notes():
    dropped = Reference(artifact_id='x', role=R.FLOOR, tags=['oak', 'herringbone'], source_note='Pinterest')
    keep = Reference(artifact_id='y', role=R.STYLE_MASTER)
    summary = select_references([keep, dropped], 1).summary
    assert summary == 'Also follow these references that could not be attached: 1 floor reference (oak, herringbone, Pinterest).'
    assert select_references([keep], 1).summary == ''
