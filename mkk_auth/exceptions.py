"""
Exceptions raised by the authentication library.

Java equivalents:
    AuthError          → public class AuthException extends RuntimeException
    PolicyError        → public class PolicyException extends AuthException
    StageError         → public class StageException extends AuthException
    LockedOutError     → public class LockedOutException extends AuthException
    ExpiredError       → public class ExpiredException extends AuthException
    LoggerRequiredError → public class LoggerRequiredException extends AuthException
"""


class AuthError(Exception):
    """Base for all authentication library errors."""


class PolicyError(AuthError):
    """Raised when a policy JSON is malformed or invalid."""


class StageError(AuthError):
    """Raised when a stage encounters an unexpected error during evaluation."""


class LockedOutError(AuthError):
    """Raised when a user is locked out due to too many failed attempts."""

    def __init__(self, message: str, retry_after_seconds: int = 0):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ExpiredError(AuthError):
    """Raised when an authentication session has expired."""


class LoggerRequiredError(AuthError):
    """
    Raised when AuthEngine is constructed without a logger.

    NEVER catch this — fix it by providing a logger. Authentication without
    audit logging is not allowed by MKK security policy.
    """
