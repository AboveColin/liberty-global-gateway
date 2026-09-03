"""Tests for the typed models and the compatibility aliases.

The identification helpers get the most attention: they are what a discovery
flow shows a user before asking for a password, and they have to degrade
without turning a partly-known gateway into a blank name.
"""

from __future__ import annotations

import pytest

from liberty_global_gateway import (
    CompalAPIError,
    CompalAuthError,
    CompalClient,
    CompalError,
    CompalLockoutError,
    CompalNetworkError,
    CompalSessionBusyError,
    CompalValidationError,
    GatewayAPIError,
    GatewayAuthError,
    GatewayError,
    GatewayLockoutError,
    GatewayNetworkError,
    GatewaySessionBusyError,
    GatewayValidationError,
    LibertyGatewayClient,
    Led,
    Localization,
)
from liberty_global_gateway.constants import KNOWN_MODELS, KNOWN_SKINS


def localization(**fields: object) -> Localization:
    """A Localization built from a router-shaped payload."""
    return Localization.from_api({"localization": fields})


class TestBrand:
    """The operator name shown to a user."""

    def test_a_known_skin_becomes_its_brand(self) -> None:
        assert localization(skin="ziggo").brand == "Ziggo"

    def test_every_shipped_skin_maps_to_a_name(self) -> None:
        for skin in KNOWN_SKINS:
            assert localization(skin=skin).brand == KNOWN_SKINS[skin]

    def test_an_unknown_skin_is_title_cased_rather_than_dropped(self) -> None:
        # A new operator should still show something readable.
        assert localization(skin="new_operator").brand == "New Operator"

    def test_no_skin_means_no_brand(self) -> None:
        assert localization().brand is None


class TestGeneration:
    """The hardware generation the firmware itself buckets a model into."""

    def test_a_known_model_maps_to_its_generation(self) -> None:
        assert localization(modelName="F3896LG").generation == "mv2+"

    def test_every_shipped_model_maps_to_a_generation(self) -> None:
        for model, generation in KNOWN_MODELS.items():
            assert localization(modelName=model).generation == generation

    def test_the_model_lookup_ignores_case(self) -> None:
        assert localization(modelName="f3896lg").generation == "mv2+"

    def test_an_unknown_model_has_no_generation(self) -> None:
        assert localization(modelName="XX9999").generation is None

    def test_no_model_means_no_generation(self) -> None:
        assert localization().generation is None


class TestDisplayName:
    """The label a discovery flow puts in front of a user."""

    def test_all_three_fields_produce_the_full_name(self) -> None:
        result = localization(skin="ziggo", productName="SmartWifi modem", modelName="F3896LG")
        assert result.display_name == "Ziggo SmartWifi modem (F3896LG)"

    def test_a_missing_product_name_still_reads_well(self) -> None:
        assert localization(skin="ziggo", modelName="F3896LG").display_name == "Ziggo (F3896LG)"

    def test_a_model_alone_still_reads_well(self) -> None:
        assert localization(modelName="F3896LG").display_name == (
            "Liberty Global Cable Gateway (F3896LG)"
        )

    def test_nothing_at_all_still_produces_a_name(self) -> None:
        # A blank name in a discovery list helps nobody.
        assert localization().display_name == "Liberty Global Cable Gateway"

    def test_the_raw_payload_is_kept(self) -> None:
        payload = {"localization": {"skin": "ziggo", "somethingNew": 1}}
        assert Localization.from_api(payload).raw == payload

    def test_an_empty_payload_does_not_raise(self) -> None:
        assert Localization.from_api({}).model_name is None


class TestLed:
    """LED settings, which the router reports as strings under "value"."""

    def test_reads_the_wrapped_values(self) -> None:
        led = Led.from_api({"value": {"brightness": "40", "automode": "true"}})
        assert led.brightness == 40
        assert led.automode is True

    def test_an_empty_payload_does_not_raise(self) -> None:
        led = Led.from_api({})
        assert led.brightness is None
        assert led.automode is None


class TestCompatibilityAliases:
    """The package was released as compalf3896lg; the old names are a promise."""

    def test_the_client_alias_is_the_same_class(self) -> None:
        assert CompalClient is LibertyGatewayClient

    @pytest.mark.parametrize(
        ("old", "new"),
        [
            (CompalError, GatewayError),
            (CompalAPIError, GatewayAPIError),
            (CompalAuthError, GatewayAuthError),
            (CompalLockoutError, GatewayLockoutError),
            (CompalSessionBusyError, GatewaySessionBusyError),
            (CompalNetworkError, GatewayNetworkError),
            (CompalValidationError, GatewayValidationError),
        ],
    )
    def test_each_exception_alias_is_the_same_class(self, old: type, new: type) -> None:
        assert old is new

    def test_catching_the_old_base_still_catches_a_new_error(self) -> None:
        with pytest.raises(CompalError):
            raise GatewayAPIError("boom")


class TestExceptionHierarchy:
    """The hierarchy is what lets a caller tell the router's quirks apart."""

    def test_a_lockout_is_a_kind_of_auth_error(self) -> None:
        assert issubclass(GatewayLockoutError, GatewayAuthError)

    def test_a_busy_slot_is_not_an_auth_error(self) -> None:
        # Prompting for a new password because the web UI is open would be
        # the wrong thing to do to a user.
        assert not issubclass(GatewaySessionBusyError, GatewayAuthError)

    def test_every_error_shares_one_base(self) -> None:
        for error in (
            GatewayAPIError,
            GatewayAuthError,
            GatewayLockoutError,
            GatewaySessionBusyError,
            GatewayNetworkError,
            GatewayValidationError,
        ):
            assert issubclass(error, GatewayError)

    def test_the_api_error_renders_what_it_knows(self) -> None:
        assert str(GatewayAPIError("no")) == "no"
        assert "HTTP 400" in str(GatewayAPIError("no", status_code=400))
        assert "errorCode 7" in str(GatewayAPIError("no", error_code=7))
        both = str(GatewayAPIError("no", status_code=400, error_code=7))
        assert "HTTP 400" in both and "errorCode 7" in both

    def test_a_lockout_carries_the_remaining_seconds(self) -> None:
        assert GatewayLockoutError("locked", lockout_time=90).lockout_time == 90


class TestDerivedValues:
    """Properties a dashboard reads directly."""

    def test_a_service_flow_rate_converts_to_megabits(self) -> None:
        from liberty_global_gateway import ServiceFlow

        flow = ServiceFlow.from_api({"serviceFlow": {"maxTrafficRate": 1_000_000_000}})
        assert flow.max_traffic_rate_mbps == 1000.0

    def test_a_flow_without_a_rate_has_no_megabits(self) -> None:
        from liberty_global_gateway import ServiceFlow

        assert ServiceFlow.from_api({}).max_traffic_rate_mbps is None

    def test_a_flow_entry_is_also_read_unwrapped(self) -> None:
        from liberty_global_gateway import ServiceFlow

        assert ServiceFlow.from_api({"serviceFlowId": 7}).service_flow_id == 7

    def test_a_radio_reports_itself_up(self) -> None:
        from liberty_global_gateway import WifiState

        assert WifiState.from_api("band2g", {"state": {"status": "UP"}}).up is True
        assert WifiState.from_api("band2g", {"state": {"status": "down"}}).up is False
        assert WifiState.from_api("band2g", {}).up is False

    def test_a_modem_reports_itself_operational(self) -> None:
        from liberty_global_gateway import CableModemState

        assert CableModemState.from_api({"cablemodem": {"status": "OPERATIONAL"}}).operational
        assert not CableModemState.from_api({}).operational


class TestHostName:
    """What a device is called in the hosts table."""

    def test_an_explicit_device_name_wins(self) -> None:
        from liberty_global_gateway import Host

        host = Host.from_api(
            {"macAddress": "aa", "config": {"deviceName": "nix1", "hostname": "localhost"}}
        )
        assert host.name == "nix1"

    def test_the_hostname_is_the_fallback(self) -> None:
        from liberty_global_gateway import Host

        payload = {"macAddress": "aa", "config": {"hostname": "nix1"}}
        assert Host.from_api(payload).name == "nix1"

    def test_the_mac_is_the_last_resort(self) -> None:
        from liberty_global_gateway import Host

        assert Host.from_api({"macAddress": "aa:bb"}).name == "aa:bb"

    def test_a_nameless_host_has_no_name(self) -> None:
        from liberty_global_gateway import Host

        assert Host.from_api({}).name is None


class TestFirewall:
    """The firmware reports this two different ways."""

    def test_an_explicit_flag_is_used(self) -> None:
        from liberty_global_gateway import Firewall

        assert Firewall.from_api({"firewall": {"enable": True}}).enabled is True

    def test_a_security_level_stands_in_for_the_flag(self) -> None:
        from liberty_global_gateway import Firewall

        assert Firewall.from_api({"firewall": {"securityLevel": "high"}}).enabled is True

    def test_a_security_level_of_off_means_disabled(self) -> None:
        from liberty_global_gateway import Firewall

        for level in ("off", "Disabled", "NONE"):
            assert Firewall.from_api({"firewall": {"securityLevel": level}}).enabled is False

    def test_neither_field_leaves_it_unknown(self) -> None:
        from liberty_global_gateway import Firewall

        assert Firewall.from_api({}).enabled is None
