"""Error codes shared by every module. Raise DomainError, never bare exceptions."""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    JOB_INVALID_TRANSITION = "JOB_INVALID_TRANSITION"
    JOB_MISSING_RESULT = "JOB_MISSING_RESULT"
    JOB_MISSING_ERROR = "JOB_MISSING_ERROR"
    JOB_NOT_RETRYABLE = "JOB_NOT_RETRYABLE"
    FINALIZE_REQUIRES_APPROVED = "FINALIZE_REQUIRES_APPROVED"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
    ARTIFACT_CORRUPT = "ARTIFACT_CORRUPT"
    SNAPSHOT_EXISTS = "SNAPSHOT_EXISTS"
    SNAPSHOT_NAME_INVALID = "SNAPSHOT_NAME_INVALID"


class DomainError(Exception):
    def __init__(self, code: ErrorCode, message: str, **details: Any) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"code": str(self.code), "message": self.message, "details": self.details}
