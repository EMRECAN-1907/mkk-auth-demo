"""
mkk_auth — Modular Authentication Library for MKK
==================================================

This is a Python reference implementation. The production version will be
written in Java/Spring with the same architecture.

Public API:
    AuthEngine          — Main orchestrator
    Policy              — Loaded JSON policy
    AuthContext         — Per-session state container
    AuthState           — Engine state snapshot returned to application
    StageStatus         — Outcome of a stage evaluation
    AuthLogger          — Required logger interface
    LoggerFactory       — Standard logger implementations
    providers.*         — Provider protocols and in-memory implementations
"""
from mkk_auth.engine import AuthEngine
from mkk_auth.policy import Policy
from mkk_auth.context import AuthContext
from mkk_auth.state import AuthState, StageResult, StageStatus, AuthOutcome
from mkk_auth.logging.logger import AuthLogger, LoggerFactory
from mkk_auth.exceptions import (
    AuthError,
    PolicyError,
    StageError,
    LockedOutError,
    ExpiredError,
    LoggerRequiredError,
)

__version__ = "0.1.0"

__all__ = [
    "AuthEngine",
    "Policy",
    "AuthContext",
    "AuthState",
    "StageResult",
    "StageStatus",
    "AuthOutcome",
    "AuthLogger",
    "LoggerFactory",
    "AuthError",
    "PolicyError",
    "StageError",
    "LockedOutError",
    "ExpiredError",
    "LoggerRequiredError",
]
