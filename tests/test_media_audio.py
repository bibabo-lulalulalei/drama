from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import media


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "需要 ffmpeg/ffprobe")
class CutAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source.wav"
        self.output = self.root / "derived.wav"
        rate = 44100
        samples = []
        for index in range(rate * 2):
            timestamp = index / rate
            amplitude = 0 if 0.4 <= timestamp < 0.8 or 1.2 <= timestamp < 1.6 else 0.2
            value = round(32767 * amplitude * math.sin(2 * math.pi * 440 * timestamp))
            samples.append(struct.pack("<h", value))
        with wave.open(str(self.source), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(rate)
            target.writeframes(b"".join(samples))

    def tearDown(self):
        self.temp.cleanup()

    def args(self, removals):
        return argparse.Namespace(
            audio=str(self.source), out=str(self.output),
            remove=[media._parse_audio_removal(text) for text in removals],
        )

    def test_explicit_pause_cuts_preserve_source_and_close_duration(self):
        source_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        result = media.cmd_cut_audio(self.args(["0.5:0.7", "1.3:1.5"]))
        self.assertTrue(result["full_decode_ok"])
        self.assertAlmostEqual(1.6, result["duration_s"], places=3)
        self.assertEqual(source_sha, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(source_sha, result["source_sha256"])
        self.assertTrue(self.output.is_file())

    def test_existing_output_is_never_overwritten(self):
        self.output.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "不能覆盖"):
            media.cmd_cut_audio(self.args(["0.5:0.7"]))
        self.assertEqual(b"keep", self.output.read_bytes())

    def test_overlapping_ranges_are_rejected_before_output(self):
        with self.assertRaisesRegex(ValueError, "不重叠"):
            media.cmd_cut_audio(self.args(["0.5:0.9", "0.7:1.0"]))
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
