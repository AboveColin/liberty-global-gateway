"""Tests for the request path, probing and the endpoints.

Three behaviours carry the risk. probe() must never raise for an ordinary
"that is not a gateway" outcome, or discovery call sites fill up with
try/except. A 401 mid-session must cause one re-login and one retry, not a
loop. And set_led reads before it writes, because the PUT replaces both fields
and the GET wraps them in a different shape from the PUT.
"""

from __future__ import annotations

import pytest
from aiohttp import web

from liberty_global_gateway import (
    GatewayAPIError,
    GatewayNetworkError,
    GatewaySessionBusyError,
    GatewayValidationError,
    LibertyGatewayClient,
    probe,
)
from liberty_global_gateway.client import _as_bool
from liberty_global_gateway.constants import BAND_2G, BAND_5G, ERR_SESSION_BUSY

from .conftest import PASSWORD, TOKEN, USER_ID, FakeGateway

LOCALIZATION = {
    "localization": {"skin": "ziggo", "productName": "SmartWifi modem", "modelName": "F3896LG"}
}


class TestProbe:
    """Credential-free identification, which must never raise for a miss."""

    async def test_identifies_a_gateway(self, api: FakeGateway, http) -> None:
        api.json("/system/localization", LOCALIZATION)
        result = await probe(api.host, session=http, port=api.port, scheme="http")
        assert result is not None
        assert result.model_name == "F3896LG"
        assert result.brand == "Ziggo"

    async def test_a_host_is_required(self, http) -> None:
        with pytest.raises(GatewayValidationError, match="host is required"):
            await probe("", session=http)

    async def test_an_unreachable_host_is_a_miss_not_an_error(self, http) -> None:
        assert await probe("127.0.0.1", session=http, port=1, scheme="http") is None

    async def test_a_non_200_is_a_miss(self, api: FakeGateway, http) -> None:
        api.status("/system/localization", 500)
        assert await probe(api.host, session=http, port=api.port, scheme="http") is None

    async def test_a_non_json_body_is_a_miss(self, api: FakeGateway, http) -> None:
        api.text("/system/localization", "<html>hello</html>")
        assert await probe(api.host, session=http, port=api.port, scheme="http") is None

    async def test_json_without_a_localization_key_is_a_miss(
        self, api: FakeGateway, http
    ) -> None:
        # Something else answering on this path is not a gateway.
        api.json("/system/localization", {"hello": "world"})
        assert await probe(api.host, session=http, port=api.port, scheme="http") is None

    async def test_a_localization_without_a_model_is_a_miss(
        self, api: FakeGateway, http
    ) -> None:
        # A gateway always reports at least a model.
        api.json("/system/localization", {"localization": {"skin": "ziggo"}})
        assert await probe(api.host, session=http, port=api.port, scheme="http") is None

    async def test_a_list_where_an_object_belongs_is_a_miss(
        self, api: FakeGateway, http
    ) -> None:
        api.json("/system/localization", [1, 2, 3])
        assert await probe(api.host, session=http, port=api.port, scheme="http") is None

    async def test_probing_sends_no_credentials(self, api: FakeGateway, http) -> None:
        api.json("/system/localization", LOCALIZATION)
        await probe(api.host, session=http, port=api.port, scheme="http")
        assert "Authorization" not in api.requests[-1].headers

    async def test_probe_closes_a_session_it_created(self, api: FakeGateway) -> None:
        result = await probe(api.host, port=api.port, scheme="http")
        assert result is None or result.model_name


class TestRequestPath:
    """Authentication, retries and error mapping on every read."""

    async def test_the_first_read_logs_in_first(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/system/info", {"systemInfo": {"modelName": "F3896LG"}})
        await client.get_system_info()
        assert "/rest/v1/user/login" in api.paths("POST")

    async def test_the_bearer_token_is_sent(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/system/info", {"systemInfo": {}})
        await client.get_system_info()
        assert api.requests[-1].headers["Authorization"] == f"Bearer {TOKEN}"

    async def test_a_401_triggers_one_relogin_and_retry(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.sequence(
            "/system/info",
            (401, {"message": "token expired"}),
            (200, {"systemInfo": {"modelName": "F3896LG"}}),
        )
        info = await client.get_system_info()
        assert info.raw["systemInfo"]["modelName"] == "F3896LG"
        assert api.paths("GET").count("/rest/v1/system/info") == 2

    async def test_a_second_401_is_reported_rather_than_retried_again(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/system/info", {"message": "token expired"}, status=401)
        with pytest.raises(GatewayAPIError) as caught:
            await client.get_system_info()
        assert caught.value.status_code == 401
        assert api.paths("GET").count("/rest/v1/system/info") == 2

    async def test_a_503_is_a_session_busy_error(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.status("/system/info", 503)
        with pytest.raises(GatewaySessionBusyError):
            await client.get_system_info()

    async def test_the_busy_error_code_alone_is_enough(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/system/info", {"errorCode": ERR_SESSION_BUSY}, status=200)
        with pytest.raises(GatewaySessionBusyError):
            await client.get_system_info()

    async def test_an_error_carries_the_status_and_the_error_code(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/system/info", {"message": "no", "errorCode": 4099}, status=400)
        with pytest.raises(GatewayAPIError) as caught:
            await client.get_system_info()
        assert caught.value.status_code == 400
        assert caught.value.error_code == 4099
        assert "errorCode 4099" in str(caught.value)

    async def test_an_error_without_a_message_names_the_path(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.status("/system/info", 500)
        with pytest.raises(GatewayAPIError, match="/system/info failed"):
            await client.get_system_info()

    async def test_an_unreachable_router_is_a_network_error(self, http) -> None:
        client = LibertyGatewayClient("127.0.0.1", PASSWORD, session=http, port=1, scheme="http")
        with pytest.raises(GatewayNetworkError):
            await client.get_system_info()


class TestReads:
    """Each endpoint unwraps a differently shaped envelope."""

    async def test_localization(self, api: FakeGateway, client: LibertyGatewayClient) -> None:
        api.json("/system/localization", LOCALIZATION)
        result = await client.get_localization()
        assert result.display_name == "Ziggo SmartWifi modem (F3896LG)"

    async def test_hosts_are_two_levels_deep(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json(
            "/network/hosts",
            {
                "hosts": {
                    "hosts": [
                        {"macAddress": "aa", "config": {"hostname": "nix1", "connected": True}},
                        {"macAddress": "bb", "config": {"hostname": "nix2", "connected": True}},
                    ]
                }
            },
        )
        assert len(await client.get_hosts()) == 2

    async def test_hosts_default_to_connected_only(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/hosts", {"hosts": {"hosts": []}})
        await client.get_hosts()
        assert api.requests[-1].query.get("connectedOnly") == "true"

    async def test_hosts_can_include_the_disconnected(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/hosts", {"hosts": {"hosts": []}})
        await client.get_hosts(connected_only=False)
        assert "connectedOnly" not in api.requests[-1].query

    async def test_downstream_channels_are_unwrapped(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json(
            "/cablemodem/downstream",
            {"downstream": {"channels": [{"channelId": 1}, {"channelId": 2}]}},
        )
        assert len(await client.get_downstream_channels()) == 2

    async def test_upstream_channels_are_unwrapped(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/cablemodem/upstream", {"upstream": {"channels": [{"channelId": 1}]}})
        assert len(await client.get_upstream_channels()) == 1

    async def test_an_empty_envelope_yields_an_empty_list(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/cablemodem/downstream", {})
        assert await client.get_downstream_channels() == []

    async def test_service_flows_are_unwrapped(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/cablemodem/serviceflows", {"serviceFlows": [{"id": 1}]})
        assert len(await client.get_service_flows()) == 1

    async def test_the_event_log_is_unwrapped(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/cablemodem/eventlog", {"eventlog": [{"text": "boot"}]})
        assert len(await client.get_event_log()) == 1

    async def test_port_forwards_are_two_levels_deep(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/portforwarding", {"portforwarding": {"rules": [{"id": 1}]}})
        assert len(await client.get_port_forwarding()) == 1

    async def test_reserved_ips_are_one_level_deep(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/reservedipaddresses", {"rules": [{"macAddress": "aa"}]})
        assert len(await client.get_reserved_ips()) == 1

    async def test_mta_lines_are_unwrapped(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/mta/lines", {"lines": [{"lineNumber": 1}]})
        assert len(await client.get_mta_lines()) == 1

    async def test_ip_port_filters_merge_both_families(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json(
            "/network/ipportfilters",
            {"ipportfilters": {"ipv4": {"rules": [{"id": 1}]}, "ipv6": {"rules": [{"id": 2}]}}},
        )
        assert len(await client.get_ip_port_filters()) == 2

    async def test_mac_filters_and_port_triggers_come_back_raw(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/macfilters", {"macfilters": {"rules": [{"id": 1}]}})
        api.json("/network/porttriggers", {"porttriggers": {"rules": [{"id": 2}]}})
        assert await client.get_mac_filters() == [{"id": 1}]
        assert await client.get_port_triggers() == [{"id": 2}]

    async def test_upnp_and_smart_wifi_read_a_nested_flag(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/upnp", {"upnp": {"enable": "true"}})
        api.json("/wifi/smartmode", {"smartmode": {"enable": False}})
        assert await client.get_upnp() is True
        assert await client.get_smart_wifi() is False

    async def test_a_missing_flag_is_unknown_rather_than_false(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/upnp", {})
        assert await client.get_upnp() is None


class TestArgumentValidation:
    """Bad arguments fail before a request, not on the router."""

    @pytest.mark.parametrize("band", [BAND_2G, BAND_5G])
    async def test_a_known_band_is_accepted(
        self, api: FakeGateway, client: LibertyGatewayClient, band: str
    ) -> None:
        api.json(
            f"/wifi/{band}/config",
            {
                "config": {
                    "enable": True,
                    "ssid": {"ssid": "home", "securityType": "WPA2-PSK"},
                    "radio": {"channelNumber": 6, "channelWidth": "20MHz"},
                }
            },
        )
        config = await client.get_wifi_config(band)
        assert config.band == band
        assert config.ssid == "home"
        assert config.channel_number == 6

    async def test_an_unknown_band_is_refused_without_a_request(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        with pytest.raises(GatewayValidationError, match="band must be one of"):
            await client.get_wifi_config("band6g")
        assert api.paths("GET") == []

    @pytest.mark.parametrize("family", ["ipv4", "ipv6"])
    async def test_a_known_ip_family_is_accepted(
        self, api: FakeGateway, client: LibertyGatewayClient, family: str
    ) -> None:
        api.json(f"/network/{family}/firewall", {"firewall": {}})
        await client.get_firewall(family)

    async def test_an_unknown_ip_family_is_refused(
        self, client: LibertyGatewayClient
    ) -> None:
        with pytest.raises(GatewayValidationError, match="ipv4"):
            await client.get_firewall("ipv7")

    async def test_dhcp_validates_its_family_too(
        self, client: LibertyGatewayClient
    ) -> None:
        with pytest.raises(GatewayValidationError, match="ipv4"):
            await client.get_dhcp("ipv7")

    async def test_both_bands_are_fetched_together(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        for band in (BAND_2G, BAND_5G):
            api.json(f"/wifi/{band}/config", {"config": {"ssid": {"ssid": band}}})
            api.json(f"/wifi/{band}/state", {"state": {"status": "up"}})
            api.json(f"/wifi/{band}/guest/config", {"config": {"ssid": {"ssid": "guest"}}})
        assert set(await client.get_wifi_configs()) == {BAND_2G, BAND_5G}
        assert set(await client.get_wifi_states()) == {BAND_2G, BAND_5G}
        assert set(await client.get_guest_wifi_configs()) == {BAND_2G, BAND_5G}

    async def test_wps_reads_a_nested_flag(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json(f"/wifi/{BAND_2G}/wps/config", {"config": {"enable": "true"}})
        assert await client.get_wps_enabled(BAND_2G) is True


class TestWrites:
    """The two settings this library changes, and the reboot."""

    async def test_upnp_is_written_in_the_nested_shape(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/upnp", {}, method="PUT")
        await client.set_upnp(True)
        assert api.bodies[-1] == {"upnp": {"enable": True}}

    async def test_led_settings_are_read_before_they_are_written(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        # The PUT replaces both fields, so writing one without reading the
        # other resets it.
        api.json("/network/ledlight", {"value": {"brightness": 40, "automode": "true"}})
        api.json("/network/ledlight", {}, method="PUT")
        await client.set_led(brightness=80)
        assert api.bodies[-1] == {"brightness": "80", "automode": "true"}

    async def test_the_put_body_is_flat_while_the_get_is_wrapped(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/ledlight", {"value": {"brightness": 40, "automode": "false"}})
        api.json("/network/ledlight", {}, method="PUT")
        await client.set_led(automode=True)
        assert "value" not in api.bodies[-1]

    async def test_the_firmware_wants_strings_not_numbers(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/ledlight", {"value": {"brightness": 40, "automode": "false"}})
        api.json("/network/ledlight", {}, method="PUT")
        await client.set_led(brightness=50, automode=True)
        body = api.bodies[-1]
        assert body == {"brightness": "50", "automode": "true"}

    @pytest.mark.parametrize(("given", "written"), [(-10, "0"), (250, "100"), (55, "55")])
    async def test_the_brightness_is_clamped_to_the_allowed_range(
        self, api: FakeGateway, client: LibertyGatewayClient, given: int, written: str
    ) -> None:
        api.json("/network/ledlight", {"value": {"brightness": 40, "automode": "false"}})
        api.json("/network/ledlight", {}, method="PUT")
        await client.set_led(brightness=given)
        assert api.bodies[-1]["brightness"] == written

    async def test_a_reboot_is_posted(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/system/reboot", {}, method="POST")
        await client.reboot()
        assert "/rest/v1/system/reboot" in api.paths("POST")

    async def test_a_rejected_write_is_an_api_error(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/network/upnp", {"errorCode": 101}, status=400, method="PUT")
        with pytest.raises(GatewayAPIError) as caught:
            await client.set_upnp(True)
        assert caught.value.error_code == 101

    async def test_a_rejected_action_is_an_api_error(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.json("/system/reboot", {"errorCode": 7}, status=500, method="POST")
        with pytest.raises(GatewayAPIError) as caught:
            await client.reboot()
        assert caught.value.status_code == 500


class TestBooleanCoercion:
    """The firmware sends booleans as strings, numbers and actual booleans."""

    @pytest.mark.parametrize("value", ["true", "1", "yes", "on", "enabled", "TRUE", " True "])
    def test_the_truthy_strings(self, value: str) -> None:
        assert _as_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", "disabled", ""])
    def test_the_falsey_strings(self, value: str) -> None:
        assert _as_bool(value) is False

    def test_a_real_boolean_passes_through(self) -> None:
        assert _as_bool(True) is True
        assert _as_bool(False) is False

    def test_none_stays_unknown(self) -> None:
        # An absent setting is not a disabled setting.
        assert _as_bool(None) is None

    def test_a_number_is_coerced(self) -> None:
        assert _as_bool(1) is True
        assert _as_bool(0) is False


class TestEveryReadEndpoint:
    """One case per remaining read, so no endpoint ships unexercised.

    Each entry is (method name, API path, envelope, a check on the result).
    """

    CASES = [
        (
            "get_modem_mode",
            "/system/modemmode",
            {"modemmode": {"enable": False}},
            lambda r: r.raw["modemmode"]["enable"] is False,
        ),
        (
            "get_lan_info",
            "/network/ipv4/info",
            {"info": {"address": "192.168.178.1", "netmask": "255.255.255.0"}},
            lambda r: r.raw["info"]["address"] == "192.168.178.1",
        ),
        (
            "get_ipv6_info",
            "/network/ipv6/info",
            {"info": {"prefix": "2001:db8::/56"}},
            lambda r: r.raw["info"]["prefix"] == "2001:db8::/56",
        ),
        (
            "get_cable_modem_state",
            "/cablemodem/state",
            {"cablemodem": {"status": "OPERATIONAL", "upTime": 90000, "maxCPEs": "8"}},
            lambda r: r.operational and r.uptime == 90000 and r.max_cpes == 8,
        ),
        (
            "get_registration",
            "/cablemodem/registration",
            {"registration": {"registrationState": "complete"}},
            lambda r: r.raw["registration"]["registrationState"] == "complete",
        ),
        (
            "get_provisioning",
            "/system/gateway/provisioning",
            {
                "provisioning": {
                    "mode": "IPv4",
                    "macAddress": "aa:bb:cc:dd:ee:ff",
                    "ipv4": {"address": "203.0.113.5", "dnsServers": ["1.1.1.1"]},
                    "ipv6": {"globalAddress": "2001:db8::1"},
                }
            },
            lambda r: r.ipv4_address == "203.0.113.5" and r.ipv4_dns == ["1.1.1.1"],
        ),
        (
            "get_software_update",
            "/system/softwareupdate",
            {"softwareUpdate": {"status": "idle"}},
            lambda r: r.status == "idle",
        ),
        (
            "get_dmz",
            "/network/ipv4/dmz",
            {"dmz": {"enable": True, "internalHost": "192.168.178.50"}},
            lambda r: r.raw["dmz"]["internalHost"] == "192.168.178.50",
        ),
        (
            "get_led",
            "/network/ledlight",
            {"value": {"brightness": "60", "automode": "false"}},
            lambda r: r.brightness == 60 and r.automode is False,
        ),
    ]

    @pytest.mark.parametrize(
        ("method", "path", "envelope", "check"),
        CASES,
        ids=[case[0] for case in CASES],
    )
    async def test_the_endpoint_parses(
        self,
        api: FakeGateway,
        client: LibertyGatewayClient,
        method: str,
        path: str,
        envelope: dict,
        check,
    ) -> None:
        api.json(path, envelope)
        assert check(await getattr(client, method)()) is True

    @pytest.mark.parametrize("family", ["ipv4", "ipv6"])
    async def test_dhcp_reads_either_family(
        self, api: FakeGateway, client: LibertyGatewayClient, family: str
    ) -> None:
        api.json(f"/network/{family}/dhcp", {"dhcp": {"enable": True}})
        assert (await client.get_dhcp(family)).raw["dhcp"]["enable"] is True

    async def test_the_lockout_status_is_reachable_from_the_client(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.allow_login(failures=2, lockout=0)
        assert await client.get_lockout() == (2, 0)

    async def test_logout_is_reachable_from_the_client(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        await client.login()
        assert await client.logout() is True

    async def test_the_auth_manager_is_reachable_from_the_client(
        self, client: LibertyGatewayClient
    ) -> None:
        assert client.auth is not None

    async def test_a_non_json_success_body_parses_as_nothing(
        self, api: FakeGateway, client: LibertyGatewayClient
    ) -> None:
        api.text("/system/modemmode", "not json")
        assert (await client.get_modem_mode()).raw == {}
