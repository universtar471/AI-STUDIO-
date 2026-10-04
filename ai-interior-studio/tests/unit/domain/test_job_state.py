from __future__ import annotations

import itertools

import pytest

from services.core.domain import (
    IN_FLIGHT_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    DomainError,
    ErrorCode,
    JobError,
    JobState as S,
    RenderResult,
    ensure_can_finalize,
    new_job,
    retry_job,
    transition,
)

RESULT = RenderResult(artifact_ids=["art1"])
ERROR = JobError(code="OOM", message="out of VRAM")
VALID = [(a, b) for a, nxt in TRANSITIONS.items() for b in nxt]
INVALID = [(a, b) for a, b in itertools.product(S, S) if b not in TRANSITIONS[a]]


def _job_in(state: S, request_):
    """Build a job in `state` by bypassing the machine (test setup only)."""
    job = new_job(request_)
    extra = {"result": RESULT} if state in (S.REVIEW, S.APPROVED, S.FINALIZING, S.DONE) else {}
    return job.model_copy(update={"state": state, **extra})


def test_every_state_has_a_row():
    assert set(TRANSITIONS) == set(S)


@pytest.mark.parametrize("a,b", VALID, ids=lambda s: str(s))
def test_valid_transitions(a, b, request_):
    job = _job_in(a, request_)
    moved = transition(job, b, result=RESULT, error=ERROR, reason="t")
    assert moved.state is b
    assert moved.history[-1].from_state is a and moved.history[-1].to_state is b
    assert job.state is a and job.history == []  # the input job is untouched


@pytest.mark.parametrize("a,b", INVALID, ids=lambda s: str(s))
def test_invalid_transitions_raise_with_code(a, b, request_):
    with pytest.raises(DomainError) as exc:
        transition(_job_in(a, request_), b, result=RESULT, error=ERROR)
    assert exc.value.code is ErrorCode.JOB_INVALID_TRANSITION
    assert exc.value.details["from_state"] == str(a)


def test_spec_changes_are_in_place():
    assert S.RETRY in TRANSITIONS[S.FAILED]  # a failed job can be retried
    assert TRANSITIONS[S.FINALIZING] == {S.DONE, S.APPROVED}  # failed final keeps the preview approved
    assert TERMINAL_STATES == {S.RETRY, S.DONE, S.CANCELLED}
    assert IN_FLIGHT_STATES == {S.QUEUED, S.RUNNING, S.FINALIZING}


def test_happy_path(request_):
    job = new_job(request_)
    for state in (S.QUEUED, S.RUNNING):
        job = transition(job, state)
    job = transition(job, S.REVIEW, result=RESULT)
    assert job.progress == 1.0 and job.result == RESULT
    job = transition(job, S.APPROVED)
    job = transition(job, S.FINALIZING)
    job = transition(job, S.DONE)
    assert [h.to_state for h in job.history] == [S.QUEUED, S.RUNNING, S.REVIEW, S.APPROVED, S.FINALIZING, S.DONE]


def test_review_needs_an_artifact(request_):
    running = _job_in(S.RUNNING, request_)
    for bad in (None, RenderResult()):
        with pytest.raises(DomainError) as exc:
            transition(running, S.REVIEW, result=bad)
        assert exc.value.code is ErrorCode.JOB_MISSING_RESULT


def test_failed_needs_an_error(request_):
    with pytest.raises(DomainError) as exc:
        transition(_job_in(S.RUNNING, request_), S.FAILED)
    assert exc.value.code is ErrorCode.JOB_MISSING_ERROR


@pytest.mark.parametrize("state", [S.REVIEW, S.FAILED])
def test_retry_creates_a_new_linked_job(state, request_):
    old = _job_in(state, request_)
    closed, child = retry_job(old, reason="wrong floor")
    assert closed.id == old.id and closed.state is S.RETRY and closed.result == old.result
    assert child.id != old.id and child.retry_of == old.id
    assert child.state is S.DRAFT and child.revision == old.revision + 1 and child.result is None


@pytest.mark.parametrize("state", [s for s in S if s not in (S.REVIEW, S.FAILED)])
def test_retry_refused_elsewhere(state, request_):
    with pytest.raises(DomainError) as exc:
        retry_job(_job_in(state, request_))
    assert exc.value.code is ErrorCode.JOB_NOT_RETRYABLE


def test_retry_of_upscale_keeps_pointing_at_the_preview(request_):
    from services.core.domain import RenderMode, RenderRequest

    up = new_job(RenderRequest(project_id="p1", mode=RenderMode.UPSCALE, parent_job_id="preview1"))
    assert up.parent_job_id == "preview1"
    failed = up.model_copy(update={"state": S.FAILED, "error": ERROR})
    _, child = retry_job(failed)
    assert child.parent_job_id == "preview1" and child.retry_of == up.id


@pytest.mark.parametrize("state", [s for s in S if s is not S.APPROVED])
def test_final_requires_approved_preview(state, request_):
    with pytest.raises(DomainError) as exc:
        ensure_can_finalize(_job_in(state, request_))
    assert exc.value.code is ErrorCode.FINALIZE_REQUIRES_APPROVED


def test_final_allowed_when_approved(request_):
    ensure_can_finalize(_job_in(S.APPROVED, request_))
