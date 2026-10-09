"""The bank on disk is the benchmark. The generator must reproduce it exactly."""

import json
import unittest
from pathlib import Path

from sanzaru.bank import build, shipped, split_of
from sanzaru.tasks import CORE, PLUS, RETIRED

BANK = Path(__file__).resolve().parent.parent / "bank"


class BankTests(unittest.TestCase):
    def test_the_splits_do_not_overlap(self):
        shelves = [set(CORE), set(PLUS), set(RETIRED)]
        for i, a in enumerate(shelves):
            for b in shelves[i + 1:]:
                self.assertFalse(a & b)

    def test_building_twice_is_the_same_bank(self):
        self.assertEqual(build(), build())

    def test_every_config_ships_its_contract_and_five_bombs(self):
        tree = build()
        for kind in shipped():
            folder = [rel for rel in tree if f"/{kind.value}/" in rel]
            self.assertEqual(len(folder), 6, kind.value)  # config.json + 5 bombs

    def test_the_manifest_counts_what_the_folders_hold(self):
        manifest = json.loads(build()["manifest.json"])
        self.assertEqual([c["label"] for c in manifest["configs"]],
                         [k.value for k in shipped()])
        for config in manifest["configs"]:
            self.assertIn(config["split"], ("core", "plus", "retired"))

    @unittest.skipUnless(BANK.is_dir(), "no bank checked out")
    def test_the_generator_still_reproduces_the_shipped_bank(self):
        """Byte-for-byte. If this fails, the generator drifted under the frozen
        benchmark: fix the code, or consciously rebuild and version the bank."""
        tree = build()
        on_disk = {str(p.relative_to(BANK)): p.read_text(encoding="utf-8")
                   for p in BANK.rglob("*.json")}
        self.assertEqual(on_disk.keys(), tree.keys())
        for rel, content in tree.items():
            self.assertEqual(on_disk[rel], content, f"{rel} drifted")
