"""
Custom exception classes for the Liberty Global gateway package.

The hierarchy lets callers (including the Home Assistant integration) tell the
router's quirks apart: a wrong password, a lockout, the single-session "busy"
condition, an expired token, transient network errors and bad arguments each
get their own type.
"""

from __future__ import annotations

from typing import Optional


class GatewayError(Exception):
    """Base exception for all Liberty Global gateway errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class GatewayAPIError(GatewayError):
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


class GatewayAuthError(GatewayError):
    """The password was rejected by the router."""


class GatewayLockoutError(GatewayAuthError):
    """The login endpoint is locked out after too many failed attempts.

    ``lockout_time`` is the router-reported number of seconds remaining, when
    available.
    """

    def __init__(self, message: str, lockout_time: Optional[int] = None):
        super().__init__(message)
        self.lockout_time = lockout_time


class GatewaySessionBusyError(GatewayError):
    """Another session already holds the router's single login slot.

    The gateway allows exactly one authenticated session at a time. A
    well-behaved client releases the slot with
    :meth:`~liberty_global_gateway.client.LibertyGatewayClient.logout`; if the
    holder went away without doing so, the slot frees only once its token
    idles out (see :data:`~liberty_global_gateway.constants.TOKEN_TTL`). Back
    off and retry rather than hammering the login endpoint. In practice this
    usually just means the router's own web UI is open in a browser tab.
    """


class GatewayNetworkError(GatewayError):
    """Network-level errors (timeouts, connection failures, TLS)."""


class GatewayValidationError(GatewayError):
    """Invalid arguments supplied by the caller."""


# -- backwards compatibility --------------------------------------------------
#
# The package was originally released as ``compalf3896lg`` with ``Compal*``
# exception names. Keep the old names working as aliases so existing code
# does not break on the rename.

CompalError = GatewayError
CompalAPIError = GatewayAPIError
CompalAuthError = GatewayAuthError
CompalLockoutError = GatewayLockoutError
CompalSessionBusyError = GatewaySessionBusyError
CompalNetworkError = GatewayNetworkError
CompalValidationError = GatewayValidationError
