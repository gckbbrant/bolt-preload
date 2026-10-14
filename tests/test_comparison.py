"""Exercise custom paired inputs and failure boundaries with both native CLIs."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FATIGUE = Path(os.environ.get("FATIGUE_PROJECT", str(ROOT.parent / "fatigue-spectrum"))).resolve()


class PairedComparison(unittest.TestCase):
    def setUp(self):
        (ROOT / "_build").mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="paired-test-", dir=ROOT / "_build")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.profile = self.path / "joint.json"
        self.loads = self.path / "loads.csv"
        self.sn = self.path / "sn.json"
        self.output = self.path / "report.json"
        self.profile.write_bytes((ROOT / "samples/joint.json").read_bytes())
        self.loads.write_text("time_s,force_n\n0,0\n1,5000\n2,0\n", encoding="utf-8")
        self.sn.write_bytes((FATIGUE / "samples/sn.json").read_bytes())

    def run_comparison(self, *extra):
        return subprocess.run([
            sys.executable, "scripts/compare_joints.py", "--fatigue", str(FATIGUE),
            "--profile", str(self.profile), "--loads", str(self.loads),
            "--sn", str(self.sn), "--output", str(self.output),
        ] + list(extra), cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_custom_inputs_and_stiffnesses(self):
        p = self.run_comparison("--stiff-stiffness", "600000", "--soft-stiffness", "200000")
        self.assertEqual(p.returncode, 0, p.stderr)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        cases = report["cases"]
        self.assertEqual(cases["stiff_joint"]["load_fraction"], 0.25)
        self.assertEqual(cases["soft_joint"]["load_fraction"], 0.5)
        self.assertEqual(cases["stiff_joint"]["maximum_stress_mpa"], 225)
        self.assertEqual(cases["soft_joint"]["maximum_stress_mpa"], 250)
        self.assertAlmostEqual(report["soft_to_stiff_damage_ratio"], 16)
        self.assertEqual(report["data_source"], str(self.loads))
        self.assertEqual(report["sn_source"], str(self.sn))
        self.assertEqual(report["command_argv"][report["command_argv"].index("--loads") + 1], str(self.loads))

    def test_constant_load_has_no_damage_ratio(self):
        self.loads.write_text("time_s,force_n\n0,5000\n1,5000\n", encoding="utf-8")
        p = self.run_comparison()
        self.assertEqual(p.returncode, 0, p.stderr)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertIsNone(report["soft_to_stiff_damage_ratio"])
        for case in report["cases"].values():
            self.assertEqual(case["damage"]["total_damage"], 0)

    def test_separation_removes_stale_comparison(self):
        self.loads.write_bytes((ROOT / "samples/separated.csv").read_bytes())
        self.output.write_text("old comparison", encoding="utf-8")
        p = self.run_comparison()
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("Separation", p.stderr)
        self.assertFalse(self.output.exists())

    def test_incomplete_curve_removes_stale_comparison(self):
        self.sn.write_text('[{"amplitude_mpa": 1, "cycles_to_failure": 100}, {"amplitude_mpa": 2, "cycles_to_failure": 10}]', encoding="utf-8")
        self.output.write_text("old comparison", encoding="utf-8")
        p = self.run_comparison()
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("coverage incomplete", p.stderr)
        self.assertFalse(self.output.exists())

    def test_output_input_alias_is_preserved(self):
        original = self.loads.read_bytes()
        p = self.run_comparison("--output", str(self.loads.parent / "." / self.loads.name))
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(self.loads.read_bytes(), original)

    def test_invalid_numeric_option_is_rejected(self):
        for value in ("nan", "inf", "-1", "0"):
            p = self.run_comparison("--bin-width", value)
            self.assertEqual(p.returncode, 2, p.stderr)
            self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
