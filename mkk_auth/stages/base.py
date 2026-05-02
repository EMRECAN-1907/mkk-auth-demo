"""
BaseStage — abstract parent of every stage implementation.

Java equivalent:
    public abstract class BaseStage {
        protected final Map<String, Object> config;
        protected final AuthLogger logger;

        public BaseStage(Map<String, Object> config, AuthLogger logger) {
            this.config = config;
            this.logger = logger;
        }

        public abstract StageResult evaluate(StageContext stageCtx);
    }
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from mkk_auth.context import AuthContext
from mkk_auth.state import StageResult
from mkk_auth.logging.logger import AuthLogger


@dataclass
class StageContext:
    """
    Per-evaluation context passed to every stage.
    Contains everything a stage needs to do its job.

    Java equivalent: record StageContext(...)
    """
    auth_context: AuthContext
    step_index: int
    column_index: int                # position within parallel row (0 if non-parallel)
    form_data: dict[str, Any]
    policy_name: str
    logger: AuthLogger


class BaseStage(ABC):
    """
    Base class for all stages.

    Subclasses implement `evaluate()`. They have access to:
      - self.config — their JSON config block
      - self.logger — for audit logging (Graylog in production)
      - and inside evaluate(): the AuthContext, form data, position info

    Lifecycle:
      1. __init__         — instance created from policy JSON + injected providers
      2. evaluate(ctx)    — called per submission until StageStatus != PENDING_INPUT
    """

    # === Stage metadata (subclasses should set these) ===
    STAGE_TYPE: str = ""        # Must match the "type" field in policy JSON
    CATEGORY: str = ""           # "identify" / "verify" / "deliver" / "auth"
    DISPLAY_NAME: str = ""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    # ------ Common helpers (subclasses use these) ------

    def field_name(self, suffix: str, step_idx: int, col_idx: int) -> str:
        """Generate a deterministic form field name. Matches builder convention."""
        return f"s_{step_idx}_{col_idx}_{suffix}"

    def get_input(self, ctx: StageContext, suffix: str = "in") -> str:
        """Get a single form field value (with leading/trailing whitespace stripped)."""
        key = self.field_name(suffix, ctx.step_index, ctx.column_index)
        value = ctx.form_data.get(key, "")
        return str(value).strip() if value is not None else ""

    def get_timeout(self) -> Optional[int]:
        """Per-stage timeout in seconds, or None if disabled."""
        v = self.config.get("timeout")
        return v if v is not None else None

    def get_max_retries(self) -> Optional[int]:
        v = self.config.get("maxRetries")
        return v if v is not None else None

    def mask_pii(self, value: str, head: int = 3, tail: int = 2) -> str:
        """
        Mask sensitive data for logging. Never log raw PII.
        Example: "12345678901" → "123******01"
        """
        if not value or len(value) <= head + tail:
            return "***"
        return value[:head] + "*" * (len(value) - head - tail) + value[-tail:]

    # ------ The main contract ------

    @abstractmethod
    def evaluate(self, ctx: StageContext) -> StageResult:
        """
        Evaluate this stage given current context and form input.

        Implementations:
          - Read input from ctx.form_data via self.get_input()
          - Mutate ctx.auth_context to set identified_user, mersis_data, etc.
          - Use ctx.logger to record significant events
          - Return StageResult.success(), .failed(msg, field=...), or .pending()
        """
        ...

    def get_input_descriptors(self, ctx: StageContext) -> list[dict]:
        """
        Optional: tell the application which fields this stage expects on its UI.

        Return a list of dicts like:
            [{"name": "s_0_0_in", "label": "TC Kimlik No",
              "type": "text", "validation": "\\d{11}"}]

        The application uses these to render forms. Not required — apps can
        also hardcode their own fields against the policy JSON.
        """
        return []

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.STAGE_TYPE!r}>"
