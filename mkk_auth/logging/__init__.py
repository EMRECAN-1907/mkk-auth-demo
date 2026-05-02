"""
Logging subsystem.

The library REQUIRES a logger to be passed to AuthEngine. There is no default.
This is intentional: every authentication action must be auditable.

Available implementations (in this package):
    ConsoleLogger    — prints to stdout (dev only)
    JsonFileLogger   — writes JSONL to a file
    InMemoryLogger   — stores events in a list (for tests)

For production at MKK, the Java implementation will use:
    GraylogGelfLogger — sends GELF messages to Graylog stream

The Python equivalent (GraylogGelfLogger) is provided for parity testing,
but the production path is Java/Logback/GELF.
"""
from mkk_auth.logging.logger import (
    AuthLogger,
    LogLevel,
    LogEvent,
    LoggerFactory,
)
from mkk_auth.logging.implementations import (
    ConsoleLogger,
    JsonFileLogger,
    InMemoryLogger,
    GraylogGelfLogger,
    NoOpLogger,
)
from mkk_auth.logging.sse_logger import SseLogger, sse_event_stream

__all__ = [
    "AuthLogger",
    "LogLevel",
    "LogEvent",
    "LoggerFactory",
    "ConsoleLogger",
    "JsonFileLogger",
    "InMemoryLogger",
    "GraylogGelfLogger",
    "NoOpLogger",
    "SseLogger",
    "sse_event_stream",
]
