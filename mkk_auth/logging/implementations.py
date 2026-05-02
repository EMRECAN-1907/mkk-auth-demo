"""
Concrete logger implementations.

Java equivalents:
    ConsoleLogger      → public class ConsoleLogger implements AuthLogger
    JsonFileLogger     → public class JsonFileLogger implements AuthLogger
    InMemoryLogger     → public class InMemoryLogger implements AuthLogger (test only)
    GraylogGelfLogger  → public class GraylogGelfLogger implements AuthLogger
                          (in Java: use Logback GELF appender — much simpler!)
    CompositeLogger    → public class CompositeLogger implements AuthLogger
    NoOpLogger         → public class NoOpLogger implements AuthLogger
                          (DO NOT use in production — only for testing edge cases)
"""
from __future__ import annotations
import json
import socket
import threading
from typing import Optional

from mkk_auth.logging.logger import AuthLogger, LogEvent, LogLevel


# ANSI colors for ConsoleLogger
_ANSI = {
    LogLevel.DEBUG: "\033[90m",     # gray
    LogLevel.INFO: "\033[36m",      # cyan
    LogLevel.WARN: "\033[33m",      # yellow
    LogLevel.ERROR: "\033[31m",     # red
    LogLevel.CRITICAL: "\033[1;91m" # bold red
}
_RESET = "\033[0m"


class ConsoleLogger(AuthLogger):
    """
    Logger that prints to stdout. ONLY for development.
    """

    def __init__(self, verbose: bool = False, use_color: bool = True):
        self.verbose = verbose
        self.use_color = use_color
        self._lock = threading.Lock()

    def log(self, event: LogEvent) -> None:
        # Skip debug events unless verbose
        if event.level == LogLevel.DEBUG and not self.verbose:
            return

        try:
            with self._lock:
                color = _ANSI.get(event.level, "") if self.use_color else ""
                reset = _RESET if self.use_color else ""

                ts = event.timestamp.strftime("%H:%M:%S")
                prefix = f"{color}[{ts}] {event.level.value:<8}{reset}"
                main = f"{event.event_type:<24} | {event.message}"

                # Append context if present
                ctx_parts = []
                if event.session_id:
                    ctx_parts.append(f"sid={event.session_id[:8]}")
                if event.stage_type:
                    ctx_parts.append(f"stage={event.stage_type}")
                if event.step_index is not None:
                    ctx_parts.append(f"step={event.step_index}")
                if event.user_identifier:
                    ctx_parts.append(f"user={event.user_identifier}")
                ctx = f"  [{' | '.join(ctx_parts)}]" if ctx_parts else ""

                print(f"{prefix} {main}{ctx}", flush=True)

                # Show attributes if verbose and present
                if self.verbose and event.attributes:
                    for k, v in event.attributes.items():
                        print(f"             └─ {k}: {v}")
        except Exception:
            # Logging must never break auth flow
            pass


class JsonFileLogger(AuthLogger):
    """
    Append JSONL (one JSON object per line) to a file.
    Useful for CI test artifacts.
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def log(self, event: LogEvent) -> None:
        try:
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass


class InMemoryLogger(AuthLogger):
    """
    Capture events in a list — for unit tests.
    Provides .events for inspection and helpers like .find().
    """

    def __init__(self):
        self.events: list[LogEvent] = []
        self._lock = threading.Lock()

    def log(self, event: LogEvent) -> None:
        try:
            with self._lock:
                self.events.append(event)
        except Exception:
            pass

    def find(self, event_type: str) -> list[LogEvent]:
        """Return all events matching this event_type."""
        return [e for e in self.events if e.event_type == event_type]

    def has(self, event_type: str) -> bool:
        return any(e.event_type == event_type for e in self.events)

    def count(self, event_type: Optional[str] = None) -> int:
        if event_type is None:
            return len(self.events)
        return len(self.find(event_type))

    def clear(self) -> None:
        with self._lock:
            self.events.clear()


class GraylogGelfLogger(AuthLogger):
    """
    Send GELF (Graylog Extended Log Format) messages via UDP to a Graylog stream.

    GELF format: https://docs.graylog.org/docs/gelf

    Production at MKK uses the Java equivalent — Logback's GELF appender —
    which has retry, compression, TLS, and pooled connections out of the box.
    This Python implementation is a minimal stand-in for parity testing.
    """

    # GELF severity (RFC 5424)
    _SEVERITY = {
        LogLevel.DEBUG: 7,
        LogLevel.INFO: 6,
        LogLevel.WARN: 4,
        LogLevel.ERROR: 3,
        LogLevel.CRITICAL: 2,
    }

    def __init__(self, host: str, port: int = 12201, app_name: str = "mkk_auth"):
        self.host = host
        self.port = port
        self.app_name = app_name
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._lock = threading.Lock()

    def log(self, event: LogEvent) -> None:
        try:
            gelf = self._to_gelf(event)
            payload = json.dumps(gelf, ensure_ascii=False).encode("utf-8")
            with self._lock:
                self._sock.sendto(payload, (self.host, self.port))
        except Exception:
            # Never break auth flow because of logging
            pass

    def _to_gelf(self, event: LogEvent) -> dict:
        """Convert LogEvent to GELF v1.1 format."""
        gelf = {
            "version": "1.1",
            "host": self.app_name,
            "short_message": f"[{event.event_type}] {event.message}",
            "timestamp": event.timestamp.timestamp(),
            "level": self._SEVERITY.get(event.level, 6),
            # GELF custom fields must be prefixed with _
            "_event_type": event.event_type,
            "_session_id": event.session_id or "",
            "_policy_name": event.policy_name or "",
            "_step_index": event.step_index if event.step_index is not None else -1,
            "_stage_type": event.stage_type or "",
            "_user_identifier": event.user_identifier or "",
        }
        # Flatten attributes into custom fields
        for k, v in event.attributes.items():
            # Ensure GELF-compatible types
            if isinstance(v, (str, int, float, bool)):
                gelf[f"_attr_{k}"] = v
            else:
                gelf[f"_attr_{k}"] = str(v)
        return gelf

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass


class CompositeLogger(AuthLogger):
    """
    Send each event to multiple loggers.
    Common production setup: ConsoleLogger + GraylogGelfLogger.
    """

    def __init__(self, loggers: list[AuthLogger]):
        self.loggers = loggers

    def log(self, event: LogEvent) -> None:
        for logger in self.loggers:
            try:
                logger.log(event)
            except Exception:
                pass


class NoOpLogger(AuthLogger):
    """
    Discards all events. DO NOT use in production.

    The library REJECTS this logger if you try to use it as the sole logger
    for AuthEngine. Available only for tests where logging is irrelevant.
    """
    _ALLOW_NOOP = False  # Must be flipped explicitly via internal API

    def log(self, event: LogEvent) -> None:
        pass
