"""RenderJob state machine (spec 7.2 plus the three changes listed in docs/contracts.md)."""
from __future__ import annotations

from datetime import datetime

from .enums import JobState as S
from .errors import DomainError, ErrorCode
from .models import JobError, RenderJob, RenderRequest, RenderResult, StateChange, new_id, utcnow

TRANSITIONS: dict[S, frozenset[S]] = {
    S.DRAFT: frozenset({S.QUEUED, S.CANCELLED}),
    S.QUEUED: frozenset({S.RUNNING, S.CANCELLED}),
    S.RUNNING: frozenset({S.REVIEW, S.FAILED, S.CANCELLED}),
    S.REVIEW: frozenset({S.APPROVED, S.RETRY}),
    S.FAILED: frozenset({S.RETRY}),
    S.APPROVED: frozenset({S.FINALIZING, S.DONE}),
    # A failed final returns the preview to APPROVED; the error lives on the upscale job.
    S.FINALIZING: frozenset({S.DONE, S.APPROVED}),
    # Terminal. RETRY means "replaced by a newer job" (see retry_job).
    S.RETRY: frozenset(),
    S.DONE: frozenset(),
    S.CANCELLED: frozenset(),
}

TERMINAL_STATES: frozenset[S] = frozenset(s for s, nxt in TRANSITIONS.items() if not nxt)
# States a restart must reconcile (A2 owns the reconciliation itself).
IN_FLIGHT_STATES: frozenset[S] = frozenset({S.QUEUED, S.RUNNING, S.FINALIZING})


def can_transition(from_state: S, to_state: S) -> bool:
    return to_state in TRANSITIONS[from_state]


def new_job(request: RenderRequest, *, job_id: str | None = None) -> RenderJob:
    return RenderJob(
        id=job_id or new_id(),
        project_id=request.project_id,
        request=request,
        parent_job_id=request.parent_job_id,
    )


def transition(
    job: RenderJob,
    to_state: S,
    *,
    reason: str | None = None,
    result: RenderResult | None = None,
    error: JobError | None = None,
    now: datetime | None = None,
) -> RenderJob:
    """Return a copy of `job` in `to_state`. The input job is never mutated."""
    if not can_transition(job.state, to_state):
        raise DomainError(
            ErrorCode.JOB_INVALID_TRANSITION,
            f"{job.state} -> {to_state} is not allowed",
            job_id=job.id,
            from_state=str(job.state),
            to_state=str(to_state),
            allowed=sorted(str(s) for s in TRANSITIONS[job.state]),
        )
    result = result or job.result
    update: dict = {}
    if to_state is S.REVIEW:
        if result is None or not result.artifact_ids:
            raise DomainError(ErrorCode.JOB_MISSING_RESULT, "REVIEW needs at least one artifact", job_id=job.id)
        update.update(result=result, progress=1.0, error=None)
    if to_state is S.FAILED:
        if error is None:
            raise DomainError(ErrorCode.JOB_MISSING_ERROR, "FAILED needs an error", job_id=job.id)
        update["error"] = error
    at = now or utcnow()
    update.update(
        state=to_state,
        updated_at=at,
        history=[*job.history, StateChange(from_state=job.state, to_state=to_state, at=at, reason=reason)],
    )
    return job.model_copy(update=update)


def retry_job(
    job: RenderJob, *, request: RenderRequest | None = None, reason: str | None = None
) -> tuple[RenderJob, RenderJob]:
    """Close `job` as RETRY and create its replacement. Returns (closed_job, new_job).

    The old job and its artifacts stay untouched; the new job is a new revision in DRAFT.
    """
    if not can_transition(job.state, S.RETRY):
        raise DomainError(
            ErrorCode.JOB_NOT_RETRYABLE,
            f"a job in {job.state} cannot be retried",
            job_id=job.id,
            state=str(job.state),
        )
    closed = transition(job, S.RETRY, reason=reason)
    new_request = request or job.request
    child = RenderJob(
        project_id=job.project_id,
        request=new_request,
        revision=job.revision + 1,
        parent_job_id=new_request.parent_job_id,
        retry_of=job.id,
    )
    return closed, child


def ensure_can_finalize(preview_job: RenderJob) -> None:
    """Final/4K is only allowed on an approved preview."""
    if preview_job.state is not S.APPROVED:
        raise DomainError(
            ErrorCode.FINALIZE_REQUIRES_APPROVED,
            f"job is {preview_job.state}, final needs APPROVED",
            job_id=preview_job.id,
            state=str(preview_job.state),
        )
