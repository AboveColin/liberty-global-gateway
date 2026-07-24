"""
compalf3896lg — an unofficial async Python client for the Compal F3896LG.

The F3896LG is the DOCSIS 3.1 cable gateway Liberty Global / Ziggo ship in the
Netherlands. This library talks to its ``/rest/v1`` admin API to read system
info, DOCSIS downstream/upstream channels, cable-modem state, provisioned
service flows, Wi-Fi configuration/state and the connected-hosts table, and can
reboot the gateway.

The router allows a single authenticated session. The client logs in, reads in
a burst, then calls :meth:`CompalClient.logout` to release the slot immediately
(``DELETE /user/<id>/token/<token>``) so the web UI and other clients can log in
again right away. See :class:`CompalClient`.
"""

from .auth import AuthManager
from .client import CompalClient
from .constants import (
    API_PATH,
    BAND_2G,
    BAND_5G,
    BANDS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    HOSTS_TIMEOUT,
    LOCKOUT_FAILURE_LIMIT,
    TOKEN_TTL,
)
from .exceptions import (
    CompalAPIError,
    CompalAuthError,
    CompalError,
    CompalLockoutError,
    CompalNetworkError,
    CompalSessionBusyError,
    CompalValidationError,
)
from .models import (
    CableModemState,
    DownstreamChannel,
    EventLogEntry,
    Host,
    Ipv6Info,
    LanInfo,
    ModemMode,
    Registration,
    ServiceFlow,
    SystemInfo,
    UpstreamChannel,
    WifiConfig,
    WifiState,
)

__version__ = "1.1.0"

__all__ = [
    # Main client
    "CompalClient",
    "AuthManager",
    # Exceptions
    "CompalError",
    "CompalAPIError",
    "CompalAuthError",
    "CompalLockoutError",
    "CompalSessionBusyError",
    "CompalNetworkError",
    "CompalValidationError",
    # Models
    "SystemInfo",
    "ModemMode",
    "LanInfo",
    "Ipv6Info",
    "CableModemState",
    "DownstreamChannel",
    "UpstreamChannel",
    "ServiceFlow",
    "WifiConfig",
    "WifiState",
    "Host",
    "EventLogEntry",
    "Registration",
    # Constants
    "API_PATH",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_TIMEOUT",
    "HOSTS_TIMEOUT",
    "TOKEN_TTL",
    "LOCKOUT_FAILURE_LIMIT",
    "BAND_2G",
    "BAND_5G",
    "BANDS",
]
