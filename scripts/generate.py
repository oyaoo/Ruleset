#!/usr/bin/env python3

import ipaddress
import json
import urllib.request
from pathlib import Path


DERP_MAP_URL = "https://controlplane.tailscale.com/derpmap/default"

ROOT = Path(__file__).resolve().parent.parent

DOMAIN_OUTPUT = ROOT / "tailscale-derp-domain.list"
IP_OUTPUT = ROOT / "tailscale-derp-ip.list"


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


def ip_sort_key(addr):
    ip = ipaddress.ip_address(addr)
    return ip.version, int(ip)


def main():
    data = fetch_derp_map()

    regions = data.get("Regions", {})

    domains = set()
    ipv4_addresses = set()
    ipv6_addresses = set()

    for region in regions.values():
        for node in region.get("Nodes", []):
            hostname = node.get("HostName")
            ipv4 = node.get("IPv4")
            ipv6 = node.get("IPv6")

            # DERP hostname
            if hostname:
                hostname = hostname.strip().lower().rstrip(".")
                domains.add(hostname)

            # IPv4
            if ipv4:
                try:
                    ip = ipaddress.ip_address(ipv4)
                    if ip.version == 4:
                        ipv4_addresses.add(str(ip))
                except ValueError:
                    pass

            # IPv6
            if ipv6:
                try:
                    ip = ipaddress.ip_address(ipv6)
                    if ip.version == 6:
                        ipv6_addresses.add(str(ip))
                except ValueError:
                    pass

    if not domains:
        raise RuntimeError("No DERP domains found")

    if not ipv4_addresses and not ipv6_addresses:
        raise RuntimeError("No DERP IP addresses found")

    # -------------------------------------------------
    # Surge DOMAIN-SET
    # -------------------------------------------------

    domain_lines = [
        "# Tailscale DERP domains",
        "# Source: https://controlplane.tailscale.com/derpmap/default",
        "# Automatically generated. Do not edit manually.",
        "",
    ]

    domain_lines.extend(sorted(domains))
    domain_lines.append("")

    DOMAIN_OUTPUT.write_text(
        "\n".join(domain_lines),
        encoding="utf-8",
    )

    # -------------------------------------------------
    # Surge RULE-SET for IP addresses
    # -------------------------------------------------

    ip_lines = [
        "# Tailscale DERP IP addresses",
        "# Source: https://controlplane.tailscale.com/derpmap/default",
        "# Automatically generated. Do not edit manually.",
        "",
        "# IPv4",
    ]

    for ip in sorted(ipv4_addresses, key=ip_sort_key):
        ip_lines.append(f"IP-CIDR,{ip}/32")

    ip_lines.extend([
        "",
        "# IPv6",
    ])

    for ip in sorted(ipv6_addresses, key=ip_sort_key):
        ip_lines.append(f"IP-CIDR6,{ip}/128")

    ip_lines.append("")

    IP_OUTPUT.write_text(
        "\n".join(ip_lines),
        encoding="utf-8",
    )

    print(
        f"Generated:\n"
        f"  Domains: {len(domains)}\n"
        f"  IPv4:    {len(ipv4_addresses)}\n"
        f"  IPv6:    {len(ipv6_addresses)}"
    )


if __name__ == "__main__":
    main()
