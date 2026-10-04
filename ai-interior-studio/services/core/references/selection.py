"""Fit references into a provider's image slots (brief A5, item 5)."""
from __future__ import annotations

from collections import Counter
from typing import Iterable, Sequence

from pydantic import Field

from services.core.domain import Model, Reference, ReferenceRole, ReferenceSlot

# Always attached first: they define what is being rendered and the look that must hold across views.
ANCHOR_ROLES: tuple[ReferenceRole, ...] = (
    ReferenceRole.BASE_PLAN, ReferenceRole.STYLE_MASTER, ReferenceRole.APPROVED_VIEW,
)


class SlotSelection(Model):
    selected: list[ReferenceSlot] = Field(default_factory=list)  # in slot order
    dropped: list[ReferenceSlot] = Field(default_factory=list)
    summary: str = ""  # text stand-in for the dropped references, appended to the prompt


def _tier(role: ReferenceRole, focus: set[ReferenceRole]) -> int:
    if role in ANCHOR_ROLES:
        return 0
    if role in focus:
        return 1
    return 2


def select_references(
    references: Sequence[ReferenceSlot],
    max_slots: int,
    focus_roles: Iterable[ReferenceRole] = (),
) -> SlotSelection:
    """Anchors first (in ANCHOR_ROLES order), then the roles being edited, then by priority.

    Ties keep the caller's order, so the same input always gives the same selection.
    """
    focus = {ReferenceRole(r) for r in focus_roles}
    ranked = sorted(
        enumerate(references),
        key=lambda item: (
            _tier(item[1].role, focus),
            ANCHOR_ROLES.index(item[1].role) if item[1].role in ANCHOR_ROLES else 0,
            -item[1].priority,
            item[0],
        ),
    )
    ordered = [ref for _, ref in ranked]
    slots = max(max_slots, 0)
    selected, dropped = ordered[:slots], ordered[slots:]
    return SlotSelection(selected=selected, dropped=dropped, summary=summarize_dropped(dropped))


def summarize_dropped(dropped: Sequence[ReferenceSlot]) -> str:
    """One sentence per role, using tags and notes when the reference carries them."""
    if not dropped:
        return ""
    counts = Counter(ref.role for ref in dropped)
    details: dict[ReferenceRole, list[str]] = {}
    for ref in dropped:
        if isinstance(ref, Reference):
            words = [*ref.tags, *([ref.source_note] if ref.source_note else [])]
            if words:
                details.setdefault(ref.role, []).append(', '.join(words))
    parts = []
    for role in sorted(counts, key=lambda r: [*ReferenceRole].index(r)):
        label = role.value.lower().replace('_', ' ')
        text = f'{counts[role]} {label} reference' + ('s' if counts[role] > 1 else '')
        if role in details:
            text += ' (' + '; '.join(details[role]) + ')'
        parts.append(text)
    return 'Also follow these references that could not be attached: ' + ', '.join(parts) + '.'
