"""
Provider interfaces and reference implementations.

The library defines small, focused interfaces. Applications inject concrete
implementations to connect the engine to their real backend systems.

Java equivalent: each Protocol → an `interface` in Java.

Available protocols:
    LookupProvider           — external lookups (MERSIS, MERNIS, etc.)
    OOBChannel               — out-of-band code delivery (SMS, email)
    CredentialStore          — username + password verification
    LdapProvider             — LDAP / AD bind
    SessionStore             — session persistence (Redis, DB)
    RateLimiter              — account-level lockout decisions
    PushProvider             — push notification approve/reject
    ExternalIdpProvider      — OAuth/OIDC redirect-callback flow
    ESignProvider            — e-İmza verification
    MobileSignProvider       — mobile signature operator API

In-memory implementations (for testing/demos) are in `providers.memory`.
Production code injects real implementations (Spring beans in Java).
"""
from mkk_auth.providers.protocols import (
    LookupProvider,
    OOBChannel,
    CredentialStore,
    LdapProvider,
    SessionStore,
    RateLimiter,
    RateLimitDecision,
    PushProvider,
    ExternalIdpProvider,
    ESignProvider,
    MobileSignProvider,
)
from mkk_auth.providers.memory import (
    InMemoryLookupProvider,
    InMemoryOOBChannel,
    InMemoryCredentialStore,
    InMemoryLdapProvider,
    InMemorySessionStore,
    InMemoryRateLimiter,
    InMemoryPushProvider,
    InMemoryExternalIdp,
    InMemoryESignProvider,
    InMemoryMobileSignProvider,
)

__all__ = [
    # Protocols
    "LookupProvider", "OOBChannel", "CredentialStore", "LdapProvider",
    "SessionStore", "RateLimiter", "RateLimitDecision",
    "PushProvider", "ExternalIdpProvider", "ESignProvider", "MobileSignProvider",
    # In-memory implementations
    "InMemoryLookupProvider", "InMemoryOOBChannel", "InMemoryCredentialStore",
    "InMemoryLdapProvider", "InMemorySessionStore", "InMemoryRateLimiter",
    "InMemoryPushProvider", "InMemoryExternalIdp", "InMemoryESignProvider",
    "InMemoryMobileSignProvider",
]
