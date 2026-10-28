"""Ensure effect command filter classes are exposed at the voicelink package root."""

import unittest

import voicelink


class TestFilterExports(unittest.TestCase):
    def test_effect_filters_are_exported(self):
        for name in (
            "Equalizer",
            "Timescale",
            "Karaoke",
            "Tremolo",
            "Vibrato",
            "Rotation",
            "ChannelMix",
            "Distortion",
            "LowPass",
        ):
            with self.subTest(name=name):
                self.assertTrue(hasattr(voicelink, name), f"voicelink.{name} is missing")
