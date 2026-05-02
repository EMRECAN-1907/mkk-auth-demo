"""
State and result types returned by the engine.

These are the "DTOs" the application reads from after each engine.advance() call.

Java equivalents:
    StageStatus  → enum StageStatus
    AuthOutcome  → enum AuthOutcome
    StageResult  → record StageResult(...)
    AuthState    → record AuthState(...)
"""
from __future__ import annotations
from dataclasses import dataclass, field as _field
from enum import Enum
from typing import Any, Optional


class StageStatus(Enum):
    """Outcome of a single stage evaluation."""
    SUCCESS = "success"
    FAILED = "failed"             # User input was wrong / didn't match
    PENDING_INPUT = "pending"     # Stage needs more input from user (e.g., redirect-return)
    EXPIRED = "expired"           # Per-stage timer ran out before submission


class AuthOutcome(Enum):
    """High-level outcome of the entire authentication flow."""
    PENDING_INPUT = "pending_input"   # User must submit more data
    SUCCESS = "success"                # All stages passed
    FAILED = "failed"                  # User error (wrong input, exceeded retries)
    EXPIRED = "expired"                # Time limit exceeded
    LOCKED = "locked"                  # Rate limiter says: blocked


@dataclass
class StageResult:
    """
    Returned by every Stage.evaluate() call.

    Fields:
        status   — outcome
        message  — human-readable message (shown to user)
        field    — which form field failed (for highlighting in UI)
        data     — extra structured data (e.g., for next stage)
    """
    status: StageStatus
    message: str = ""
    field: Optional[str] = None
    data: dict[str, Any] = _field(default_factory=dict)

    @classmethod
    def success(cls, message: str = "", **data) -> "StageResult":
        return cls(status=StageStatus.SUCCESS, message=message, data=data)

    @classmethod
    def failed(cls, message: str, field: Optional[str] = None) -> "StageResult":
        return cls(status=StageStatus.FAILED, message=message, field=field)

    @classmethod
    def pending(cls, message: str = "", **data) -> "StageResult":
        return cls(status=StageStatus.PENDING_INPUT, message=message, data=data)

    @property
    def ok(self) -> bool:
        return self.status == StageStatus.SUCCESS


@dataclass
class StageInfo:
    """Metadata about a stage exposed to the application (for rendering UIs)."""
    type: str
    category: str
    name: str
    config: dict[str, Any]


@dataclass
class StepInfo:
    """Metadata about a step (one row in the flow, may contain parallel stages)."""
    step_number: int
    parallel: bool
    timing_mode: str            # "perStage" or "shared"
    shared_timeout: Optional[int]
    stages: list[StageInfo]
    semantics: str = "all"      # "all" (every stage required) or "any" (alternative)


@dataclass
class AuthState:
    """
    Snapshot returned to the application after each engine.advance() call.

    The application uses this to:
      - decide what to render
      - know where the user is in the flow
      - access the auth context (identified_user, etc.)
      - report errors to the user
    """
    outcome: AuthOutcome
    current_step: Optional[StepInfo] = None
    context: dict[str, Any] = _field(default_factory=dict)
    errors: list[StageResult] = _field(default_factory=list)
    locked_until_seconds: int = 0      # if outcome == LOCKED, retry after this many seconds
    attempts_remaining: dict[str, int] = _field(default_factory=dict)  # {stage_key: remaining}
    timer_deadline_unix: Optional[float] = None     # epoch seconds when current step expires

    @property
    def is_pending(self) -> bool:
        return self.outcome == AuthOutcome.PENDING_INPUT

    @property
    def is_success(self) -> bool:
        return self.outcome == AuthOutcome.SUCCESS

    @property
    def is_terminal(self) -> bool:
        return self.outcome in (AuthOutcome.SUCCESS, AuthOutcome.LOCKED, AuthOutcome.EXPIRED)
