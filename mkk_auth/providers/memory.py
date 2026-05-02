"""
In-memory implementations of all provider protocols.

These are for development, testing, and demos. Production must inject real
implementations (Oracle DB, Redis, NetGSM API, Azure AD, etc.).

In Java, the equivalents would live in a `test` source set.
"""
from __future__ import annotations
import pickle
import time
import secrets
import threading
from collections import defaultdict
from typing import Optional

from mkk_auth.providers.protocols import (
    LookupProvider, OOBChannel, CredentialStore, LdapProvider,
    SessionStore, RateLimiter, RateLimitDecision,
    PushProvider, ExternalIdpProvider, ESignProvider, MobileSignProvider,
)


# =====================================================================
# Lookup
# =====================================================================
class InMemoryLookupProvider(LookupProvider):
    """
    Looks up records in a pre-populated dict, keyed by `value`.

    Usage:
        provider = InMemoryLookupProvider({
            "0123456789012345": {"company_name": "...", "representatives": [...]},
        })
    """

    def __init__(self, data: dict[str, dict]):
        self.data = data

    def lookup(self, key: str, value: str) -> Optional[dict]:
        record = self.data.get(value)
        if record is None:
            return None
        # Defensive copy — engine should not mutate provider's storage
        return dict(record)


# =====================================================================
# OOB
# =====================================================================
class InMemoryOOBChannel(OOBChannel):
    """
    Stores sent codes in memory; useful for tests and CLI demos.
    Optionally invokes a callback when a code is sent — used by demos to
    print the code so the user can "see what was sent".
    """

    def __init__(self, sink: Optional[callable] = None):
        self.sent_messages: list[tuple[str, str, dict]] = []
        self.sink = sink
        self._lock = threading.Lock()

    def send(self, recipient: str, code: str, options: Optional[dict] = None) -> bool:
        with self._lock:
            self.sent_messages.append((recipient, code, options or {}))
        if self.sink:
            try:
                self.sink(recipient, code, options or {})
            except Exception:
                pass
        return True

    def last_code(self) -> Optional[str]:
        return self.sent_messages[-1][1] if self.sent_messages else None


# =====================================================================
# CredentialStore
# =====================================================================
class InMemoryCredentialStore(CredentialStore):
    """
    Verifies credentials against a pre-populated dict.

    Usage:
        store = InMemoryCredentialStore({
            "username": {"demo": ("demo1234", {"name": "Demo User", ...})},
            "tckn": {"11111111110": ("tckn1234", {"name": "Bireysel", ...})},
        })

    Format: { identifier_type: { identifier: (password, user_attrs) } }
    """

    def __init__(self, data: dict[str, dict[str, tuple[str, dict]]]):
        self.data = data

    def verify(self, identifier_type: str, identifier: str, password: str) -> Optional[dict]:
        type_map = self.data.get(identifier_type, {})
        record = type_map.get(identifier)
        if record is None:
            return None
        stored_pw, user_attrs = record
        if stored_pw != password:
            return None
        return dict(user_attrs)


# =====================================================================
# LDAP
# =====================================================================
class InMemoryLdapProvider(LdapProvider):
    """
    Mock LDAP. Stores {username: (password, attributes)}.
    """

    def __init__(self, data: dict[str, tuple[str, dict]]):
        self.data = data

    def bind(self, username: str, password: str) -> Optional[dict]:
        record = self.data.get(username)
        if record is None:
            return None
        stored_pw, attrs = record
        if stored_pw != password:
            return None
        return dict(attrs)


# =====================================================================
# Session
# =====================================================================
class InMemorySessionStore(SessionStore):
    """
    Process-local dict store. NOT shared across processes.
    For production: RedisSessionStore.
    """

    def __init__(self):
        self._store: dict[str, tuple[bytes, float]] = {}  # session_id → (data, expires_at)
        self._lock = threading.Lock()

    def load(self, session_id: str) -> Optional[bytes]:
        with self._lock:
            entry = self._store.get(session_id)
            if entry is None:
                return None
            data, expires_at = entry
            if time.time() > expires_at:
                del self._store[session_id]
                return None
            return data

    def save(self, session_id: str, data: bytes, ttl_seconds: int = 1800) -> None:
        with self._lock:
            self._store[session_id] = (data, time.time() + ttl_seconds)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)


# =====================================================================
# RateLimiter
# =====================================================================
class InMemoryRateLimiter(RateLimiter):
    """
    Sliding-window rate limiter. Tracks failure timestamps per (key, action).

    Configuration:
        window_seconds       — how far back to look (default 1 hour)
        max_failures         — fail count threshold (default 10)
        lockout_seconds      — how long to lock after threshold (default 300 = 5 min)
    """

    def __init__(
        self,
        window_seconds: int = 3600,
        max_failures: int = 10,
        lockout_seconds: int = 300,
    ):
        self.window_seconds = window_seconds
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self._failures: dict[str, list[float]] = defaultdict(list)
        self._lockouts: dict[str, float] = {}  # composite_key → unlock_at_epoch
        self._lock = threading.Lock()

    def _composite(self, key: str, action: str) -> str:
        return f"{key}|{action}"

    def check(self, key: str, action: str) -> RateLimitDecision:
        ck = self._composite(key, action)
        now = time.time()

        with self._lock:
            # Active lockout?
            unlock_at = self._lockouts.get(ck)
            if unlock_at is not None:
                if now < unlock_at:
                    remaining = int(unlock_at - now)
                    return RateLimitDecision(
                        allowed=False,
                        retry_after_seconds=remaining,
                        reason=f"Çok fazla başarısız deneme. {remaining} saniye sonra tekrar deneyin.",
                    )
                else:
                    # Expired lockout
                    del self._lockouts[ck]
                    self._failures[ck].clear()

            # Drop old failures outside window
            cutoff = now - self.window_seconds
            self._failures[ck] = [t for t in self._failures[ck] if t > cutoff]

            return RateLimitDecision(allowed=True)

    def record_failure(self, key: str, action: str) -> None:
        ck = self._composite(key, action)
        now = time.time()
        with self._lock:
            self._failures[ck].append(now)
            cutoff = now - self.window_seconds
            self._failures[ck] = [t for t in self._failures[ck] if t > cutoff]
            if len(self._failures[ck]) >= self.max_failures:
                self._lockouts[ck] = now + self.lockout_seconds

    def record_success(self, key: str, action: str) -> None:
        ck = self._composite(key, action)
        with self._lock:
            self._failures.pop(ck, None)
            self._lockouts.pop(ck, None)


# =====================================================================
# Push
# =====================================================================
class InMemoryPushProvider(PushProvider):
    """
    Mock push notifications. Tests/demos can call .approve(req_id) or
    .reject(req_id) to simulate user tap.
    """

    def __init__(self):
        self._requests: dict[str, dict] = {}        # req_id → request data
        self._responses: dict[str, str] = {}        # req_id → "approved" / "rejected"
        self._lock = threading.Lock()

    def send_approval_request(self, user_id: str, request_data: dict) -> str:
        req_id = secrets.token_hex(8)
        with self._lock:
            self._requests[req_id] = {
                "user_id": user_id,
                "data": request_data,
                "sent_at": time.time(),
            }
        return req_id

    def poll_response(self, request_id: str) -> Optional[str]:
        with self._lock:
            return self._responses.get(request_id)

    # Test helpers
    def approve(self, request_id: str) -> None:
        with self._lock:
            self._responses[request_id] = "approved"

    def reject(self, request_id: str) -> None:
        with self._lock:
            self._responses[request_id] = "rejected"

    def auto_approve_all(self, response: str = "approved") -> None:
        """Auto-respond to every existing request — useful in CLI demos."""
        with self._lock:
            for req_id in self._requests:
                self._responses[req_id] = response


# =====================================================================
# External IDP
# =====================================================================
class InMemoryExternalIdp(ExternalIdpProvider):
    """
    Mock external IDP (e-Devlet, etc.) — auto-returns a fake user identity
    when given any code.
    """

    def __init__(self, base_url: str, fake_user: dict):
        self.base_url = base_url
        self.fake_user = fake_user

    def build_authorize_url(self, state: str, redirect_uri: str) -> str:
        return f"{self.base_url}?state={state}&redirect_uri={redirect_uri}"

    def exchange_code(self, code: str) -> Optional[dict]:
        if not code:
            return None
        return dict(self.fake_user)


# =====================================================================
# e-İmza
# =====================================================================
class InMemoryESignProvider(ESignProvider):
    """
    Mock e-İmza — accepts any 4+ digit PIN that's not "0000".
    Returns a fake certificate subject.
    """

    def __init__(self, fake_subject: dict):
        self.fake_subject = fake_subject

    def verify_signature(self, signed_data: bytes, pin: str) -> Optional[dict]:
        if not pin or len(pin) < 4 or pin == "0000":
            return None
        return dict(self.fake_subject)


# =====================================================================
# Mobile signature
# =====================================================================
class InMemoryMobileSignProvider(MobileSignProvider):
    """
    Mock mobile signature operator. Tests can call .approve(req_id).
    """

    def __init__(self, fake_user_attrs: dict):
        self.fake_user_attrs = fake_user_attrs
        self._requests: dict[str, dict] = {}
        self._approved: set[str] = set()
        self._lock = threading.Lock()

    def request_signature(self, phone: str, operator: str, challenge: str) -> str:
        req_id = secrets.token_hex(8)
        with self._lock:
            self._requests[req_id] = {
                "phone": phone,
                "operator": operator,
                "challenge": challenge,
            }
        return req_id

    def poll_result(self, request_id: str) -> Optional[dict]:
        with self._lock:
            if request_id in self._approved:
                return dict(self.fake_user_attrs)
        return None

    def approve(self, request_id: str) -> None:
        with self._lock:
            self._approved.add(request_id)
