"""
Logger interface — the contract every concrete logger must follow.

Java equivalent:
    public interface AuthLogger {
        void log(LogEvent event);
    }

    public record LogEvent(
        Instant timestamp,
        LogLevel level,
        String eventType,
        String sessionId,
        String policyName,
        Integer stepIndex,
        String stageType,
        String message,
        Map<String, Object> attributes
    ) {}

The library NEVER constructs strings for logging. Always uses LogEvent records
so downstream systems (Graylog) can index structured fields.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class LogLevel(Enum):
    """Log severity, modeled after RFC 5424 syslog levels."""
    DEBUG = "DEBUG"          # Verbose internal state
    INFO = "INFO"            # Normal flow events
    WARN = "WARN"            # Suspicious but not blocking
    ERROR = "ERROR"          # Stage failures, validation errors
    CRITICAL = "CRITICAL"    # Lockouts, expired sessions, security events


@dataclass
class LogEvent:
    """
    A single log event. Always structured.
    All fields except `message` and `event_type` are optional.

    Standard event_types used by the library:
      engine.start              — session began
      engine.advance            — engine.advance() called
      stage.start               — stage evaluation began
      stage.success             — stage passed
      stage.failed              — stage rejected user input
      stage.expired             — per-stage timer ran out
      stage.lockout             — max retries reached
      step.start                — moved to a new step
      step.expired              — shared timer ran out
      session.success           — entire flow completed
      session.locked            — user locked out
      external_idp.redirect     — user sent to external provider
      external_idp.callback     — user returned from provider
      oob.code_sent             — OTP/code sent (recipient masked!)
      provider.lookup           — external lookup performed
      rate_limiter.check        — rate limit decision
      security.suspicious       — anomaly detected
    """
    event_type: str
    message: str
    level: LogLevel = LogLevel.INFO
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: Optional[str] = None
    policy_name: Optional[str] = None
    step_index: Optional[int] = None
    stage_type: Optional[str] = None
    user_identifier: Optional[str] = None     # Masked! e.g. "12345***901" — never raw PII
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON-based loggers (GELF, JSONL, etc.)."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "event_type": self.event_type,
            "message": self.message,
            "session_id": self.session_id,
            "policy_name": self.policy_name,
            "step_index": self.step_index,
            "stage_type": self.stage_type,
            "user_identifier": self.user_identifier,
            "attributes": self.attributes,
        }


class AuthLogger(ABC):
    """
    Abstract base for all loggers.

    The library calls .log() at every significant event. Implementations
    MUST be thread-safe and MUST NOT raise — failing silently is preferable
    to breaking auth flow due to a logging error.

    Java equivalent: public interface AuthLogger
    """

    @abstractmethod
    def log(self, event: LogEvent) -> None:
        """Emit a structured log event."""
        ...

    # Convenience methods — all delegate to .log()
    def info(self, event_type: str, message: str, **attrs) -> None:
        self.log(LogEvent(
            event_type=event_type, message=message, level=LogLevel.INFO,
            attributes=attrs.pop("attributes", {}), **attrs
        ))

    def warn(self, event_type: str, message: str, **attrs) -> None:
        self.log(LogEvent(
            event_type=event_type, message=message, level=LogLevel.WARN,
            attributes=attrs.pop("attributes", {}), **attrs
        ))

    def error(self, event_type: str, message: str, **attrs) -> None:
        self.log(LogEvent(
            event_type=event_type, message=message, level=LogLevel.ERROR,
            attributes=attrs.pop("attributes", {}), **attrs
        ))

    def critical(self, event_type: str, message: str, **attrs) -> None:
        self.log(LogEvent(
            event_type=event_type, message=message, level=LogLevel.CRITICAL,
            attributes=attrs.pop("attributes", {}), **attrs
        ))

    def debug(self, event_type: str, message: str, **attrs) -> None:
        self.log(LogEvent(
            event_type=event_type, message=message, level=LogLevel.DEBUG,
            attributes=attrs.pop("attributes", {}), **attrs
        ))


class LoggerFactory:
    """
    Helper to construct standard loggers.

    Java equivalent: public class LoggerFactory (factory class)
    """

    @staticmethod
    def console(verbose: bool = False) -> "AuthLogger":
        """For local dev — prints to stdout."""
        from mkk_auth.logging.implementations import ConsoleLogger
        return ConsoleLogger(verbose=verbose)

    @staticmethod
    def json_file(path: str) -> "AuthLogger":
        """Append JSONL events to a file. Suitable for CI test artifacts."""
        from mkk_auth.logging.implementations import JsonFileLogger
        return JsonFileLogger(path)

    @staticmethod
    def in_memory() -> "AuthLogger":
        """Capture events in a list — for unit tests."""
        from mkk_auth.logging.implementations import InMemoryLogger
        return InMemoryLogger()

    @staticmethod
    def graylog_gelf(host: str, port: int = 12201, app_name: str = "mkk_auth") -> "AuthLogger":
        """
        Send GELF-formatted UDP messages to a Graylog stream.
        Use for production-like testing in Python; the real production logger
        is the Java GraylogGelfLogger using Logback's GELF appender.
        """
        from mkk_auth.logging.implementations import GraylogGelfLogger
        return GraylogGelfLogger(host=host, port=port, app_name=app_name)

    @staticmethod
    def composite(*loggers: "AuthLogger") -> "AuthLogger":
        """
        Combine multiple loggers — sends every event to all of them.
        Common pattern: ConsoleLogger + GraylogGelfLogger together.
        """
        from mkk_auth.logging.implementations import CompositeLogger
        return CompositeLogger(list(loggers))
