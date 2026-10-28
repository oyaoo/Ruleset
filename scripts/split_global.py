#!/usr/bin/env python3
"""Split Surge and Clash Global rules independently into four regions plus remainder.

Only DOMAIN and DOMAIN-SUFFIX rules can be classified by country-code TLD.
Everything else remains in Global_Remaining, so no source rule is lost.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import yaml

SOURCE_URLS = {
    "Surge": (
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/"
        "master/rule/Surge/Global/Global_All_No_Resolve.list"
    ),
    "Clash": (
        "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/"
        "master/rule/Clash/Global/Global_Classical_No_Resolve.yaml"
    ),
}

# Country-code TLD classification (not the physical location of a website).
# Americas includes North, Central and South America, plus the Caribbean.
# Europe includes the 27 EU member-country codes, .eu, UK, Switzerland and Norway.
# Southeast Asia includes Timor-Leste. Territories with their own ccTLDs are
# grouped geographically for the Americas; nonlisted ccTLDs go to remainder.
REGION_CODES = {
    "Japan": set("JP".split()),
    "Americas": set("""
        AG AR AW BB BL BM BO BQ BR BS BZ CA CL CO CR CU CW
        DM DO EC FK GD GF GL GP GT GY HN HT JM KN KY LC MF
        MQ MS MX NI PA PE PM PR PY SR SV SX TC TT US UY VC VE VG VI
    """.split()),
    "SoutheastAsia": set("BN ID KH LA MM MY PH SG TH TL VN".split()),
    "Europe": set("""
        AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV
        MT NL PL PT RO SE SI SK EU GB CH NO
    """.split()),
}

# The project's five output files per format, always emitted in this order.
REGION_ORDER = ("Japan", "Americas", "SoutheastAsia", "Europe")
REMAINDER_NAME = "Global_Remaining"

# .uk is the standard UK ccTLD; .gb also maps to the Europe category.
TLD_ALIASES = {"uk": "GB"}


def validate_regions() -> None:
    owners: dict[str, str] = {}
    for region, codes in REGION_CODES.items():
        for code in codes:
            if code in owners:
                raise ValueError(f"Overlapping region code: {code} ({owners[code]}, {region})")
            owners[code] = region


validate_regions()
CODE_TO_REGION = {
    code: name for name, codes in REGION_CODES.items() for code in codes
}


def region_of_rule(rule: str) -> str | None:
    """Map DOMAIN and DOMAIN-SUFFIX rules by their last domain label only."""
    parts = rule.split(",", 2)
    if len(parts) < 2 or parts[0].strip().upper() not in {"DOMAIN", "DOMAIN-SUFFIX"}:
        return None

    domain = parts[1].strip().lower().rstrip(".")
    if not domain or any(ch in domain for ch in ("*", "/", " ")):
        return None

    tld = domain.rsplit(".", 1)[-1]
    country = TLD_ALIASES.get(tld, tld.upper())
    return CODE_TO_REGION.get(country)


def read_surge(path: Path) -> list[str]:
    return [
        row.strip()
        for row in path.read_text(encoding="utf-8-sig").splitlines()
        if row.strip() and not row.lstrip().startswith("#")
    ]


def read_clash(path: Path) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("payload"), list):
        raise ValueError(f"Expected Clash Classical payload list: {path}")
    if any(not isinstance(rule, str) for rule in data["payload"]):
        raise ValueError(f"Non-string rule in Clash payload: {path}")
    return [rule.strip() for rule in data["payload"] if rule.strip()]


def split_rules(rules: list[str]) -> tuple[dict[str, list[str]], int]:
    if not rules:
        raise ValueError("Empty upstream rule set: refusing to replace outputs")

    result = {name: [] for name in (*REGION_ORDER, REMAINDER_NAME)}
    seen: set[str] = set()
    duplicates = 0
    for rule in rules:
        if rule in seen:
            duplicates += 1
            continue
        seen.add(rule)
        category = region_of_rule(rule) or REMAINDER_NAME
        result[category].append(rule)

    if sum(len(chunk) for chunk in result.values()) != len(seen):
        raise AssertionError("Rule count mismatch: source rules were lost")
    return result, duplicates


def file_content(format_name: str, category: str, rules: list[str]) -> str:
    header = (
        f"# Generated from blackmatrix7/ios_rule_script ({format_name})\n"
        f"# Category: {category} | Rules: {len(rules)}\n"
        f"# Source: {SOURCE_URLS[format_name]}\n"
        "# Classification: country-code domain TLD only; not geo-IP.\n"
    )
    if format_name == "Surge":
        return header + "\n".join(rules) + "\n"

    # YAML classical providers must keep a valid empty list if a region has no rules.
    if not rules:
        return header + "payload: []\n"

    # YAML single-quoted scalar: escape apostrophes, preserving rule contents.
    payload = ("  - '" + rule.replace("'", "''") + "'" for rule in rules)
    return header + "payload:\n" + "\n".join(payload) + "\n"


def generate(source: Path, destination: Path, format_name: str) -> dict[str, int]:
    if format_name not in SOURCE_URLS:
        raise ValueError(f"Unknown output format: {format_name}")
    rules = read_surge(source) if format_name == "Surge" else read_clash(source)
    groups, duplicates = split_rules(rules)
    extension = ".list" if format_name == "Surge" else ".yaml"
    destination.mkdir(parents=True, exist_ok=True)

    # Prepare all file contents before deleting obsolete country files.
    files = {
        f"{category}{extension}": file_content(format_name, category, groups[category])
        for category in (*REGION_ORDER, REMAINDER_NAME)
    }
    # Prune old 223 country-code outputs from the preceding version.
    for existing in destination.glob(f"*{extension}"):
        if existing.name not in files:
            existing.unlink()

    for filename, content in files.items():
        (destination / filename).write_text(content, encoding="utf-8")

    counts = {category: len(groups[category]) for category in groups}
    print(
        f"{format_name}: source={len(rules)}, duplicates={duplicates}, "
        f"output={sum(counts.values())}; "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surge-source", type=Path, required=True)
    parser.add_argument("--clash-source", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("rules"))
    args = parser.parse_args()

    generate(args.surge_source, args.output_root / "Surge", "Surge")
    generate(args.clash_source, args.output_root / "Clash", "Clash")


if __name__ == "__main__":
    main()
