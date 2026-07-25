"""
High-level async client for Liberty Global cable gateways.

These are the DOCSIS 3.0/3.1 gateways Liberty Global and its sister operators
ship to subscribers -- Ziggo's "SmartWifi modem", UPC's "Connect Box", Virgin
Media's "Hub", and the Sunrise/Yallo/Unitymedia equivalents. They all run the
same LG-RDK firmware and expose the same ``/rest/v1`` admin API. See
:data:`~liberty_global_gateway.constants.KNOWN_MODELS`.

Example::

    import asyncio
    from liberty_global_gateway import LibertyGatewayClient

    async def main():
        async with LibertyGatewayClient("192.168.178.1", "admin-password") as client:
            await client.login()
            print((await client.get_system_info()).software_version)
            for ch in await client.get_downstream_channels():
                print(ch.channel_id, ch.power, "dBmV", ch.snr, "dB")

    asyncio.run(main())

The router allows a single authenticated session at a time. The client
establishes one session per :meth:`login`, reuses it for a burst of reads, and
releases the slot immediately on :meth:`logout` / :meth:`close` via
``DELETE /user/<id>/token/<token>`` -- so the web UI and other clients can log
in again right away, without waiting out
:data:`~liberty_global_gateway.constants.TOKEN_TTL`.

A small part of the API needs no credentials at all: see :func:`probe`, which
identifies a gateway from ``/rest/v1/system/localization`` alone.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp

from .auth import AuthManager
from .constants import (
    API_PATH,
    BAND_2G,
    BAND_5G,
    BANDS,
    DEFAULT_PORT,
    DEFAULT_SCHEME,
    DEFAULT_TIMEOUT,
    ERR_SESSION_BUSY,
    HOSTS_TIMEOUT,
    LOCALIZATION_PATH,
    PROBE_TIMEOUT,
    USER_AGENT,
)
from .exceptions import (
    GatewayAPIError,
    GatewayNetworkError,
    GatewaySessionBusyError,
    GatewayValidationError,
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
    Led,
    Ipv6Info,
    LanInfo,
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


def _as_bool(value: Any) -> Optional[bool]:
    """Coerce an API truthy/falsey value to bool, preserving None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on", "enabled")
    return bool(value)


async def probe(
    host: str,
    *,
    session: Optional[aiohttp.ClientSession] = None,
    port: int = DEFAULT_PORT,
    scheme: str = DEFAULT_SCHEME,
    verify_ssl: bool = False,
    timeout: float = PROBE_TIMEOUT,
) -> Optional[Localization]:
    """Identify a Liberty Global gateway at ``host`` without credentials.

    ``/rest/v1/system/localization`` is served unauthenticated, so this can
    check whether an arbitrary address is one of these gateways -- and which
    model and operator it is -- before prompting anyone for a password.

    Returns the parsed :class:`~liberty_global_gateway.models.Localization` on
    success, or ``None`` if the host is unreachable, is not a gateway, or
    answers with something unrecognisable. It never raises for an ordinary
    "that isn't a gateway" outcome, which keeps discovery call sites simple.
    """
    if not host:
        raise GatewayValidationError("host is required")

    own_session = session is None
    session = session or aiohttp.ClientSession()
    url = f"{scheme}://{host}:{port}{API_PATH}{LOCALIZATION_PATH}"
    try:
        async with session.get(
            url,
            headers={"User-Agent": USER_AGENT},
            ssl=None if verify_ssl else False,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                return None
            try:
                body = await resp.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError):
                return None
    except (asyncio.TimeoutError, aiohttp.ClientError, OSError):
        return None
    finally:
        if own_session:
            await session.close()

    if not isinstance(body, dict) or "localization" not in body:
        return None
    localization = Localization.from_api(body)
    # A gateway always reports at least a model; anything else is some other
    # device that happens to answer on this path.
    if not localization.model_name:
        return None
    return localization


class LibertyGatewayClient:
    """High-level client for a single Liberty Global cable gateway."""

    def __init__(
        self,
        host: str,
        password: str,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        port: int = DEFAULT_PORT,
        scheme: str = DEFAULT_SCHEME,
        verify_ssl: bool = False,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        if not host:
            raise GatewayValidationError("host is required")
        if not password:
            raise GatewayValidationError("password is required")
        self._host = host
        self._base_url = f"{scheme}://{host}:{port}"
        self._timeout = timeout
        self._ssl: Optional[bool] = None if verify_ssl else False
        self._owns_session = session is None
        self._session = session or aiohttp.ClientSession()
        self._auth = AuthManager(
            self._session,
            self._base_url,
            password,
            ssl=self._ssl,
            timeout=timeout,
        )

    # -- construction ---------------------------------------------------------

    @classmethod
    def create(
        cls,
        host: str,
        password: str,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        **kwargs: Any,
    ) -> "LibertyGatewayClient":
        """Alias for the constructor, mirroring the sibling ``basicfit`` client."""
        return cls(host, password, session=session, **kwargs)

    @property
    def auth(self) -> AuthManager:
        """The underlying auth manager (exposes the current token)."""
        return self._auth

    @property
    def host(self) -> str:
        """The router host this client talks to."""
        return self._host

    async def login(self, *, check_lockout: bool = True) -> None:
        """Establish the authenticated session (see :meth:`AuthManager.async_login`)."""
        await self._auth.async_login(check_lockout=check_lockout)

    async def get_lockout(self) -> tuple[int, int]:
        """Return ``(contiguous_failures, lockout_seconds)`` without logging in."""
        return await self._auth.async_get_lockout()

    async def logout(self) -> bool:
        """Release the router's single login slot immediately.

        Sends the gateway's logout (``DELETE /user/<id>/token/<token>``) so the
        one session becomes free again without waiting for the idle timeout.
        Safe to call when not logged in. See :meth:`AuthManager.async_logout`.
        """
        return await self._auth.async_logout()

    async def close(self) -> None:
        """Log out (freeing the slot) and close the session if we created it."""
        await self._auth.async_logout()
        if self._owns_session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "LibertyGatewayClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # -- low level ------------------------------------------------------------

    async def _get(self, path: str, *, timeout: float | None = None) -> Any:
        """Authenticated GET with a single re-login retry on ``401``."""
        if not self._auth.token:
            await self.login()

        status, data = await self._raw("GET", path, timeout=timeout)
        if status == 401:
            # Token expired mid-session; the slot is now free, so re-login once.
            self._auth.clear()
            await self._auth.async_login()
            status, data = await self._raw("GET", path, timeout=timeout)

        if status == 503 or (isinstance(data, dict) and data.get("errorCode") == ERR_SESSION_BUSY):
            raise GatewaySessionBusyError(f"{path}: router session slot is busy")
        if status >= 400:
            message = data.get("message") if isinstance(data, dict) else None
            error_code = data.get("errorCode") if isinstance(data, dict) else None
            raise GatewayAPIError(message or f"{path} failed", status_code=status, error_code=error_code)
        return data

    async def _post(self, path: str, json: Any = None) -> Any:
        """Authenticated POST (used for actions such as reboot)."""
        if not self._auth.token:
            await self.login()
        status, data = await self._raw("POST", path, json=json)
        if status >= 400:
            error_code = data.get("errorCode") if isinstance(data, dict) else None
            raise GatewayAPIError(f"{path} failed", status_code=status, error_code=error_code)
        return data

    async def _put(self, path: str, json: Any = None) -> Any:
        """Authenticated PUT (used to change settings)."""
        if not self._auth.token:
            await self.login()
        status, data = await self._raw("PUT", path, json=json)
        if status >= 400:
            error_code = data.get("errorCode") if isinstance(data, dict) else None
            raise GatewayAPIError(f"{path} failed", status_code=status, error_code=error_code)
        return data

    async def _raw(self, method: str, path: str, json: Any = None,
                   timeout: float | None = None):
        headers = {"User-Agent": USER_AGENT, **self._auth.auth_header()}
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{API_PATH}{path}",
                headers=headers,
                json=json,
                ssl=self._ssl,
                timeout=aiohttp.ClientTimeout(total=timeout or self._timeout),
            ) as resp:
                try:
                    body = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    body = None
                return resp.status, body
        except asyncio.TimeoutError as err:
            raise GatewayNetworkError(f"request to {path} timed out") from err
        except aiohttp.ClientError as err:
            raise GatewayNetworkError(f"request to {path} failed: {err}") from err

    # -- system ---------------------------------------------------------------

    async def get_localization(self) -> Localization:
        """Operator skin, product name and model (``/system/localization``).

        The endpoint itself needs no authentication -- see the module-level
        :func:`probe` for the credential-free version used by discovery.
        """
        return Localization.from_api(await self._get(LOCALIZATION_PATH))

    async def get_system_info(self) -> SystemInfo:
        """Model, firmware and hardware revision."""
        return SystemInfo.from_api(await self._get("/system/info"))

    async def get_modem_mode(self) -> ModemMode:
        """Whether the gateway is in bridge/modem mode."""
        return ModemMode.from_api(await self._get("/system/modemmode"))

    # -- network --------------------------------------------------------------

    async def get_lan_info(self) -> LanInfo:
        """LAN IPv4 address and subnet."""
        return LanInfo.from_api(await self._get("/network/ipv4/info"))

    async def get_ipv6_info(self) -> Ipv6Info:
        """LAN IPv6 delegated prefix."""
        return Ipv6Info.from_api(await self._get("/network/ipv6/info"))

    async def get_hosts(self, connected_only: bool = True) -> list[Host]:
        """Devices in the router's DHCP/association table.

        With ``connected_only`` (the default) only currently-connected devices
        are returned.
        """
        query = "?connectedOnly=true" if connected_only else ""
        # The hosts table is assembled on demand and is markedly slower than the
        # other endpoints, so give it a more generous timeout of its own.
        data = await self._get(f"/network/hosts{query}", timeout=HOSTS_TIMEOUT)
        hosts = ((data or {}).get("hosts") or {}).get("hosts") or []
        return [Host.from_api(h) for h in hosts]

    # -- cable modem / DOCSIS -------------------------------------------------

    async def get_cable_modem_state(self) -> CableModemState:
        """DOCSIS registration state, uptime and identifiers."""
        return CableModemState.from_api(await self._get("/cablemodem/state"))

    async def get_downstream_channels(self) -> list[DownstreamChannel]:
        """All DOCSIS downstream channels."""
        data = await self._get("/cablemodem/downstream")
        channels = ((data or {}).get("downstream") or {}).get("channels") or []
        return [DownstreamChannel.from_api(c) for c in channels]

    async def get_upstream_channels(self) -> list[UpstreamChannel]:
        """All DOCSIS upstream channels (SC-QAM and OFDMA)."""
        data = await self._get("/cablemodem/upstream")
        channels = ((data or {}).get("upstream") or {}).get("channels") or []
        return [UpstreamChannel.from_api(c) for c in channels]

    async def get_service_flows(self) -> list[ServiceFlow]:
        """Provisioned DOCSIS service flows (the plan's rate caps)."""
        data = await self._get("/cablemodem/serviceflows")
        flows = (data or {}).get("serviceFlows") or []
        return [ServiceFlow.from_api(f) for f in flows]

    async def get_registration(self) -> Registration:
        """DOCSIS registration summary (complete / downstream locked)."""
        return Registration.from_api(await self._get("/cablemodem/registration"))

    async def get_event_log(self) -> list[EventLogEntry]:
        """Cable-modem event log, newest entry first."""
        data = await self._get("/cablemodem/eventlog")
        entries = (data or {}).get("eventlog") or []
        return [EventLogEntry.from_api(e) for e in entries]

    # -- wifi -----------------------------------------------------------------

    async def get_wifi_config(self, band: str) -> WifiConfig:
        """Configuration of one band (``"band2g"`` or ``"band5g"``)."""
        band = self._check_band(band)
        return WifiConfig.from_api(band, await self._get(f"/wifi/{band}/config"))

    async def get_wifi_state(self, band: str) -> WifiState:
        """Operational state of one band (``"band2g"`` or ``"band5g"``)."""
        band = self._check_band(band)
        return WifiState.from_api(band, await self._get(f"/wifi/{band}/state"))

    async def get_wifi_configs(self) -> dict[str, WifiConfig]:
        """Configuration of both Wi-Fi bands, keyed by band."""
        return {
            BAND_2G: await self.get_wifi_config(BAND_2G),
            BAND_5G: await self.get_wifi_config(BAND_5G),
        }

    async def get_wifi_states(self) -> dict[str, WifiState]:
        """Operational state of both Wi-Fi bands, keyed by band."""
        return {
            BAND_2G: await self.get_wifi_state(BAND_2G),
            BAND_5G: await self.get_wifi_state(BAND_5G),
        }

    async def get_guest_wifi_config(self, band: str) -> GuestWifiConfig:
        """Guest Wi-Fi config for one band (SSID + enabled; no passphrase)."""
        band = self._check_band(band)
        return GuestWifiConfig.from_api(
            band, await self._get(f"/wifi/{band}/guest/config"))

    async def get_guest_wifi_configs(self) -> dict[str, GuestWifiConfig]:
        """Guest Wi-Fi config for both bands, keyed by band."""
        return {
            BAND_2G: await self.get_guest_wifi_config(BAND_2G),
            BAND_5G: await self.get_guest_wifi_config(BAND_5G),
        }

    async def get_smart_wifi(self) -> Optional[bool]:
        """Whether Smart Wi-Fi (band steering) is enabled."""
        data = await self._get("/wifi/smartmode")
        return _as_bool(((data or {}).get("smartmode") or {}).get("enable"))

    @staticmethod
    def _check_band(band: str) -> str:
        if band not in BANDS:
            raise GatewayValidationError(f"band must be one of {BANDS}, got {band!r}")
        return band

    # -- WAN / system ---------------------------------------------------------

    async def get_provisioning(self) -> Provisioning:
        """WAN/provisioning info: public IPv4/IPv6, gateway, DNS, lease times."""
        return Provisioning.from_api(await self._get("/system/gateway/provisioning"))

    async def get_software_update(self) -> SoftwareUpdate:
        """Firmware update status."""
        return SoftwareUpdate.from_api(await self._get("/system/softwareupdate"))

    # -- network features -----------------------------------------------------

    async def get_upnp(self) -> Optional[bool]:
        """Whether UPnP IGD is enabled."""
        data = await self._get("/network/upnp")
        return _as_bool(((data or {}).get("upnp") or {}).get("enable"))

    async def get_dmz(self) -> Dmz:
        """DMZ configuration (enabled + internal host)."""
        return Dmz.from_api(await self._get("/network/ipv4/dmz"))

    async def get_firewall(self, ip_version: str = "ipv4") -> Firewall:
        """Firewall configuration for ``"ipv4"`` (default) or ``"ipv6"``."""
        if ip_version not in ("ipv4", "ipv6"):
            raise GatewayValidationError("ip_version must be 'ipv4' or 'ipv6'")
        return Firewall.from_api(await self._get(f"/network/{ip_version}/firewall"))

    async def get_port_forwarding(self) -> list[PortForwardRule]:
        """Configured port-forwarding rules."""
        data = await self._get("/network/portforwarding")
        rules = ((data or {}).get("portforwarding") or {}).get("rules") or []
        return [PortForwardRule.from_api(r) for r in rules]

    async def get_reserved_ips(self) -> list[ReservedIp]:
        """Static DHCP reservations (MAC → IP)."""
        data = await self._get("/network/reservedipaddresses")
        return [ReservedIp.from_api(r) for r in ((data or {}).get("rules") or [])]

    async def get_mta_lines(self) -> list[MtaLine]:
        """Telephony (MTA) lines and whether each is operational."""
        data = await self._get("/mta/lines")
        return [MtaLine.from_api(x) for x in ((data or {}).get("lines") or [])]

    async def get_dhcp(self, ip_version: str = "ipv4") -> DhcpServer:
        """LAN DHCP server config for ``"ipv4"`` (default) or ``"ipv6"``."""
        if ip_version not in ("ipv4", "ipv6"):
            raise GatewayValidationError("ip_version must be 'ipv4' or 'ipv6'")
        return DhcpServer.from_api(await self._get(f"/network/{ip_version}/dhcp"))

    async def get_led(self) -> Led:
        """Front-panel LED brightness/auto settings."""
        return Led.from_api(await self._get("/network/ledlight"))

    async def get_wps_enabled(self, band: str) -> Optional[bool]:
        """Whether WPS is enabled for a band."""
        band = self._check_band(band)
        data = await self._get(f"/wifi/{band}/wps/config")
        return _as_bool(((data or {}).get("config") or {}).get("enable"))

    async def get_mac_filters(self) -> list[dict]:
        """MAC-filter rules (raw entries)."""
        data = await self._get("/network/macfilters")
        return list(((data or {}).get("macfilters") or {}).get("rules") or [])

    async def get_port_triggers(self) -> list[dict]:
        """Port-trigger rules (raw entries)."""
        data = await self._get("/network/porttriggers")
        return list(((data or {}).get("porttriggers") or {}).get("rules") or [])

    async def get_ip_port_filters(self) -> list[dict]:
        """IP/port-filter rules (IPv4 + IPv6 combined, raw entries)."""
        data = await self._get("/network/ipportfilters")
        f = (data or {}).get("ipportfilters") or {}
        return list((f.get("ipv4") or {}).get("rules") or []) + \
            list((f.get("ipv6") or {}).get("rules") or [])

    # -- writes ---------------------------------------------------------------

    async def set_upnp(self, enable: bool) -> None:
        """Enable or disable UPnP IGD."""
        await self._put("/network/upnp", {"upnp": {"enable": bool(enable)}})

    async def set_led(self, *, brightness: Optional[int] = None,
                      automode: Optional[bool] = None) -> None:
        """Set the front-panel LED brightness (0-100) and/or auto mode.

        Only the given fields change; the rest keep their current values. The
        firmware expects string values, which this method handles.
        """
        current = await self.get_led()
        new_bright = current.brightness if brightness is None else int(brightness)
        new_auto = current.automode if automode is None else bool(automode)
        if new_bright is not None:
            new_bright = max(0, min(100, new_bright))
        # Note: GET wraps this in {"value": {...}} but the PUT body is flat.
        await self._put("/network/ledlight", {
            "brightness": str(new_bright if new_bright is not None else 100),
            "automode": "true" if new_auto else "false",
        })

    # -- actions --------------------------------------------------------------

    async def reboot(self) -> None:
        """Reboot the gateway (``POST /system/reboot``).

        This drops the WAN connection for a minute or two. It is a deliberate,
        destructive action — call it only on explicit user intent.
        """
        await self._post("/system/reboot")
