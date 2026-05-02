"""
Provider protocols — the contracts.

Each protocol below corresponds to a Java `interface`. Applications implement
these against their real systems (Oracle, NetGSM, Azure AD, etc.).

We use `Protocol` (PEP 544) instead of `ABC` so that any class with the right
shape satisfies it — closer to Java's structural-by-name interfaces.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


# =====================================================================
# Lookup — for stages that query external directories
# =====================================================================
@runtime_checkable
class LookupProvider(Protocol):
    """
    Performs a lookup against an external source by key/value.

    Java equivalent:
        public interface LookupProvider {
            Optional<Map<String, Object>> lookup(String key, String value);
        }

    Examples of `key`:
        "mersis"   — Maliye MERSIS sorgu (returns company + reps)
        "mernis"   — Nüfus müdürlüğü (returns individual)
        "title"    — Ünvan/sicil bazlı sorgu
        "passport" — Yabancı yatırımcı bilgisi
    """

    def lookup(self, key: str, value: str) -> Optional[dict]:
        ...


# =====================================================================
# OOB (Out-Of-Band) — SMS, Email
# =====================================================================
@runtime_checkable
class OOBChannel(Protocol):
    """
    Sends a one-time code through an out-of-band channel.

    Java equivalent:
        public interface OOBChannel {
            boolean send(String recipient, String code, Map<String, Object> options);
        }
    """

    def send(self, recipient: str, code: str, options: Optional[dict] = None) -> bool:
        """
        Send `code` to `recipient` (phone, email, etc.).
        Returns True if successfully dispatched (not necessarily delivered).
        """
        ...


# =====================================================================
# Credential store — username/identifier + password
# =====================================================================
@runtime_checkable
class CredentialStore(Protocol):
    """
    Verifies a credential pair against a backing store.

    Java equivalent:
        public interface CredentialStore {
            Optional<Map<String, Object>> verify(
                String identifierType, String identifier, String password);
        }
    """

    def verify(self, identifier_type: str, identifier: str, password: str) -> Optional[dict]:
        """
        Returns the user record if credentials match, else None.
        identifier_type: "username", "tckn", "vkn", "sicil", "passport", etc.
        """
        ...


# =====================================================================
# LDAP / Active Directory
# =====================================================================
@runtime_checkable
class LdapProvider(Protocol):
    """
    Authenticates against an LDAP/AD server via bind operation.

    Java equivalent:
        public interface LdapProvider {
            Optional<Map<String, Object>> bind(String username, String password);
        }
    """

    def bind(self, username: str, password: str) -> Optional[dict]:
        """Returns the user attributes if bind succeeds, else None."""
        ...


# =====================================================================
# Session storage
# =====================================================================
@runtime_checkable
class SessionStore(Protocol):
    """
    Persistent storage for AuthContext between requests.

    Java equivalent:
        public interface SessionStore {
            Optional<byte[]> load(String sessionId);
            void save(String sessionId, byte[] data, int ttlSeconds);
            void delete(String sessionId);
        }

    The library serializes AuthContext to bytes (pickle in Python; equivalent
    serialization in Java) and stores it. Application picks Redis, DB, etc.
    """

    def load(self, session_id: str) -> Optional[bytes]:
        ...

    def save(self, session_id: str, data: bytes, ttl_seconds: int = 1800) -> None:
        ...

    def delete(self, session_id: str) -> None:
        ...


# =====================================================================
# Rate limiter — account-level lockout policy
# =====================================================================
@dataclass
class RateLimitDecision:
    """
    Returned by RateLimiter.check().

    Java equivalent: record RateLimitDecision(boolean allowed, int retryAfterSeconds, String reason)
    """
    allowed: bool
    retry_after_seconds: int = 0
    reason: str = ""


@runtime_checkable
class RateLimiter(Protocol):
    """
    Tracks failed authentication attempts across sessions and decides
    when an identifier should be locked out.

    Java equivalent:
        public interface RateLimiter {
            RateLimitDecision check(String key, String action);
            void recordFailure(String key, String action);
            void recordSuccess(String key, String action);
        }

    Implementations: Redis-backed sliding window, DB row counter, in-memory dict.
    """

    def check(self, key: str, action: str) -> RateLimitDecision:
        ...

    def record_failure(self, key: str, action: str) -> None:
        ...

    def record_success(self, key: str, action: str) -> None:
        ...


# =====================================================================
# Push notification provider
# =====================================================================
@runtime_checkable
class PushProvider(Protocol):
    """
    Sends a push notification to a user's device and waits (asynchronously)
    for their tap response.

    Java equivalent:
        public interface PushProvider {
            String sendApprovalRequest(String userId, ApprovalRequest req);
            ApprovalStatus pollResponse(String requestId);
        }

    Real impl: FCM/APNS/Huawei HMS. Library calls send → polls until
    tapResponse arrives or timeout.
    """

    def send_approval_request(self, user_id: str, request_data: dict) -> str:
        """Returns a request_id used to poll for the user's tap response."""
        ...

    def poll_response(self, request_id: str) -> Optional[str]:
        """
        Returns "approved" / "rejected" / None (still waiting).
        """
        ...


# =====================================================================
# External IDP — e-Devlet, GIB, Google, etc.
# =====================================================================
@runtime_checkable
class ExternalIdpProvider(Protocol):
    """
    Mediates redirect-based external identity flows.

    Java equivalent:
        public interface ExternalIdpProvider {
            String buildAuthorizeUrl(String state, String redirectUri);
            Optional<Map<String, Object>> exchangeCode(String code);
        }
    """

    def build_authorize_url(self, state: str, redirect_uri: str) -> str:
        """Construct the URL to send the user to (e.g., e-Devlet OAuth endpoint)."""
        ...

    def exchange_code(self, code: str) -> Optional[dict]:
        """
        Exchange authorization code for user info.
        Returns user attributes if successful, None on failure.
        """
        ...


# =====================================================================
# e-İmza
# =====================================================================
@runtime_checkable
class ESignProvider(Protocol):
    """
    Verifies an e-İmza (USB token + certificate) signing operation.

    Java equivalent:
        public interface ESignProvider {
            Optional<Map<String, Object>> verifySignature(
                byte[] signedData, String pin);
        }
    """

    def verify_signature(self, signed_data: bytes, pin: str) -> Optional[dict]:
        """Returns certificate subject details on success, None on failure."""
        ...


# =====================================================================
# Mobile signature
# =====================================================================
@runtime_checkable
class MobileSignProvider(Protocol):
    """
    Operator-mediated mobile signature (Turkcell, Vodafone, TT).

    Java equivalent:
        public interface MobileSignProvider {
            String requestSignature(String phone, String operator, String challenge);
            Optional<Map<String, Object>> pollResult(String requestId);
        }
    """

    def request_signature(self, phone: str, operator: str, challenge: str) -> str:
        ...

    def poll_result(self, request_id: str) -> Optional[dict]:
        ...
