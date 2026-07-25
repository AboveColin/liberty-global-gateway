"""
Typed models for the Liberty Global gateway API.

Each model exposes a ``from_api`` classmethod that maps the raw JSON the router
returns into a stable, documented shape. The original payload is kept on
``raw`` for anything not modelled yet.

The Wi-Fi models deliberately do **not** surface the pre-shared key as a
first-class field — it is only present in ``raw`` — so that downstream
consumers (e.g. a Home Assistant sensor) don't leak it by accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


def _num(value: Any) -> Optional[float]:
    """Best-effort float conversion; ``None``/``""`` -> ``None``."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    """Best-effort int conversion; ``None``/``""`` -> ``None``."""
    num = _num(value)
    return int(num) if num is not None else None


def _bool(value: Any) -> Optional[bool]:
    """Best-effort bool conversion tolerant of ``"true"``/``"false"`` strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes", "up", "enabled"):
            return True
        if low in ("false", "0", "no", "down", "disabled"):
            return False
    return None


@dataclass
class Localization:
    """Operator branding and model identification (``/system/localization``).

    Unlike every other endpoint, this one answers without authentication,
    which makes it the cheapest way to positively identify a gateway --
    useful for discovery, before any password is asked for.
    """

    skin: Optional[str]
    """Operator identifier, e.g. ``"ziggo"``. See
    :data:`~liberty_global_gateway.constants.KNOWN_SKINS`."""

    product_name: Optional[str]
    """The operator's marketing name, e.g. ``"SmartWifi modem"``."""

    model_name: Optional[str]
    """Hardware model, e.g. ``"F3896LG"``. See
    :data:`~liberty_global_gateway.constants.KNOWN_MODELS`."""

    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Localization":
        """Build from a ``/system/localization`` payload."""
        loc = (payload or {}).get("localization") or {}
        return cls(
            skin=loc.get("skin"),
            product_name=loc.get("productName"),
            model_name=loc.get("modelName"),
            raw=payload or {},
        )

    @property
    def brand(self) -> Optional[str]:
        """The operator's display name, e.g. ``"Ziggo"``.

        Falls back to a title-cased version of :attr:`skin` for operators the
        shipped table does not know about yet.
        """
        if not self.skin:
            return None
        from .constants import KNOWN_SKINS  # local import: avoids a cycle

        return KNOWN_SKINS.get(self.skin, self.skin.replace("_", " ").title())

    @property
    def generation(self) -> Optional[str]:
        """Hardware generation (``mv1``/``mv2+``/``mv3``), if the model is known."""
        if not self.model_name:
            return None
        from .constants import KNOWN_MODELS  # local import: avoids a cycle

        return KNOWN_MODELS.get(self.model_name.upper())

    @property
    def display_name(self) -> str:
        """A human-friendly device name, e.g. ``"Ziggo SmartWifi modem (F3896LG)"``.

        Degrades gracefully when the router omits any of the three fields.
        """
        head = " ".join(p for p in (self.brand, self.product_name) if p)
        if not head:
            head = "Liberty Global Cable Gateway"
        return f"{head} ({self.model_name})" if self.model_name else head


@dataclass
class SystemInfo:
    """Basic model / firmware identification (``/system/info``)."""

    model_name: Optional[str]
    software_version: Optional[str]
    hardware_version: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "SystemInfo":
        """Build from a ``/system/info`` payload."""
        info = (payload or {}).get("info") or {}
        return cls(
            model_name=info.get("modelName"),
            software_version=info.get("softwareVersion"),
            hardware_version=info.get("hardwareVersion"),
            raw=payload or {},
        )


@dataclass
class ModemMode:
    """Router vs. bridge mode (``/system/modemmode``)."""

    bridge_mode: Optional[bool]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "ModemMode":
        """Build from a ``/system/modemmode`` payload."""
        mode = (payload or {}).get("modemmode") or {}
        return cls(bridge_mode=_bool(mode.get("enable")), raw=payload or {})


@dataclass
class LanInfo:
    """LAN IPv4 configuration (``/network/ipv4/info``)."""

    lan_ip: Optional[str]
    lan_subnet: Optional[str]
    lan_subnet_mask: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "LanInfo":
        """Build from a ``/network/ipv4/info`` payload."""
        info = (payload or {}).get("info") or {}
        return cls(
            lan_ip=info.get("lanIpAddress"),
            lan_subnet=info.get("lanSubnet"),
            lan_subnet_mask=info.get("lanSubnetMask"),
            raw=payload or {},
        )


@dataclass
class Ipv6Info:
    """LAN IPv6 delegated prefix (``/network/ipv6/info``)."""

    prefix_address: Optional[str]
    prefix_length: Optional[int]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Ipv6Info":
        """Build from a ``/network/ipv6/info`` payload."""
        info = (payload or {}).get("info") or {}
        return cls(
            prefix_address=info.get("lanNetworkPrefixAddress"),
            prefix_length=_int(info.get("lanNetworkPrefixLength")),
            raw=payload or {},
        )


@dataclass
class CableModemState:
    """DOCSIS cable-modem registration state (``/cablemodem/state``)."""

    status: Optional[str]
    service_status: Optional[str]
    docsis_version: Optional[str]
    mac_address: Optional[str]
    serial_number: Optional[str]
    uptime: Optional[int]
    access_allowed: Optional[bool]
    max_cpes: Optional[int]
    baseline_privacy_enabled: Optional[bool]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def operational(self) -> bool:
        """``True`` when the modem is registered and in full service."""
        return (self.status or "").lower() == "operational"

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "CableModemState":
        """Build from a ``/cablemodem/state`` payload."""
        cm = (payload or {}).get("cablemodem") or {}
        return cls(
            status=cm.get("status"),
            service_status=cm.get("serviceStatus"),
            docsis_version=cm.get("docsisVersion"),
            mac_address=cm.get("macAddress"),
            serial_number=cm.get("serialNumber"),
            uptime=_int(cm.get("upTime")),
            access_allowed=_bool(cm.get("accessAllowed")),
            max_cpes=_int(cm.get("maxCPEs")),
            baseline_privacy_enabled=_bool(cm.get("baselinePrivacyEnabled")),
            raw=payload or {},
        )


@dataclass
class DownstreamChannel:
    """A single DOCSIS downstream channel (``/cablemodem/downstream``)."""

    channel_id: Optional[int]
    channel_type: Optional[str]
    frequency: Optional[int]
    power: Optional[float]
    snr: Optional[float]
    rx_mer: Optional[float]
    modulation: Optional[str]
    corrected_errors: Optional[int]
    uncorrected_errors: Optional[int]
    lock_status: Optional[bool]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "DownstreamChannel":
        """Build from one ``downstream.channels`` entry."""
        return cls(
            channel_id=_int(payload.get("channelId")),
            channel_type=payload.get("channelType"),
            frequency=_int(payload.get("frequency")),
            power=_num(payload.get("power")),
            snr=_num(payload.get("snr")),
            rx_mer=_num(payload.get("rxMer")),
            modulation=payload.get("modulation"),
            corrected_errors=_int(payload.get("correctedErrors")),
            uncorrected_errors=_int(payload.get("uncorrectedErrors")),
            lock_status=_bool(payload.get("lockStatus")),
            raw=payload,
        )


@dataclass
class UpstreamChannel:
    """A single DOCSIS upstream channel (``/cablemodem/upstream``).

    Covers both SC-QAM (``atdma``) and OFDMA channels; OFDMA-only fields are
    ``None`` on SC-QAM channels and vice versa.
    """

    channel_id: Optional[int]
    channel_type: Optional[str]
    frequency: Optional[int]
    power: Optional[float]
    modulation: Optional[str]
    symbol_rate: Optional[int]
    channel_width: Optional[int]
    lock_status: Optional[bool]
    t3_timeout: Optional[int]
    t4_timeout: Optional[int]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "UpstreamChannel":
        """Build from one ``upstream.channels`` entry."""
        return cls(
            channel_id=_int(payload.get("channelId")),
            channel_type=payload.get("channelType"),
            frequency=_int(payload.get("frequency")),
            power=_num(payload.get("power")),
            modulation=payload.get("modulation"),
            symbol_rate=_int(payload.get("symbolRate")),
            channel_width=_int(payload.get("channelWidth")),
            lock_status=_bool(payload.get("lockStatus")),
            t3_timeout=_int(payload.get("t3Timeout")),
            t4_timeout=_int(payload.get("t4Timeout")),
            raw=payload,
        )


@dataclass
class ServiceFlow:
    """A provisioned DOCSIS service flow (``/cablemodem/serviceflows``).

    ``max_traffic_rate`` is the provisioned rate cap in bits/second — the
    downstream/upstream flows give the effective plan speed.
    """

    service_flow_id: Optional[int]
    direction: Optional[str]
    max_traffic_rate: Optional[int]
    max_traffic_burst: Optional[int]
    min_reserved_rate: Optional[int]
    schedule_type: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def max_traffic_rate_mbps(self) -> Optional[float]:
        """``max_traffic_rate`` expressed in Mbit/s."""
        return round(self.max_traffic_rate / 1_000_000, 1) if self.max_traffic_rate else None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "ServiceFlow":
        """Build from one ``serviceFlows`` entry."""
        flow = (payload or {}).get("serviceFlow") or payload or {}
        return cls(
            service_flow_id=_int(flow.get("serviceFlowId")),
            direction=flow.get("direction"),
            max_traffic_rate=_int(flow.get("maxTrafficRate")),
            max_traffic_burst=_int(flow.get("maxTrafficBurst")),
            min_reserved_rate=_int(flow.get("minReservedRate")),
            schedule_type=flow.get("scheduleType"),
            raw=payload or {},
        )


@dataclass
class WifiConfig:
    """Configuration of one Wi-Fi band (``/wifi/band{2,5}g/config``).

    The pre-shared key is intentionally **not** exposed as a field; it remains
    available in ``raw`` for callers that genuinely need it.
    """

    band: str
    enable: Optional[bool]
    ssid: Optional[str]
    broadcast_ssid: Optional[bool]
    security_type: Optional[str]
    encryption_type: Optional[str]
    channel_number: Optional[int]
    channel_width: Optional[str]
    mode: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, band: str, payload: dict[str, Any]) -> "WifiConfig":
        """Build from a ``/wifi/<band>/config`` payload."""
        config = (payload or {}).get("config") or {}
        ssid = config.get("ssid") or {}
        radio = config.get("radio") or {}
        return cls(
            band=band,
            enable=_bool(config.get("enable")),
            ssid=ssid.get("ssid"),
            broadcast_ssid=_bool(ssid.get("broadcastSsid")),
            security_type=ssid.get("securityType"),
            encryption_type=ssid.get("encryptionType"),
            channel_number=_int(radio.get("channelNumber")),
            channel_width=radio.get("channelWidth"),
            mode=radio.get("mode"),
            raw=payload or {},
        )


@dataclass
class WifiState:
    """Operational state of one Wi-Fi band (``/wifi/band{2,5}g/state``)."""

    band: str
    enable: Optional[bool]
    status: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def up(self) -> bool:
        """``True`` when the radio reports itself up."""
        return (self.status or "").lower() == "up"

    @classmethod
    def from_api(cls, band: str, payload: dict[str, Any]) -> "WifiState":
        """Build from a ``/wifi/<band>/state`` payload."""
        state = (payload or {}).get("state") or {}
        return cls(
            band=band,
            enable=_bool(state.get("enable")),
            status=state.get("status"),
            raw=payload or {},
        )


@dataclass
class EventLogEntry:
    """One entry from the cable-modem event log (``/cablemodem/eventlog``)."""

    time: Optional[str]
    priority: Optional[str]
    message: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "EventLogEntry":
        """Build from one ``eventlog`` entry."""
        return cls(
            time=payload.get("time"),
            priority=payload.get("priority"),
            message=payload.get("message"),
            raw=payload or {},
        )


@dataclass
class Registration:
    """DOCSIS registration summary (``/cablemodem/registration``)."""

    registration_complete: Optional[bool]
    downstream_locked: Optional[bool]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Registration":
        """Build from a ``/cablemodem/registration`` payload."""
        reg = (payload or {}).get("registration") or {}
        return cls(
            registration_complete=_bool(reg.get("registrationComplete")),
            downstream_locked=_bool(reg.get("downstreamLocked")),
            raw=payload or {},
        )


@dataclass
class Provisioning:
    """WAN/provisioning info (``/system/gateway/provisioning``)."""

    mode: Optional[str]
    wan_mac: Optional[str]
    ipv4_address: Optional[str]
    ipv4_gateway: Optional[str]
    ipv4_dns: list[str] = field(default_factory=list)
    ipv4_lease_time: Optional[int] = None
    ipv6_global_address: Optional[str] = None
    ipv6_gateway: Optional[str] = None
    ipv6_dns: list[str] = field(default_factory=list)
    dslite_enabled: Optional[bool] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Provisioning":
        p = (payload or {}).get("provisioning") or {}
        v4 = p.get("ipv4") or {}
        v6 = p.get("ipv6") or {}
        return cls(
            mode=p.get("mode"),
            wan_mac=p.get("macAddress"),
            ipv4_address=v4.get("address"),
            ipv4_gateway=v4.get("defaultGateway"),
            ipv4_dns=list(v4.get("dnsServers") or []),
            ipv4_lease_time=_int(v4.get("leaseTime")),
            ipv6_global_address=v6.get("globalAddress"),
            ipv6_gateway=v6.get("defaultGateway"),
            ipv6_dns=list(v6.get("dnsServers") or []),
            dslite_enabled=_bool((p.get("dsLite") or {}).get("enable")),
            raw=payload or {},
        )


@dataclass
class Led:
    """Front-panel LED settings (``/network/ledlight``)."""

    brightness: Optional[int]
    automode: Optional[bool]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Led":
        v = (payload or {}).get("value") or {}
        return cls(brightness=_int(v.get("brightness")),
                   automode=_bool(v.get("automode")), raw=payload or {})


@dataclass
class DhcpServer:
    """LAN DHCP server config (``/network/ipv4/dhcp``)."""

    enabled: Optional[bool]
    min_address: Optional[str]
    max_address: Optional[str]
    subnet_mask: Optional[str]
    lease_time: Optional[int]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "DhcpServer":
        d = (payload or {}).get("dhcp") or {}
        return cls(
            enabled=_bool(d.get("enable")),
            min_address=d.get("minAddress"),
            max_address=d.get("maxAddress"),
            subnet_mask=d.get("subnetMask"),
            lease_time=_int(d.get("leaseTime")),
            raw=payload or {},
        )


@dataclass
class SoftwareUpdate:
    """Firmware update status (``/system/softwareupdate``)."""

    status: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "SoftwareUpdate":
        return cls(status=((payload or {}).get("softwareUpdate") or {}).get("status"),
                   raw=payload or {})


@dataclass
class Dmz:
    """DMZ config (``/network/ipv4/dmz``)."""

    enabled: Optional[bool]
    internal_ip: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Dmz":
        d = (payload or {}).get("dmz") or {}
        return cls(enabled=_bool(d.get("enable")),
                   internal_ip=d.get("internalIp") or d.get("internalIpAddress"),
                   raw=payload or {})


@dataclass
class Firewall:
    """Firewall config (``/network/ipv4/firewall`` or ipv6)."""

    enabled: Optional[bool]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Firewall":
        f = (payload or {}).get("firewall") or {}
        # Firmware exposes this variously; treat a disabled/off security level as off.
        enabled = f.get("enable")
        if enabled is None and "securityLevel" in f:
            enabled = str(f.get("securityLevel")).lower() not in ("off", "disabled", "none")
        return cls(enabled=_bool(enabled) if enabled is not None else None,
                   raw=payload or {})


@dataclass
class GuestWifiConfig:
    """Guest Wi-Fi config for one band (``/wifi/<band>/guest/config``).

    The passphrase is intentionally **not** captured as a field; it stays only
    inside ``raw`` so callers that surface guest Wi-Fi never leak the key.
    """

    band: str
    enabled: Optional[bool]
    ssid: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, band: str, payload: dict[str, Any]) -> "GuestWifiConfig":
        cfg = (payload or {}).get("config") or {}
        ssid = (cfg.get("ssid") or {}).get("ssid")
        return cls(band=band, enabled=_bool(cfg.get("enable")), ssid=ssid,
                   raw=payload or {})


@dataclass
class PortForwardRule:
    """One port-forwarding rule (``/network/portforwarding``)."""

    id: Optional[int]
    enabled: Optional[bool]
    protocol: Optional[str]
    external_start_port: Optional[int]
    external_end_port: Optional[int]
    local_address: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "PortForwardRule":
        r = (payload or {}).get("rule") or {}
        return cls(
            id=_int(payload.get("id")),
            enabled=_bool(r.get("enable")),
            protocol=r.get("protocol"),
            external_start_port=_int(r.get("externalStartPort")),
            external_end_port=_int(r.get("externalEndPort")),
            local_address=r.get("localAddress"),
            raw=payload or {},
        )


@dataclass
class ReservedIp:
    """A static DHCP reservation (``/network/reservedipaddresses``)."""

    mac_address: Optional[str]
    ip_address: Optional[str]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "ReservedIp":
        return cls(mac_address=payload.get("macAddress"),
                   ip_address=payload.get("ipAddress"), raw=payload or {})


@dataclass
class MtaLine:
    """A telephony (MTA) line (``/mta/lines``)."""

    id: Optional[int]
    enabled: Optional[bool]
    operational: Optional[bool]
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "MtaLine":
        line = (payload or {}).get("line") or {}
        return cls(id=_int(payload.get("id")), enabled=_bool(line.get("enable")),
                   operational=_bool(line.get("operational")), raw=payload or {})


@dataclass
class Host:
    """A device seen by the router's DHCP/association table (``/network/hosts``)."""

    mac_address: Optional[str]
    hostname: Optional[str]
    device_name: Optional[str]
    device_type: Optional[str]
    interface: Optional[str]
    connected: Optional[bool]
    ip_address: Optional[str]
    ipv6_address: Optional[str]
    lease_time_remaining: Optional[int]
    speed: Optional[float]
    band: Optional[str]
    ssid: Optional[str]
    rssi: Optional[int]
    ethernet_port: Optional[int]
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> Optional[str]:
        """Best display name: explicit device name, else hostname, else MAC."""
        return self.device_name or self.hostname or self.mac_address

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Host":
        """Build from one ``hosts.hosts`` entry."""
        config = (payload or {}).get("config") or {}
        wifi = config.get("wifi") or {}
        ethernet = config.get("ethernet") or {}
        ipv4 = config.get("ipv4") or {}
        ipv6 = config.get("ipv6") or {}
        device_name = config.get("deviceName")
        return cls(
            mac_address=payload.get("macAddress"),
            hostname=config.get("hostname"),
            device_name=device_name or None,
            device_type=config.get("deviceType"),
            interface=config.get("interface"),
            connected=_bool(config.get("connected")),
            ip_address=ipv4.get("address"),
            ipv6_address=ipv6.get("address") if isinstance(ipv6, dict) else None,
            lease_time_remaining=_int(ipv4.get("leaseTimeRemaining")),
            speed=_num(config.get("speed")),
            band=wifi.get("band"),
            ssid=wifi.get("ssid"),
            rssi=_int(wifi.get("rssi")),
            ethernet_port=_int(ethernet.get("port")),
            raw=payload or {},
        )
