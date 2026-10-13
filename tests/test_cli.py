"""Native CLI tests for joint separation, CSV exports and file handling."""
import json
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JointCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["moon", "build", "--target", "native"], cwd=ROOT, check=True)
        cls.binary = ROOT / "_build/native/debug/build/cmd/main/main"
        if platform.system() == "Windows":
            cls.binary = cls.binary.with_suffix(".exe")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="joint-cli-", dir=ROOT / "_build")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)

    def run_cli(self, *args):
        return subprocess.run([str(self.binary)] + [str(a) for a in args], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")

    def test_hand_calculation(self):
        result = self.path / "result.json"
        p = self.run_cli("analyze", "samples/joint.json", "--force", "5000", "--json", result)
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(result.read_text(encoding="utf-8"))
        self.assertEqual(data["stress_mpa"], 220)
        self.assertEqual(data["bolt_force_n"] - data["clamp_force_n"], 5000)

    def test_separation_blocks_and_removes_stale_stress(self):
        stress, report = self.path / "stress.csv", self.path / "history.json"
        stress.write_text("old result", encoding="utf-8")
        p = self.run_cli("history", "samples/joint.json", "samples/separated.csv", "--stress", stress, "--json", report)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertFalse(stress.exists())
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(data["separation"]["sample_index"], 2)
        self.assertEqual(len(data["samples"]), 2)

    def test_csv_has_correct_units_and_rows(self):
        stress = self.path / "stress.csv"
        p = self.run_cli("history", "samples/joint.json", "samples/loads.csv", "--stress", stress)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = stress.read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[0], "time_s,stress_mpa")
        self.assertEqual(len(rows), 10)

    def test_invalid_time_clears_old_export(self):
        loads, stress = self.path / "loads.csv", self.path / "stress.csv"
        loads.write_text("time_s,force_n\n1,10\n0,20\n", encoding="utf-8")
        stress.write_text("old result", encoding="utf-8")
        p = self.run_cli("history", "samples/joint.json", loads, "--stress", stress)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertFalse(stress.exists())

    def test_input_alias_is_not_overwritten(self):
        profile = self.path / "profile.json"
        original = (ROOT / "samples/joint.json").read_bytes()
        profile.write_bytes(original)
        alias = str(profile.parent) + "/./" + profile.name
        p = self.run_cli("analyze", profile, "--force", "5000", "--json", alias)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(profile.read_bytes(), original)

    def test_outputs_cannot_alias_each_other(self):
        output = self.path / "same.txt"
        output.write_text("preserve", encoding="utf-8")
        p = self.run_cli("analyze", "samples/joint.json", "--force", "5000", "--json", output, "--svg", output)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
