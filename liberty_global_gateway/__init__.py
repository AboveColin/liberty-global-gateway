"""
liberty_global_gateway — an unofficial async Python client for Liberty Global
cable gateways.

Liberty Global and its sister operators ship a family of DOCSIS cable gateways
that all run the same LG-RDK firmware: Ziggo's "SmartWifi modem", UPC's
"Connect Box", Virgin Media's "Hub", and the Sunrise / Yallo / Unitymedia
equivalents. This library talks to their shared ``/rest/v1`` admin API to read
system info, DOCSIS downstream/upstream channels, cable-modem state,
provisioned service flows, Wi-Fi configuration/state, firewall and DMZ status,
port forwards and the connected-hosts table; it can toggle UPnP and the status
LEDs, and reboot the gateway.

Known models are listed in :data:`~liberty_global_gateway.constants.KNOWN_MODELS`
and operator skins in :data:`~liberty_global_gateway.constants.KNOWN_SKINS`.

The router allows a single authenticated session. The client logs in, reads in
a burst, then calls :meth:`LibertyGatewayClient.logout` to release the slot
immediately (``DELETE /user/<id>/token/<token>``) so the web UI and other
clients can log in again right away. See :class:`LibertyGatewayClient`.

:func:`probe` identifies a gateway with no credentials at all, which is what
makes zero-configuration discovery possible.

This package was previously released as ``compalf3896lg``; the old ``Compal*``
class names still work as aliases.
"""

from .auth import AuthManager
from .client import LibertyGatewayClient, probe
from .constants import (
    API_PATH,
    BAND_2G,
    BAND_5G,
    BANDS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    HOSTS_TIMEOUT,
    KNOWN_MANUFACTURERS,
    KNOWN_MODELS,
    KNOWN_SKINS,
    LOCALIZATION_PATH,
    LOCKOUT_FAILURE_LIMIT,
    PROBE_TIMEOUT,
    TOKEN_TTL,
)
from .exceptions import (
    # Current names
    GatewayAPIError,
    GatewayAuthError,
    GatewayError,
    GatewayLockoutError,
    GatewayNetworkError,
    GatewaySessionBusyError,
    GatewayValidationError,
    # Pre-rename aliases
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
    DhcpServer,
    Dmz,
    DownstreamChannel,
    EventLogEntry,
    Firewall,
    GuestWifiConfig,
    Host,
    Ipv6Info,
    LanInfo,
    Led,
    Localization,
    ModemMode,
    MtaLine,
    PortForwardRule,
    Provisioning,
    Registration,
    ReservedIp,
    ServiceFlow,
    SoftwareUpdate,
    SystemInfo,
    UpstreamChannel,
    WifiConfig,
    WifiState,
)

#: Pre-rename alias for :class:`LibertyGatewayClient`.
CompalClient = LibertyGatewayClient

__version__ = "2.0.0"

__all__ = [
    # Main client
    "LibertyGatewayClient",
    "AuthManager",
    "probe",
    # Exceptions
    "GatewayError",
    "GatewayAPIError",
    "GatewayAuthError",
    "GatewayLockoutError",
    "GatewaySessionBusyError",
    "GatewayNetworkError",
    "GatewayValidationError",
    # Models
    "Localization",
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
    "Provisioning",
    "SoftwareUpdate",
    "Dmz",
    "Firewall",
    "GuestWifiConfig",
    "PortForwardRule",
    "ReservedIp",
    "MtaLine",
    "Led",
    "DhcpServer",
    # Constants
    "API_PATH",
    "LOCALIZATION_PATH",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_TIMEOUT",
    "HOSTS_TIMEOUT",
    "PROBE_TIMEOUT",
    "TOKEN_TTL",
    "LOCKOUT_FAILURE_LIMIT",
    "KNOWN_MODELS",
    "KNOWN_SKINS",
    "KNOWN_MANUFACTURERS",
    "BAND_2G",
    "BAND_5G",
    "BANDS",
    # Pre-rename aliases
    "CompalClient",
    "CompalError",
    "CompalAPIError",
    "CompalAuthError",
    "CompalLockoutError",
    "CompalSessionBusyError",
    "CompalNetworkError",
    "CompalValidationError",
]
