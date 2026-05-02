"""
AuthEngine — the orchestrator.

This is the public surface application code interacts with.

Java equivalent:
    @Service
    public class AuthEngine {
        public AuthState advance(AuthContext ctx, Map<String, Object> formData);
        public AuthState start(String policyName, Map<String, Object> formData);
        public AuthState resume(String sessionId, Map<String, Object> formData);
    }

Lifecycle:
    engine = AuthEngine.from_policy("policy.json", providers={...}, logger=...)
    state = engine.start({"mersis": "0123456789012345"})
    if state.is_pending:
        # render UI, get next input
        state = engine.advance(state.context["session_id"], {"selected_tckn": "..."})
    if state.is_success:
        # log user in
"""
from __future__ import annotations
import pickle
import time
from typing import Any, Optional

from mkk_auth.context import AuthContext
from mkk_auth.exceptions import (
    AuthError, LoggerRequiredError, PolicyError, LockedOutError, ExpiredError,
)
from mkk_auth.logging.logger import AuthLogger
from mkk_auth.logging.implementations import NoOpLogger
from mkk_auth.policy import Policy, Step
from mkk_auth.providers.protocols import RateLimiter, SessionStore
from mkk_auth.providers.memory import InMemorySessionStore
from mkk_auth.stages.base import BaseStage, StageContext
from mkk_auth.stages.registry import StageRegistry, get_default_registry
from mkk_auth.state import (
    AuthOutcome, AuthState, StageInfo, StageResult, StageStatus, StepInfo,
)


class AuthEngine:
    """
    Stateless orchestrator. The library does not hold per-session state itself —
    sessions go through the SessionStore.

    Constructor parameters:
        policy        — parsed Policy
        providers     — dict of provider implementations
        logger        — REQUIRED audit logger (raises LoggerRequiredError if missing)
        session_store — defaults to InMemorySessionStore (warns in production)
        rate_limiter  — optional RateLimiter for account-level lockout
        registry      — defaults to the global default registry
    """

    def __init__(
        self,
        policy: Policy,
        providers: dict[str, Any],
        logger: AuthLogger,
        session_store: Optional[SessionStore] = None,
        rate_limiter: Optional[RateLimiter] = None,
        registry: Optional[StageRegistry] = None,
    ):
        # Logger is mandatory
        if logger is None:
            raise LoggerRequiredError(
                "AuthEngine requires a logger. Use LoggerFactory.console() for dev "
                "or LoggerFactory.graylog_gelf(...) for production."
            )
        # Special case: NoOp must be wrapped or refused
        if isinstance(logger, NoOpLogger):
            raise LoggerRequiredError(
                "NoOpLogger is not allowed as the sole logger. "
                "Authentication actions MUST be auditable."
            )

        self.policy = policy
        self.providers = providers
        self.logger = logger
        self.session_store = session_store or InMemorySessionStore()
        self.rate_limiter = rate_limiter
        self.registry = registry or get_default_registry()

        # Pre-instantiate all stages (validates the policy + provider wiring)
        self._stage_instances: list[list[BaseStage]] = []
        # For sub_steps: keyed by (step_idx, col_idx) → list[list[BaseStage]]
        # i.e. for each alternative item that has sub_steps, store the
        # pre-built stage instances of those sub_steps.
        self._substep_instances: dict = {}
        for step_idx, step in enumerate(policy.steps):
            row: list[BaseStage] = []
            for col_idx, item in enumerate(step.items):
                stage = self.registry.create(
                    item.type, item.config, self.providers
                )
                row.append(stage)
                # Pre-build sub_steps too
                if item.sub_steps:
                    sub_rows = []
                    for ss in item.sub_steps:
                        sub_row = [
                            self.registry.create(s.type, s.config, self.providers)
                            for s in ss.items
                        ]
                        sub_rows.append(sub_row)
                    self._substep_instances[(step_idx, col_idx)] = sub_rows
            self._stage_instances.append(row)

        warnings = policy.validate()
        for w in warnings:
            self.logger.warn("policy.warning", w, policy_name=policy.policy_name)

        self.logger.info(
            "engine.ready",
            f"AuthEngine ready for policy {policy.policy_name!r}",
            policy_name=policy.policy_name,
            attributes={
                "step_count": len(policy.steps),
                "total_stages": sum(len(s.items) for s in policy.steps),
            },
        )

    # ===================================================================
    # Construction helpers
    # ===================================================================

    @classmethod
    def from_policy(
        cls,
        policy_path: str,
        providers: dict[str, Any],
        logger: AuthLogger,
        **kwargs,
    ) -> "AuthEngine":
        """Convenience: load policy from file path."""
        policy = Policy.from_file(policy_path)
        return cls(policy=policy, providers=providers, logger=logger, **kwargs)

    @classmethod
    def from_dict(
        cls,
        policy_dict: dict,
        providers: dict[str, Any],
        logger: AuthLogger,
        **kwargs,
    ) -> "AuthEngine":
        """Convenience: load policy from in-memory dict."""
        policy = Policy.from_dict(policy_dict)
        return cls(policy=policy, providers=providers, logger=logger, **kwargs)

    # ===================================================================
    # Public API — the application calls these
    # ===================================================================

    def start(
        self,
        form_data: Optional[dict] = None,
        request_metadata: Optional[dict] = None,
    ) -> AuthState:
        """
        Start a fresh auth session and run as far as possible with given inputs.
        Returns AuthState.
        """
        ctx = AuthContext()
        if request_metadata:
            ctx.request_metadata = dict(request_metadata)

        self.logger.info(
            "engine.start",
            "Auth session started",
            session_id=ctx.session_id,
            policy_name=self.policy.policy_name,
            attributes={"metadata": request_metadata or {}},
        )

        return self._advance_internal(ctx, form_data or {})

    def resume(
        self,
        session_id: str,
        form_data: Optional[dict] = None,
    ) -> AuthState:
        """
        Resume an existing session by ID. The library loads the AuthContext from
        the SessionStore. Returns AuthState.
        """
        raw = self.session_store.load(session_id)
        if raw is None:
            self.logger.warn(
                "engine.session_not_found",
                "Tried to resume unknown session",
                session_id=session_id,
            )
            raise ExpiredError(f"Session {session_id!r} not found or expired")

        ctx: AuthContext = pickle.loads(raw)
        return self._advance_internal(ctx, form_data or {})

    def advance(
        self,
        ctx: AuthContext,
        form_data: Optional[dict] = None,
    ) -> AuthState:
        """
        Advance an in-memory context (no SessionStore round-trip).
        Useful for tests and CLI demos.
        """
        return self._advance_internal(ctx, form_data or {})

    # ===================================================================
    # Internal flow control
    # ===================================================================

    def _advance_internal(
        self,
        ctx: AuthContext,
        form_data: dict,
    ) -> AuthState:
        # Check rate limiter for the identifying key, if available
        rl_key = self._rate_limit_key(ctx)
        if self.rate_limiter and rl_key:
            decision = self.rate_limiter.check(rl_key, "auth")
            if not decision.allowed:
                self.logger.critical(
                    "session.locked",
                    f"User locked: {decision.reason}",
                    session_id=ctx.session_id,
                    policy_name=self.policy.policy_name,
                    user_identifier=self._mask(rl_key),
                    attributes={
                        "retry_after": decision.retry_after_seconds,
                    },
                )
                self._save_session(ctx)
                return AuthState(
                    outcome=AuthOutcome.LOCKED,
                    locked_until_seconds=decision.retry_after_seconds,
                    context=ctx.to_safe_dict(),
                    errors=[StageResult.failed(decision.reason)],
                )

        # Walk forward through steps until we either:
        #   - exhaust all steps (success)
        #   - hit a stage that needs more input (pending)
        #   - hit a failure (failed/expired/locked)
        # Continue while there are more steps OR we're in a sub-flow.
        while (ctx.current_step_index < len(self.policy.steps)
               or ctx.in_injected_flow):
            step_idx = ctx.current_step_index
            
            # Check if we're in an injected sub-flow first
            if ctx.in_injected_flow and ctx.chosen_alternative:
                parent_step_idx, parent_col_idx = ctx.chosen_alternative
                parent_item = self.policy.steps[parent_step_idx].items[parent_col_idx]
                if ctx.injected_step_index < len(parent_item.sub_steps):
                    # We're running an injected sub-step
                    step = parent_item.sub_steps[ctx.injected_step_index]
                    sub_rows = self._substep_instances.get(
                        (parent_step_idx, parent_col_idx), []
                    )
                    if ctx.injected_step_index < len(sub_rows):
                        row = sub_rows[ctx.injected_step_index]
                    else:
                        ctx.in_injected_flow = False
                        continue
                    # For form keys: use the injected step index + 100 as a
                    # "virtual" step_idx. This keeps form keys positive and
                    # distinct from main flow keys.
                    # E.g. sub-step 0 → step_idx = 100, sub-step 1 → 101
                    step_idx = 100 + ctx.injected_step_index
                else:
                    # Done with injected sub-flow, move to next real step
                    ctx.in_injected_flow = False
                    ctx.chosen_alternative = None
                    ctx.injected_step_index = 0
                    ctx.current_step_index += 1
                    continue
            else:
                step = self.policy.steps[step_idx]
                row = self._stage_instances[step_idx]

            # Initialize step start time on first encounter
            if step_idx not in ctx.step_started_at:
                ctx.step_started_at[step_idx] = time.time()
                self.logger.info(
                    "step.start",
                    f"Starting step {step.step_number}",
                    session_id=ctx.session_id,
                    policy_name=self.policy.policy_name,
                    step_index=step_idx,
                    attributes={
                        "stage_count": len(step.items),
                        "parallel": step.is_parallel(),
                        "timing_mode": step.timing.mode,
                    },
                )

            # Check if step's shared timeout has expired
            if self._step_expired(ctx, step):
                self.logger.critical(
                    "step.expired",
                    f"Step {step.step_number} expired",
                    session_id=ctx.session_id,
                    step_index=step_idx,
                )
                self._save_session(ctx)
                return AuthState(
                    outcome=AuthOutcome.EXPIRED,
                    context=ctx.to_safe_dict(),
                    errors=[StageResult.failed(
                        f"Adım {step.step_number} için süre doldu"
                    )],
                )

            # Mark per-stage timeouts that have run out (so submission fails them)
            self._mark_per_stage_expired(ctx, step, row)

            # Evaluate every stage in the row.
            # Multi-pass: if a stage in this row populates identified_user,
            # re-evaluate the previously-pending stages (which were waiting for it).
            errors: list[StageResult] = []
            pending: list[StageResult] = []
            failed_cols: list[int] = []
            success_cols: set[int] = set()

            # Track which stages we've already evaluated successfully
            MAX_PASSES = 3  # safety limit
            for pass_num in range(MAX_PASSES):
                made_progress = False
                pass_pending: list[tuple[int, StageResult]] = []
                pass_errors: list[tuple[int, StageResult]] = []

                # Snapshot identified_user BEFORE this pass
                user_before = ctx.identified_user

                for col_idx, stage in enumerate(row):
                    # Skip already-resolved stages
                    if col_idx in success_cols or col_idx in failed_cols:
                        continue

                    # If stage already expired, force-fail without evaluating
                    if ctx.is_expired(step_idx, col_idx):
                        pass_errors.append((col_idx, StageResult.failed(
                            f"{stage.DISPLAY_NAME}: süre doldu", field=None,
                        )))
                        continue

                    stage_ctx = StageContext(
                        auth_context=ctx, step_index=step_idx, column_index=col_idx,
                        form_data=form_data, policy_name=self.policy.policy_name,
                        logger=self.logger,
                    )
                    try:
                        result = stage.evaluate(stage_ctx)
                    except Exception as e:
                        self.logger.error(
                            "stage.exception", f"Stage threw exception: {e}",
                            session_id=ctx.session_id, step_index=step_idx,
                            stage_type=stage.STAGE_TYPE,
                            attributes={"exception_type": type(e).__name__},
                        )
                        pass_errors.append((col_idx, StageResult.failed(
                            f"İç hata: {stage.DISPLAY_NAME}"
                        )))
                        continue

                    # Rate limiter post-check (unchanged)
                    if self.rate_limiter:
                        new_rl_key = self._rate_limit_key(ctx)
                        if new_rl_key and new_rl_key != rl_key:
                            rl_key = new_rl_key
                            decision = self.rate_limiter.check(new_rl_key, "auth")
                            if not decision.allowed:
                                self.logger.critical(
                                    "session.locked",
                                    f"User locked (post-eval check): {decision.reason}",
                                    session_id=ctx.session_id,
                                    user_identifier=self._mask(new_rl_key),
                                    attributes={"retry_after": decision.retry_after_seconds},
                                )
                                self._save_session(ctx)
                                return AuthState(
                                    outcome=AuthOutcome.LOCKED,
                                    locked_until_seconds=decision.retry_after_seconds,
                                    context=ctx.to_safe_dict(),
                                    errors=[StageResult.failed(decision.reason)],
                                )

                    if result.status == StageStatus.SUCCESS:
                        self.logger.info(
                            "stage.success", f"{stage.DISPLAY_NAME} succeeded",
                            session_id=ctx.session_id, step_index=step_idx,
                            stage_type=stage.STAGE_TYPE,
                        )
                        success_cols.add(col_idx)
                        made_progress = True
                    elif result.status == StageStatus.FAILED:
                        self.logger.warn(
                            "stage.failed", f"{stage.DISPLAY_NAME} failed: {result.message}",
                            session_id=ctx.session_id, step_index=step_idx,
                            stage_type=stage.STAGE_TYPE,
                        )
                        pass_errors.append((col_idx, result))
                    elif result.status == StageStatus.PENDING_INPUT:
                        pass_pending.append((col_idx, result))

                # Commit this pass's failures
                for col_idx, err in pass_errors:
                    errors.append(err)
                    failed_cols.append(col_idx)

                # Commit pending only on the last pass (or if nothing changed)
                user_after = ctx.identified_user
                if user_after == user_before and not made_progress:
                    # Nothing more we can do - commit the pending
                    pending.extend([p for _, p in pass_pending])
                    break
                elif pass_num == MAX_PASSES - 1:
                    pending.extend([p for _, p in pass_pending])
                    break
                # Otherwise, do another pass — pending stages may now succeed

            # ===== Step completion check =====
            # "any" semantics: a single success completes the step. Other stages
            # are skipped (their pending/error state is ignored).
            # "all" semantics (default): every stage must succeed.
            
            if step.semantics == "any":
                if success_cols:
                    # Someone succeeded — step complete!
                    chosen_col = min(success_cols)
                    chosen_item = step.items[chosen_col]
                    self.logger.info(
                        "step.alternative_chosen",
                        f"Alternative chosen: stage at column {chosen_col} succeeded",
                        session_id=ctx.session_id,
                        step_index=step_idx,
                        attributes={"chosen_column": chosen_col,
                                    "chosen_type": chosen_item.type,
                                    "available_alternatives": len(row),
                                    "has_sub_steps": len(chosen_item.sub_steps) > 0},
                    )
                    # If the chosen alternative has sub_steps, inject them
                    # into the runtime flow. They will run before the next
                    # real step.
                    if chosen_item.sub_steps and not ctx.in_injected_flow:
                        ctx.chosen_alternative = (step_idx, chosen_col)
                        ctx.injected_step_index = 0
                        ctx.in_injected_flow = True
                        self.logger.info(
                            "step.sub_flow_injected",
                            f"Injected {len(chosen_item.sub_steps)} sub-steps from {chosen_item.type}",
                            session_id=ctx.session_id,
                            attributes={"count": len(chosen_item.sub_steps)},
                        )
                    # Skip the rest — clear pending/errors for the whole step
                    pending = []
                    # Fall through to advance
                else:
                    # No success yet — could still be pending (user picking)
                    # OR all alternatives failed (errors only)
                    if pending:
                        self._save_session(ctx)
                        return self._build_pending_state(ctx, step, row, pending)
                    # All failed — handle as failure (same as "all" semantics)
                    if errors:
                        stage_locked, rate_decision = self._handle_failures(
                            ctx, step, row, failed_cols
                        )
                        self._save_session(ctx)
                        if rate_decision is not None:
                            return AuthState(
                                outcome=AuthOutcome.LOCKED,
                                locked_until_seconds=rate_decision.retry_after_seconds,
                                context=ctx.to_safe_dict(),
                                errors=[StageResult.failed(rate_decision.reason)],
                            )
                        if stage_locked:
                            return AuthState(
                                outcome=AuthOutcome.LOCKED,
                                context=ctx.to_safe_dict(),
                                errors=errors + [StageResult.failed(
                                    "Bu adımda maksimum deneme aşıldı."
                                )],
                            )
                        return self._build_pending_state(ctx, step, row, [], errors=errors)
            else:
                # "all" semantics — original behavior
                # If anything is still pending, return pending state
                if pending:
                    self._save_session(ctx)
                    return self._build_pending_state(ctx, step, row, pending)

                # If anything failed, increment attempt counters on failed stages only
                if errors:
                    stage_locked, rate_decision = self._handle_failures(
                        ctx, step, row, failed_cols
                    )
                    self._save_session(ctx)

                    if rate_decision is not None:
                        # Account-level lockout (rate limiter)
                        return AuthState(
                            outcome=AuthOutcome.LOCKED,
                            locked_until_seconds=rate_decision.retry_after_seconds,
                            context=ctx.to_safe_dict(),
                            errors=[StageResult.failed(rate_decision.reason)],
                        )
                    if stage_locked:
                        # Stage-level lockout (maxRetries exceeded)
                        return AuthState(
                            outcome=AuthOutcome.LOCKED,
                            context=ctx.to_safe_dict(),
                            errors=errors + [StageResult.failed(
                                "Bu adımda maksimum deneme aşıldı."
                            )],
                        )
                    return self._build_pending_state(ctx, step, row, [], errors=errors)

            # All stages passed — advance
            if ctx.in_injected_flow and step_idx >= 100:
                # We were processing an injected sub-step → advance within sub-flow
                ctx.injected_step_index += 1
            else:
                # Either:
                # - Normal flow → advance main step
                # - Just entered injected flow this iteration (alternative chosen) →
                #   parent step is done, but injected_step_index stays at 0 so the
                #   next loop iteration starts the FIRST injected sub-step.
                ctx.current_step_index += 1

        # All steps complete — success
        if self.rate_limiter and rl_key:
            self.rate_limiter.record_success(rl_key, "auth")

        self.logger.info(
            "session.success",
            "Authentication session completed successfully",
            session_id=ctx.session_id,
            policy_name=self.policy.policy_name,
            user_identifier=self._mask(rl_key) if rl_key else None,
        )

        # Clean up session (don't keep finished contexts around)
        self.session_store.delete(ctx.session_id)
        return AuthState(
            outcome=AuthOutcome.SUCCESS,
            context=ctx.to_safe_dict(),
        )

    # ===================================================================
    # Helpers
    # ===================================================================

    def _rate_limit_key(self, ctx: AuthContext) -> Optional[str]:
        """Find the best identifier to rate-limit on."""
        user = ctx.identified_user or {}
        for k in ("identifier", "tckn", "username", "phone", "email"):
            v = user.get(k)
            if v:
                return str(v)
        # Fallback: identifier submitted (even on failed auth)
        if ctx.attempted_identifier:
            return ctx.attempted_identifier
        return None

    def _mask(self, value: str) -> str:
        if not value or len(value) <= 5:
            return "***"
        return value[:3] + "*" * (len(value) - 5) + value[-2:]

    def _step_expired(self, ctx: AuthContext, step: Step) -> bool:
        """Check if step's shared timeout has elapsed (only meaningful in 'shared' mode)."""
        if step.timing.mode != "shared" or not step.timing.shared_timeout:
            return False
        started = ctx.step_started_at.get(ctx.current_step_index, time.time())
        return (time.time() - started) > step.timing.shared_timeout

    def _mark_per_stage_expired(
        self,
        ctx: AuthContext,
        step: Step,
        row: list[BaseStage],
    ) -> None:
        """In perStage mode, mark stages whose individual timer ran out."""
        if step.timing.mode != "perStage":
            return
        started = ctx.step_started_at.get(ctx.current_step_index, time.time())
        elapsed = time.time() - started
        for col_idx, stage in enumerate(row):
            timeout = stage.get_timeout()
            if timeout and elapsed > timeout:
                ctx.mark_expired(ctx.current_step_index, col_idx)

    def _handle_failures(
        self,
        ctx: AuthContext,
        step: Step,
        row: list[BaseStage],
        failed_cols: list[int],
    ) -> tuple[bool, Optional["RateLimitDecision"]]:
        """
        Increment attempt counters for failed stages.
        Returns (stage_locked, rate_limit_decision):
          - stage_locked: True if any stage exceeded its maxRetries
          - rate_limit_decision: not None if account-level rate limit kicked in
        """
        any_locked = False
        rl_key = self._rate_limit_key(ctx)

        # Record every failure to rate limiter (account-level)
        rate_limit_decision = None
        if self.rate_limiter and rl_key and failed_cols:
            self.rate_limiter.record_failure(rl_key, "auth")
            # Re-check: did this push us into lockout?
            decision = self.rate_limiter.check(rl_key, "auth")
            if not decision.allowed:
                rate_limit_decision = decision
                self.logger.critical(
                    "session.locked",
                    f"Account locked after failure: {decision.reason}",
                    session_id=ctx.session_id,
                    user_identifier=self._mask(rl_key),
                    attributes={"retry_after": decision.retry_after_seconds},
                )

        for col_idx in failed_cols:
            stage = row[col_idx]
            count = ctx.increment_attempts(ctx.current_step_index, col_idx)
            max_retries = stage.get_max_retries()
            if max_retries is not None and count >= max_retries:
                any_locked = True
                self.logger.critical(
                    "stage.lockout",
                    f"Max retries reached on {stage.DISPLAY_NAME}",
                    session_id=ctx.session_id,
                    step_index=ctx.current_step_index,
                    stage_type=stage.STAGE_TYPE,
                    attributes={"attempts": count, "max": max_retries},
                )
        return any_locked, rate_limit_decision

    def _build_pending_state(
        self,
        ctx: AuthContext,
        step: Step,
        row: list[BaseStage],
        pending: list[StageResult],
        errors: Optional[list[StageResult]] = None,
    ) -> AuthState:
        """Build an AuthState describing the current step waiting for input."""
        # In sub-flow: report a step number that matches the form key prefix
        # the engine expects (100 + injected_step_index). This way the frontend
        # builds form keys like s_100_0_in which match what the stage will read.
        if ctx.in_injected_flow:
            display_step_number = 100 + ctx.injected_step_index + 1
        else:
            display_step_number = step.step_number
        step_info = StepInfo(
            step_number=display_step_number,
            parallel=step.is_parallel(),
            timing_mode=step.timing.mode,
            shared_timeout=step.timing.shared_timeout,
            semantics=step.semantics,
            stages=[
                StageInfo(
                    type=stage.STAGE_TYPE,
                    category=stage.CATEGORY,
                    name=stage.DISPLAY_NAME,
                    config=stage.config,
                )
                for stage in row
            ],
        )

        # Compute remaining attempts per stage
        attempts_remaining = {}
        for col_idx, stage in enumerate(row):
            max_retries = stage.get_max_retries()
            if max_retries is not None:
                used = ctx.get_attempts(ctx.current_step_index, col_idx)
                attempts_remaining[stage.STAGE_TYPE] = max(0, max_retries - used)

        # Compute timer deadline for the application UI
        deadline = None
        if step.timing.mode == "shared" and step.timing.shared_timeout:
            started = ctx.step_started_at.get(ctx.current_step_index, time.time())
            deadline = started + step.timing.shared_timeout

        # Pending data (e.g. external_idp redirect URL) — surface via context
        ctx_dict = ctx.to_safe_dict()
        for p in pending:
            if p.data:
                ctx_dict.setdefault("pending_data", {}).update(p.data)

        return AuthState(
            outcome=AuthOutcome.PENDING_INPUT,
            current_step=step_info,
            context=ctx_dict,
            errors=errors or [],
            attempts_remaining=attempts_remaining,
            timer_deadline_unix=deadline,
        )

    def _save_session(self, ctx: AuthContext) -> None:
        """Persist context to session store."""
        ttl = self.policy.session_minutes * 60
        try:
            data = pickle.dumps(ctx)
            self.session_store.save(ctx.session_id, data, ttl_seconds=ttl)
        except Exception as e:
            self.logger.error(
                "session.save_failed",
                f"Failed to save session: {e}",
                session_id=ctx.session_id,
            )
