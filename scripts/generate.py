#!/usr/bin/env python3

import ipaddress
import json
import urllib.request
from pathlib import Path

DERP_MAP_URL = "https://login.tailscale.com/derpmap/default"
OUTPUT = Path(__file__).resolve().parent.parent / "tailscale-derp.list"


def fetch_derp_map():
    req = urllib.request.Request(
        DERP_MAP_URL,
        headers={
            "User-Agent": "tailscale-surge-rules/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    data = fetch_derp_map()

    # 兼容可能的字段大小写变化
    regions = data.get("Regions") or data.get("regions") or {}

    if isinstance(regions, dict):
        regions = regions.values()

    ipv4_addresses = set()
    ipv6_addresses = set()

    for region in regions:
        nodes = region.get("Nodes") or region.get("nodes") or []

        for node in nodes:
            ipv4 = node.get("IPv4") or node.get("ipv4")
            ipv6 = node.get("IPv6") or node.get("ipv6")

            if ipv4:
                try:
                    address = ipaddress.ip_address(ipv4)
                    if address.version == 4:
                        ipv4_addresses.add(address)
                except ValueError:
                    pass

            if ipv6:
                try:
                    address = ipaddress.ip_address(ipv6)
                    if address.version == 6:
                        ipv6_addresses.add(address)
                except ValueError:
                    pass

    if not ipv4_addresses and not ipv6_addresses:
        raise RuntimeError(
            "No DERP IP addresses found. "
            "The Tailscale DERP map format may have changed."
        )

    lines = [
        "# Tailscale DERP IP addresses for Surge",
        "# Source: https://login.tailscale.com/derpmap/default",
        "# Automatically generated. Do not edit manually.",
        "",
    ]

    lines.append("# IPv4")
    for address in sorted(ipv4_addresses):
        lines.append(f"IP-CIDR,{address}/32")

    lines.append("")
    lines.append("# IPv6")
    for address in sorted(ipv6_addresses):
        lines.append(f"IP-CIDR6,{address}/128")

    lines.append("")

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")

    print(
        f"Generated {len(ipv4_addresses)} IPv4 and "
        f"{len(ipv6_addresses)} IPv6 DERP addresses."
    )


if __name__ == "__main__":
    main()
