"""
Liberty Global cable gateway quickstart.

Reads the router host and admin password from the environment and prints a
short status summary. The F3896LG allows only one session at a time, so close
any open router web-UI tab before running this.

    GATEWAY_HOST=192.168.178.1 GATEWAY_PASSWORD='your-admin-password' \
        python examples/quickstart.py
"""

import asyncio
import os

from liberty_global_gateway import LibertyGatewayClient, GatewaySessionBusyError

HOST = os.environ.get("GATEWAY_HOST", "192.168.178.1")
PASSWORD = os.environ.get("GATEWAY_PASSWORD", "")


async def main() -> None:
    if not PASSWORD:
        raise SystemExit("set GATEWAY_PASSWORD (the router admin password)")

    async with LibertyGatewayClient(HOST, PASSWORD) as client:
        try:
            await client.login()
        except GatewaySessionBusyError:
            raise SystemExit(
                "the router already has an active session — close its web UI and retry"
            )

        info = await client.get_system_info()
        print(f"Model:    {info.model_name}")
        print(f"Firmware: {info.software_version}")

        state = await client.get_cable_modem_state()
        print(f"\nDOCSIS {state.docsis_version} — {state.status} ({state.service_status})")
        print(f"Uptime:   {state.uptime} s")

        flows = await client.get_service_flows()
        for flow in flows:
            print(f"  {flow.direction:<10} {flow.max_traffic_rate_mbps} Mbps ({flow.schedule_type})")

        downstream = await client.get_downstream_channels()
        upstream = await client.get_upstream_channels()
        print(f"\nChannels: {len(downstream)} downstream, {len(upstream)} upstream")
        if downstream:
            powers = [c.power for c in downstream if c.power is not None]
            snrs = [c.snr for c in downstream if c.snr is not None]
            if powers:
                print(f"  downstream power {min(powers)}..{max(powers)} dBmV")
            if snrs:
                print(f"  downstream SNR   {min(snrs)}..{max(snrs)} dB")

        hosts = await client.get_hosts()
        print(f"\nConnected devices: {len(hosts)}")
        for host in hosts[:10]:
            print(f"  {host.ip_address:<15} {host.name} ({host.interface})")


if __name__ == "__main__":
    asyncio.run(main())
