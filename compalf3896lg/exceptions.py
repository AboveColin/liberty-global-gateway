"""
Custom exception classes for the Compal F3896LG package.

The hierarchy lets callers (including the Home Assistant integration) tell the
router's quirks apart: a wrong password, a lockout, the single-session "busy"
condition, an expired token, transient network errors and bad arguments each
get their own type.
"""

from __future__ import annotations

from typing import Optional


class CompalError(Exception):
    """Base exception for all Compal F3896LG errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CompalAPIError(CompalError):
    """A non-success response from the router API."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"HTTP {self.status_code}")
        if self.error_code is not None:
            parts.append(f"errorCode {self.error_code}")
        return f"{parts[0]} ({', '.join(parts[1:])})" if len(parts) > 1 else parts[0]


class CompalAuthError(CompalError):
    """The password was rejected by the router."""


class CompalLockoutError(CompalAuthError):
    """The login endpoint is locked out after too many failed attempts.

    ``lockout_time`` is the router-reported number of seconds remaining, when
    available.
    """

    def __init__(self, message: str, lockout_time: Optional[int] = None):
        super().__init__(message)
        self.lockout_time = lockout_time


class CompalSessionBusyError(CompalError):
    """Another session already holds the router's single login slot.

    The F3896LG allows exactly one authenticated session at a time and has no
    logout endpoint, so the slot frees only when the previous session's token
    expires (see :data:`~compalf3896lg.constants.TOKEN_TTL`). Back off and
    retry rather than hammering the login endpoint.
    """


class CompalNetworkError(CompalError):
    """Network-level errors (timeouts, connection failures, TLS)."""


class CompalValidationError(CompalError):
    """Invalid arguments supplied by the caller."""
