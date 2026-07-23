![PyPI - Downloads](https://img.shields.io/pypi/dm/compalf3896lg)
![PyPI - Downloads](https://img.shields.io/pypi/dd/compalf3896lg)

# Unofficial Compal F3896LG API Client

_Disclaimer: this is an unofficial Python client for the Compal F3896LG cable gateway's local admin API. It is not affiliated with, endorsed by, or in any way connected to Compal, Liberty Global, Ziggo, or VodafoneZiggo. Use it on your own gateway, at your own risk._

## Introduction

The **Compal F3896LG** is the DOCSIS 3.1 cable gateway that Liberty Global / Ziggo ship to customers in the Netherlands (it also appears elsewhere in the Liberty Global footprint). Its web UI is a single-page app that talks to a small REST API under `https://<router>/rest/v1`.

This library is an asynchronous Python wrapper around that API. It reads system/firmware info, DOCSIS downstream/upstream channels, cable-modem registration state, provisioned service flows (your plan's rate caps), Wi-Fi configuration/state and the connected-hosts table — and can reboot the gateway. Every response is parsed into a documented dataclass, with the raw payload kept on `.raw`.

## Features

- **Single-session handling:** the F3896LG allows exactly one authenticated session and has **no logout endpoint**. The client logs in, reads in a burst, and drops the token; the router frees the slot once the token idles out. A login attempt while another session is active raises `CompalSessionBusyError` instead of failing confusingly.
- **Lockout-aware login:** the password endpoint locks out after a handful of contiguous wrong attempts. Before each login the client reads the unauthenticated login status and refuses to try while a lockout is active, so it never makes things worse.
- **DOCSIS diagnostics:** downstream power/SNR/modulation/error counters per channel, upstream power/modulation, and provisioned service-flow rates.
- **Connected devices:** the DHCP/association table with hostname, IP, interface, Wi-Fi band and RSSI — handy for presence detection.
- **Typed models:** every response becomes a dataclass; the Wi-Fi PSK is deliberately kept out of the modelled fields (it stays in `.raw`) so it isn't surfaced by accident.

## Installation

Requires Python 3.11 or newer.

```bash
pip install compalf3896lg
```

Or from a checkout:

```bash
pip install -r requirements.txt
```

## Authentication

The gateway uses a **password-only** login (no username): `POST /rest/v1/user/login` with `{"password": "..."}` returns a bearer token that is valid for a single session. The admin certificate is self-signed, so TLS verification is off by default.

> **One session at a time.** Close the router's web UI before using this library, or expect a `CompalSessionBusyError`. There is no logout call — the router releases the session on its own roughly 15 minutes after the last request.

## Usage

The client manages its own `aiohttp` session (pass your own via `session=` if you prefer) and works as an async context manager.

```python
import asyncio
from compalf3896lg import CompalClient

async def main():
    async with CompalClient("192.168.178.1", "your-admin-password") as client:
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

### Checking lockout state without logging in

```python
async with CompalClient("192.168.178.1", "your-admin-password") as client:
    failures, lockout_seconds = await client.get_lockout()
    print(f"{failures} contiguous failures, locked out for {lockout_seconds}s")
```

### Rebooting

```python
async with CompalClient("192.168.178.1", "your-admin-password") as client:
    await client.login()
    await client.reboot()   # drops the WAN for a minute or two — deliberate action
```

## Example

`examples/quickstart.py` prints a status summary using `COMPAL_HOST` / `COMPAL_PASSWORD` from the environment:

```bash
COMPAL_HOST=192.168.178.1 COMPAL_PASSWORD='your-admin-password' python examples/quickstart.py
```

## Home Assistant

A companion Home Assistant integration built on this library lives at [HA-Compal-F3896LG](https://github.com/AboveColin/HA-Compal-F3896LG) — install it via HACS to get DOCSIS signal, connected-device and gateway-status sensors, plus a reboot button.

## Notes

- **TLS:** the admin cert is self-signed; verification is off by default. Pass `verify_ssl=True` if you have installed the cert.
- **`/network/ipv4/info`** returns the **LAN** address/subnet, not the WAN IP — the stock firmware does not expose the public WAN address over this API.
- **Errors:** the package raises `CompalAuthError` (wrong password), `CompalLockoutError` (login locked out), `CompalSessionBusyError` (another session active), `CompalAPIError` (bad response, carries `status_code`/`error_code`), `CompalNetworkError` (timeout/connection/TLS) and `CompalValidationError` (bad arguments) — all subclasses of `CompalError`.

## License

MIT — see [LICENSE](LICENSE).
