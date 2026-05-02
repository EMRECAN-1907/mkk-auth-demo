"""
SSE Logger — streams log events to connected web clients via Server-Sent Events.

Usage:
    from mkk_auth.logging.sse_logger import SseLogger, sse_event_stream

    sse_logger = SseLogger()
    engine = AuthEngine(..., logger=sse_logger)

    # In Flask:
    @app.route("/logs/<session_id>")
    def stream_logs(session_id):
        return Response(
            sse_event_stream(sse_logger, session_id),
            mimetype="text/event-stream",
        )

The logger keeps a per-session queue of events. Web clients subscribe via
EventSource and receive events as JSON.
"""
from __future__ import annotations
import json
import queue
import threading
import time
from typing import Iterator, Optional

from mkk_auth.logging.logger import AuthLogger, LogEvent


class SseLogger(AuthLogger):
    """
    Logger that holds per-session queues of LogEvents for SSE streaming.

    Thread-safe. Each session has its own queue, so multiple browsers/sessions
    can stream concurrently without seeing each other's events.

    Also keeps a "global" queue (None as session id) that receives EVERY event,
    useful for an admin dashboard that wants to see everything.
    """

    # How many events to keep buffered per session (oldest dropped if full)
    QUEUE_MAXSIZE = 1000

    def __init__(self):
        self._queues: dict[Optional[str], list[queue.Queue]] = {}
        self._lock = threading.Lock()

    # ---------- AuthLogger contract ----------

    def log(self, event: LogEvent) -> None:
        """Push event to the matching session queue + the global queue."""
        try:
            self._dispatch(event.session_id, event)
            self._dispatch(None, event)  # global stream
        except Exception:
            pass  # logging must never break auth flow

    # ---------- SSE-side API ----------

    def subscribe(self, session_id: Optional[str]) -> queue.Queue:
        """
        A new web client wants to listen on this session.
        Returns a fresh queue that will receive all future events for this session.
        """
        q: queue.Queue = queue.Queue(maxsize=self.QUEUE_MAXSIZE)
        with self._lock:
            self._queues.setdefault(session_id, []).append(q)
        return q

    def unsubscribe(self, session_id: Optional[str], q: queue.Queue) -> None:
        with self._lock:
            queues = self._queues.get(session_id, [])
            if q in queues:
                queues.remove(q)
            if not queues:
                self._queues.pop(session_id, None)

    # ---------- internal ----------

    def _dispatch(self, key: Optional[str], event: LogEvent) -> None:
        with self._lock:
            queues = list(self._queues.get(key, []))
        for q in queues:
            try:
                q.put_nowait(event)
            except queue.Full:
                # Drop oldest if buffer is full
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (queue.Empty, queue.Full):
                    pass


def sse_event_stream(
    logger: SseLogger,
    session_id: Optional[str] = None,
    keepalive_seconds: float = 15.0,
) -> Iterator[str]:
    """
    Generator yielding SSE-formatted strings.

    Each event is sent as:
        data: {"timestamp": "...", "level": "INFO", "event_type": "...", ...}\n\n

    Keepalive comments are sent every `keepalive_seconds` to prevent timeouts.

    Usage in Flask:
        return Response(sse_event_stream(logger, sid), mimetype="text/event-stream")
    """
    q = logger.subscribe(session_id)
    try:
        # Initial keepalive comment so the connection is established immediately
        yield ": connected\n\n"

        last_keepalive = time.time()
        while True:
            try:
                # Wait up to 1s for an event
                event: LogEvent = q.get(timeout=1.0)
                payload = json.dumps(event.to_dict(), ensure_ascii=False, default=str)
                yield f"data: {payload}\n\n"
                last_keepalive = time.time()
            except queue.Empty:
                # No event — maybe send keepalive
                if (time.time() - last_keepalive) > keepalive_seconds:
                    yield ": keepalive\n\n"
                    last_keepalive = time.time()
    finally:
        logger.unsubscribe(session_id, q)
