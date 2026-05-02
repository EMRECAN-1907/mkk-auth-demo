"""
Per-session authentication context.

Stages READ from and WRITE to this object as the flow progresses.

Java equivalent: public class AuthContext (POJO with getters/setters)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
import time
import uuid


@dataclass
class AuthContext:
    """
    Living state of a single authentication session.

    This object accumulates data across stages:
      - stage 1 (MERSIS lookup) writes mersis_data
      - stage 2 (representative_select) writes identified_user (reading from mersis_data)
      - stage 3 (sms_oob) reads identified_user.phone, writes verified=True

    Persistence is the application's responsibility (Redis, DB, signed cookie).
    The library never touches storage directly.
    """
    # === Identity tracking ===
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: float = field(default_factory=time.time)

    # === Flow position ===
    current_step_index: int = 0
    step_started_at: dict[int, float] = field(default_factory=dict)  # {step_idx: epoch_seconds}
    attempts: dict[str, int] = field(default_factory=dict)          # {"step_col": count}
    expired_stages: set[str] = field(default_factory=set)           # {"step_col"}

    # === Identity data (filled progressively by stages) ===
    identified_user: Optional[dict] = None    # The user we believe is logging in
    attempted_identifier: Optional[str] = None  # Identifier submitted (even if auth failed) - for rate limiting
    mersis_data: Optional[dict] = None        # Full lookup result (company + reps)
    selected_record: Optional[dict] = None    # Picked from a list (e.g., chosen rep)
    verified: bool = False                    # OOB / 2FA succeeded

    # === Internal state (used by stages but not by the app) ===
    _otp_codes: dict[str, str] = field(default_factory=dict)  # generated codes per stage
    _idp_completed: dict[str, bool] = field(default_factory=dict)  # external_idp returned
    _captcha_codes: dict[str, str] = field(default_factory=dict)
    
    # Sub-flow injection: when an alternative is chosen and its stage has
    # sub_steps, we record which alternative was picked. Engine looks up
    # the actual sub_steps from policy on demand (no Step objects stored
    # in context — simpler pickling).
    chosen_alternative: Optional[tuple] = None  # (parent_step_idx, col_idx) or None
    injected_step_index: int = 0  # which sub-step we're on
    in_injected_flow: bool = False  # True while running injected sub-steps

    # === Application-injected data ===
    request_metadata: dict[str, Any] = field(default_factory=dict)  # IP, user-agent, etc.

    def to_safe_dict(self) -> dict:
        """
        Serialize for the application — strips internal fields.
        Use this in AuthState.context.
        """
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "current_step_index": self.current_step_index,
            "identified_user": self.identified_user,
            "mersis_data": self.mersis_data,
            "selected_record": self.selected_record,
            "verified": self.verified,
        }

    def attempt_key(self, step_idx: int, col_idx: int) -> str:
        return f"{step_idx}_{col_idx}"

    def get_attempts(self, step_idx: int, col_idx: int) -> int:
        return self.attempts.get(self.attempt_key(step_idx, col_idx), 0)

    def increment_attempts(self, step_idx: int, col_idx: int) -> int:
        key = self.attempt_key(step_idx, col_idx)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return self.attempts[key]

    def mark_expired(self, step_idx: int, col_idx: int) -> None:
        self.expired_stages.add(self.attempt_key(step_idx, col_idx))

    def is_expired(self, step_idx: int, col_idx: int) -> bool:
        return self.attempt_key(step_idx, col_idx) in self.expired_stages

    def reset_step(self, step_idx: int) -> None:
        """Called when restarting a step (after lockout/expiry, before retry)."""
        self.step_started_at.pop(step_idx, None)
        keys_to_remove = [k for k in self.attempts if k.startswith(f"{step_idx}_")]
        for k in keys_to_remove:
            del self.attempts[k]
        self.expired_stages = {k for k in self.expired_stages if not k.startswith(f"{step_idx}_")}
