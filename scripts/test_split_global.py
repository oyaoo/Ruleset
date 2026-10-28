import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from split_global import (  # noqa: E402
    REGION_CODES,
    REGION_ORDER,
    REMAINDER_NAME,
    generate,
    file_content,
    read_clash,
    read_surge,
    region_of_rule,
    split_rules,
)


class TestGlobalRegionSplit(unittest.TestCase):
    def test_region_mapping(self):
        cases = {
            "DOMAIN,shop.co.jp": "Japan",
            "DOMAIN-SUFFIX,example.jp": "Japan",
            "DOMAIN-SUFFIX,example.us": "Americas",
            "DOMAIN-SUFFIX,example.ca": "Americas",
            "DOMAIN-SUFFIX,example.br": "Americas",
            "DOMAIN-SUFFIX,example.mx": "Americas",
            "DOMAIN-SUFFIX,example.pr": "Americas",
            "DOMAIN-SUFFIX,example.ai": "Americas",  # Anguilla (globally marketed TLD)
            "DOMAIN-SUFFIX,example.sg": "SoutheastAsia",
            "DOMAIN-SUFFIX,example.vn": "SoutheastAsia",
            "DOMAIN,example.tl": "SoutheastAsia",
            "DOMAIN-SUFFIX,example.de": "Europe",
            "DOMAIN-SUFFIX,example.fr": "Europe",
            "DOMAIN-SUFFIX,example.eu": "Europe",
            "DOMAIN-SUFFIX,example.com": None,
            "DOMAIN-SUFFIX,example.net": None,
            "DOMAIN-SUFFIX,example.uk": "Europe",
            "DOMAIN-SUFFIX,example.co.uk": "Europe",
            "DOMAIN-SUFFIX,example.gb": "Europe",
            "DOMAIN-SUFFIX,example.ch": "Europe",
            "DOMAIN-SUFFIX,example.no": "Europe",
            "DOMAIN-SUFFIX,example.hk": None,
            "DOMAIN-SUFFIX,example.cn": None,
            "DOMAIN-SUFFIX,example.io": None,
            "DOMAIN-KEYWORD,example.jp": None,
            "IP-CIDR,1.2.3.0/24,no-resolve": None,
            "PROCESS-NAME,AnyApp": None,
            "DOMAIN-SUFFIX,*.jp": None,
        }
        for rule, expected in cases.items():
            with self.subTest(rule=rule):
                self.assertEqual(region_of_rule(rule), expected)

    def test_all_27_eu_codes_plus_uk_ch_no(self):
        european_codes = set("""
            AT BE BG CY CZ DE DK EE ES FI FR GR HR HU IE IT LT LU LV
            MT NL PL PT RO SE SI SK EU GB CH NO
        """.split())
        self.assertEqual(REGION_CODES["Europe"], european_codes)
        for code in european_codes:
            with self.subTest(code=code):
                self.assertEqual(region_of_rule(f"DOMAIN-SUFFIX,example.{code.lower()}"), "Europe")

    def test_regions_are_disjoint(self):
        codes = [x for region in REGION_ORDER for x in REGION_CODES[region]]
        self.assertEqual(len(codes), len(set(codes)))

    def test_separate_formats_no_loss_prune_old_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            surge = base / "surge.list"
            clash = base / "clash.yaml"
            surge.write_text(
                "# original\n"
                "DOMAIN-SUFFIX,shop.co.jp\nDOMAIN-SUFFIX,site.us\n"
                "DOMAIN-SUFFIX,site.vn\nDOMAIN-SUFFIX,site.de\n"
                "DOMAIN-SUFFIX,site.uk\nDOMAIN-SUFFIX,site.com\n"
                "DOMAIN-KEYWORD,test\nUSER-AGENT,SomeUserAgent*\n"
                "DOMAIN-SUFFIX,shop.co.jp\n", encoding="utf-8"
            )
            clash.write_text(
                "payload:\n"
                "  - 'DOMAIN-SUFFIX,shop.co.jp'\n"
                "  - 'DOMAIN-SUFFIX,site.ca'\n"
                "  - 'DOMAIN-SUFFIX,site.sg'\n"
                "  - 'DOMAIN-SUFFIX,site.eu'\n"
                "  - 'DOMAIN-SUFFIX,site.com'\n"
                "  - 'IP-CIDR,8.8.8.0/24,no-resolve'\n", encoding="utf-8"
            )
            surge_dir = base / "output/Surge"
            clash_dir = base / "output/Clash"
            surge_dir.mkdir(parents=True)
            clash_dir.mkdir(parents=True)
            (surge_dir / "US.list").write_text("old", encoding="utf-8")
            (clash_dir / "DE.yaml").write_text("old", encoding="utf-8")
            (clash_dir / "EU.yaml").write_text("old", encoding="utf-8")
            (surge_dir / "EU.list").write_text("old", encoding="utf-8")
            c1 = generate(surge, surge_dir, "Surge")
            c2 = generate(clash, clash_dir, "Clash")
            self.assertEqual(c1, {
                "Japan": 1, "Americas": 1, "SoutheastAsia": 1, "Europe": 2,
                REMAINDER_NAME: 3,
            })
            self.assertEqual(c2, {
                "Japan": 1, "Americas": 1, "SoutheastAsia": 1, "Europe": 1,
                REMAINDER_NAME: 2,
            })
            self.assertEqual(
                {x.name for x in surge_dir.iterdir()},
                {f"{key}.list" for key in (*REGION_ORDER, REMAINDER_NAME)},
            )
            self.assertEqual(
                {x.name for x in clash_dir.iterdir()},
                {f"{key}.yaml" for key in (*REGION_ORDER, REMAINDER_NAME)},
            )
            self.assertEqual(read_surge(surge_dir / "Japan.list"), ["DOMAIN-SUFFIX,shop.co.jp"])
            self.assertEqual(read_surge(surge_dir / "Europe.list"), ["DOMAIN-SUFFIX,site.de", "DOMAIN-SUFFIX,site.uk"])
            self.assertEqual(read_clash(clash_dir / "Europe.yaml"), ["DOMAIN-SUFFIX,site.eu"])
            self.assertEqual(read_clash(clash_dir / "Americas.yaml"), ["DOMAIN-SUFFIX,site.ca"])
            self.assertEqual(read_surge(surge_dir / "Global_All_No_Resolve.list"), [
                "DOMAIN-SUFFIX,site.com",
                "DOMAIN-KEYWORD,test", "USER-AGENT,SomeUserAgent*",
            ])
            self.assertEqual(read_clash(clash_dir / "Global_All_No_Resolve.yaml"), [
                "DOMAIN-SUFFIX,site.com", "IP-CIDR,8.8.8.0/24,no-resolve",
            ])
            self.assertEqual(sum(c1.values()), len(set(read_surge(surge))))
            self.assertEqual(sum(c2.values()), len(set(read_clash(clash))))

    def test_empty_clash_region_is_valid_yaml(self):
        import yaml
        self.assertEqual(yaml.safe_load(file_content("Clash", "Japan", [])), {"payload": []})

    def test_empty_input_fails_without_deleting_previous_files(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            src = folder / "empty.list"
            src.write_text("# no rules\n", encoding="utf-8")
            dest = folder / "out"
            dest.mkdir()
            (dest / "US.list").write_text("old", encoding="utf-8")
            with self.assertRaises(ValueError):
                generate(src, dest, "Surge")
            self.assertTrue((dest / "US.list").exists())


if __name__ == "__main__":
    unittest.main()
