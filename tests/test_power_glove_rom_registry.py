# Project: VirtualGlove
# File: tests/test_power_glove_rom_registry.py
# Purpose: Keep the audited Power Glove game list and shared mappings complete.
# Author: Iain Bennett
# Copyright (c) 2026 Iain Bennett
# SPDX-License-Identifier: MIT
# Change log:
#   2026-09-04 - Added audited Power Glove ROM mapping coverage.
# Full history: docs/CHANGELOG.md and Git history.

"""Verify the audited Power Glove game registry and protocol classifications."""

import json
import unittest
from pathlib import Path

from virtualglove.profile_control import load_registry, select_profile_settings


ROOT = Path(__file__).resolve().parents[1]


class PowerGloveRomRegistryTests(unittest.TestCase):
    def test_all_audited_us_roms_have_expected_shared_profiles(self):
        games = json.loads((ROOT / "config/games.json").read_text())["games"]
        expected = {
            "Bad Street Brawler (USA)": "bad_street_brawler",
            "Defender II (USA)": "program_e",
            "Gyruss (USA)": "program_c",
            "Gun.Smoke (USA)": "program_g",
            "Joust (USA)": "program_b",
            "Knight Rider (USA)": "program_i",
            "Sesame Street 123 (USA)": "program_f",
            "Super Glove Ball (USA)": "super_glove_ball",
        }
        for stem, profile in expected.items():
            for extension in (".nes", ".zip", ".7z"):
                self.assertEqual(games[stem + extension], profile)

    def test_complete_mattel_index_uses_numeric_profiles_and_archive_names(self):
        registry = load_registry(ROOT / "config/games.json")
        expected = {
            "program_1": (
                "Blades of Steel (USA)", "Blaster Master (USA)",
                "Bubble Bobble (USA)", "Castlevania (USA)",
                "Castlevania II - Simon's Quest (USA)", "Contra (USA)",
                "Deadly Towers (USA)", "Donkey Kong Classics (USA, Europe)",
                "Double Dribble (USA)", "Gauntlet (USA)", "Gradius (USA)",
                "Jackal (USA)", "Kid Icarus (USA, Europe)",
                "Kung-Fu Heroes (USA)", "Metal Gear (USA)", "Metroid (USA)",
                "Mickey Mousecapade (USA)", "Operation Wolf (USA)",
                "Platoon (USA)", "Racket Attack (USA)", "Rampage (USA)",
                "RoboWarrior (USA)", "Rygar (USA)", "Seicross (USA)",
                "Star Force (USA)", "Superman (USA)", "Xenophobe (USA)",
                "Zelda II - The Adventure of Link (USA)",
            ),
            "program_3": ("Ice Hockey (USA)", "Top Gun (USA)"),
            "program_4": ("Iron Tank - The Invasion of Normandy (USA)",),
            "program_5": ("Alpha Mission (USA)", "Life Force (USA)",
                          "Xevious (USA)", "1943 - The Battle of Midway (USA)"),
            "program_6": ("Double Dragon (USA)",),
            "program_7": ("Mike Tyson's Punch-Out!! (USA)",),
            "program_8": ("Baseball (USA, Europe)", "Bases Loaded (USA)",
                          "R.B.I. Baseball (USA)"),
            "program_9": ("Rad Racer (USA)",),
            "program_10": ("R.C. Pro-Am (USA)",),
            "program_12": ("Super Mario Bros. (World)",),
            "program_14": ("Anticipation (USA)",),
        }
        for profile, titles in expected.items():
            for title in titles:
                for extension in (".nes", ".zip", ".7z"):
                    settings = select_profile_settings(
                        registry, "nes", title + extension
                    )
                    self.assertEqual(settings["profile"], profile, title + extension)

    def test_mattel_rapid_fire_exceptions_are_exact(self):
        registry = load_registry(ROOT / "config/games.json")
        expected = {
            "Alpha Mission (USA)": {"rapid_a": False},
            "Blaster Master (USA)": {"rapid_a": False},
            "Ice Hockey (USA)": {"rapid_b": False},
            "Double Dribble (USA)": {"rapid_a": False, "rapid_b": False},
            "Racket Attack (USA)": {"rapid_a": False, "rapid_b": False},
        }
        for title, overrides in expected.items():
            for extension in (".nes", ".zip", ".7z"):
                settings = select_profile_settings(registry, "nes", title + extension)
                for name, value in overrides.items():
                    self.assertIs(settings[name], value)

    def test_observed_library_aliases_select_the_same_profiles(self):
        registry = load_registry(ROOT / "config/games.json")
        expected = {
            "program_1": (
                "Castlevania (USA) (Rev A).7z",
                "Operation Wolf (Europe).zip",
                "Operation Wolf (Japan).zip",
                "Operation Wolf (USA) (Rev 0A).7z",
                "Platoon (USA) (Rev A).7z",
                "Robo Warrior (Europe).zip",
                "Robo Warrior (USA).7z",
                "Rygar (Europe).zip",
                "Rygar (USA) (Rev A).7z",
                "Zelda II - The Adventure of Link (Europe).zip",
                "Zelda II - The Adventure of Link (Europe) (Rev A).zip",
                "Zelda II - The Adventure of Link (Europe) (Rev B).zip",
            ),
            "program_3": (
                "Top Gun (Europe).zip",
                "Top Gun (Japan).zip",
                "Top Gun (USA) (Rev A).7z",
            ),
            "program_5": (
                "Xevious (Europe).zip",
                "Xevious (Japan).zip",
                "Xevious (Japan) (En) (Rev 1).zip",
            ),
            "program_7": (
                "Mike Tyson's Punch-Out!! (Europe).zip",
                "Mike Tyson's Punch-Out!! (Europe) (Rev A).zip",
                "Mike Tyson's Punch-Out!! (Japan, USA) (Rev A).7z",
            ),
            "program_8": ("Bases Loaded (USA) (Rev B).7z",),
            "program_10": (
                "R.C. Pro-Am (Europe).zip",
                "R.C. Pro-Am (Europe) (Rev A).zip",
                "R.C. Pro-Am (USA) (Rev A).7z",
            ),
        }
        for profile, filenames in expected.items():
            for filename in filenames:
                settings = select_profile_settings(registry, "nes", filename)
                self.assertEqual(settings["profile"], profile, filename)

        double_dribble = select_profile_settings(
            registry, "nes", "Double Dribble (USA) (Rev A).7z"
        )
        self.assertEqual(double_dribble["profile"], "program_1")
        self.assertIs(double_dribble["rapid_a"], False)
        self.assertIs(double_dribble["rapid_b"], False)

    def test_audit_keeps_native_protocol_unique_to_super_glove_ball(self):
        audit = (ROOT / "docs/power-glove-rom-input-audit.md").read_text()
        self.assertEqual(audit.count("native ten-byte Power Glove stream"), 1)
        self.assertIn("Only Super Glove Ball", audit)


if __name__ == "__main__":
    unittest.main()
