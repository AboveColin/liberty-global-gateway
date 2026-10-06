![PyPI - Downloads](https://img.shields.io/pypi/dm/liberty-global-gateway)
![PyPI - Downloads](https://img.shields.io/pypi/dd/liberty-global-gateway)

# liberty-global-gateway — unofficial API client for Liberty Global cable gateways

_Disclaimer: this is an unofficial Python client for the local admin API of Liberty Global's cable gateways. It is not affiliated with, endorsed by, or in any way connected to Liberty Global, Ziggo, VodafoneZiggo, UPC, Virgin Media, Sunrise, Unitymedia, Sagemcom or Compal. Use it on your own gateway, at your own risk._

> Previously released as **`compalf3896lg`**. The package and its exception names were renamed in 2.0.0 because the same API turned out to cover a whole family of models and operator brands. The old `Compal*` names still work as aliases — see [Migrating from `compalf3896lg`](#migrating-from-compalf3896lg).

## Introduction

Liberty Global and its sister operators ship a family of DOCSIS 3.0/3.1 cable gateways that all run the same **LG-RDK** firmware and expose the same REST API under `https://<gateway>/rest/v1`. Depending on where you live, the same box is sold as the **Ziggo SmartWifi modem**, the **UPC Connect Box**, a **Virgin Media Hub**, or the Sunrise / Yallo / Unitymedia equivalent.

This library is an asynchronous Python wrapper around that API. It reads system/firmware info, DOCSIS downstream/upstream channels, cable-modem registration state, provisioned service flows (your plan's rate caps), Wi-Fi configuration/state, firewall/DMZ/port-forwarding and the connected-hosts table; it can toggle UPnP and the status LEDs, and reboot the gateway. Every response is parsed into a documented dataclass, with the raw payload kept on `.raw`.

## Supported hardware

The firmware's own web UI gates its feature set on the model name. Those model IDs, and the operator skins it ships, are what this table is built from:

| Model | ODM | Generation | Typically sold as |
|---|---|---|---|
| `F3896LG` | Sagemcom | mv2+ | Ziggo SmartWifi modem (NL) |
| `F3897LG` | Sagemcom | mv2+ | Ziggo / Liberty Global |
| `F5685LGB` | Sagemcom | mv3 | Liberty Global (DOCSIS 3.1, Wi-Fi 6) |
| `F5685LGE` | Sagemcom | mv3 | Liberty Global (DOCSIS 3.1, Wi-Fi 6) |
| `CH7465LG` | Compal | mv1 | UPC / Unitymedia Connect Box |

Operator skins the firmware knows about: `ziggo`, `upc`, `virgin_media`, `unitymedia`, `sunrise`, `yallo`, `munro`, `lumina`, `grandslam`.

> **Verification status:** only the **Sagemcom F3896LG** (Ziggo, firmware `LG-RDK_12.13.16`) has been tested against real hardware. The other models share the firmware and the API surface, so they are expected to work, but they are unverified — reports welcome. Endpoints a given model lacks raise `GatewayAPIError` rather than breaking the client.

`liberty_global_gateway.KNOWN_MODELS` and `KNOWN_SKINS` expose the same data programmatically.

## Features

- **Credential-free identification:** `probe()` asks the gateway who it is over an unauthenticated endpoint — operator brand, product name and model — which is what makes zero-configuration discovery possible.
- **Single-session handling:** the gateway allows exactly one authenticated session. Call `await client.logout()` when done — it sends the gateway's logout (`DELETE /user/<id>/token/<token>`) and frees the slot **immediately**, so the web UI and other clients can log straight back in. `client.close()` logs out for you. A login attempt while another session is active raises `GatewaySessionBusyError` instead of failing confusingly; if a client exits without logging out, the router still releases the slot on its own after ~15 minutes.
- **Lockout-aware login:** the password endpoint locks out after a handful of contiguous wrong attempts. Before each login the client reads the unauthenticated login status and refuses to try while a lockout is active, so it never makes things worse.
- **DOCSIS diagnostics:** downstream power/SNR/modulation/error counters per channel, upstream power/modulation, provisioned service-flow rates, T3/T4 timeouts, the cable-modem **event log** and DOCSIS **registration** state.
- **WAN / provisioning:** the public IPv4/IPv6 address, gateway, DNS servers and lease times (`get_provisioning`), plus firmware **software-update** status.
- **Network features:** UPnP, DMZ, IPv4/IPv6 firewall, port-forwarding rules, static DHCP reservations, guest Wi-Fi (SSID only — never the PSK), Smart Wi-Fi/band-steering and telephony (MTA) line status.
- **Controls:** toggle UPnP, switch the status LEDs to automatic brightness, set LED brightness, reboot.
- **Connected devices:** the DHCP/association table with hostname, IP, interface, Wi-Fi band and RSSI — handy for presence detection.
- **Typed models:** every response becomes a dataclass; the Wi-Fi PSK is deliberately kept out of the modelled fields (it stays in `.raw`) so it isn't surfaced by accident.

## Installation

Requires Python 3.11 or newer.

```bash
pip install liberty-global-gateway
```

Or from a checkout:

```bash
pip install -r requirements.txt
```

## Authentication

The gateway uses a **password-only** login (no username): `POST /rest/v1/user/login` with `{"password": "..."}` returns a bearer token that is valid for a single session. The admin certificate is self-signed, so TLS verification is off by default.

> **One session at a time.** Close the router's web UI before using this library, or expect a `GatewaySessionBusyError`. Call `await client.logout()` (or `client.close()`) when finished to free the slot right away; otherwise the router releases the session on its own roughly 15 minutes after the last request.

The default address differs per operator: Ziggo hands out `192.168.178.1`, UPC / Virgin Media builds typically use `192.168.0.1`. Prefer your machine's actual default gateway over either.

## Usage

The client manages its own `aiohttp` session (pass your own via `session=` if you prefer) and works as an async context manager.

```python
import asyncio
from liberty_global_gateway import LibertyGatewayClient

async def main():
    async with LibertyGatewayClient("192.168.178.1", "your-admin-password") as client:
        await client.login()

        info = await client.get_system_info()
        print(info.model_name, info.software_version)

        state = await client.get_cable_modem_state()
        print(f"DOCSIS {state.docsis_version}: {state.status}, uptime {state.uptime}s")

        for flow in await client.get_service_flows():
            print(flow.direction, flow.max_traffic_rate_mbps, "Mbps")

        for ch in await client.get_downstream_channels():
            print(ch.channel_id, ch.power, "dBmV", ch.snr, "dB", ch.modulation)

        for host in await client.get_hosts():
            print(host.ip_address, host.name, host.interface)

asyncio.run(main())
```

### Identifying a gateway without credentials

`probe()` needs no password at all. It returns a `Localization` (or `None` if the host is not one of these gateways), which is enough to confirm a candidate address and label it correctly:

```python
from liberty_global_gateway import probe

localization = await probe("192.168.178.1")
if localization:
    print(localization.display_name)  # "Ziggo SmartWifi modem (F3896LG)"
    print(localization.brand)         # "Ziggo"
    print(localization.generation)    # "mv2+"
```

### Checking lockout state without logging in

```python
async with LibertyGatewayClient("192.168.178.1", "your-admin-password") as client:
    failures, lockout_seconds = await client.get_lockout()
    print(f"{failures} contiguous failures, locked out for {lockout_seconds}s")
```

### Rebooting

```python
async with LibertyGatewayClient("192.168.178.1", "your-admin-password") as client:
    await client.login()
    await client.reboot()   # drops the WAN for a minute or two — deliberate action
```

## Example

`examples/quickstart.py` prints a status summary using `GATEWAY_HOST` / `GATEWAY_PASSWORD` from the environment:

```bash
GATEWAY_HOST=192.168.178.1 GATEWAY_PASSWORD='your-admin-password' python examples/quickstart.py
```

## Home Assistant

A companion Home Assistant integration built on this library lives at [HA-Liberty-Global-Gateway](https://github.com/AboveColin/HA-Liberty-Global-Gateway) — install it via HACS to get DOCSIS signal, connected-device and gateway-status sensors, UPnP/LED controls and a reboot button, with SSDP auto-discovery on the network.

## Migrating from `compalf3896lg`

```python
# 1.x
from compalf3896lg import CompalClient, CompalAuthError

# 2.x
from liberty_global_gateway import LibertyGatewayClient, GatewayAuthError
```

The old names are re-exported as aliases (`CompalClient`, `CompalError`, `CompalAuthError`, `CompalLockoutError`, `CompalSessionBusyError`, `CompalAPIError`, `CompalNetworkError`, `CompalValidationError`), so existing code keeps working after changing the import package. Method names and model fields are unchanged.

## Notes

- **TLS:** the admin cert is self-signed; verification is off by default. Pass `verify_ssl=True` if you have installed the cert.
- **`/network/ipv4/info`** returns the **LAN** address/subnet; for the public WAN address use `get_provisioning()` (`/system/gateway/provisioning`).
- **Errors:** the package raises `GatewayAuthError` (wrong password), `GatewayLockoutError` (login locked out), `GatewaySessionBusyError` (another session active), `GatewayAPIError` (bad response, carries `status_code`/`error_code`), `GatewayNetworkError` (timeout/connection/TLS) and `GatewayValidationError` (bad arguments) — all subclasses of `GatewayError`.

## Supporting the project

This project is free and stays free. If it is useful to you, you can support its
development through [GitHub Sponsors](https://github.com/sponsors/AboveColin).
Sponsorship is voluntary and unlocks nothing: every feature, fix and security
update ships in the public release.

## License

MIT — see [LICENSE](LICENSE).
