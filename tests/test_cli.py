"""Native CLI tests for joint separation, CSV exports and file handling."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JointCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["moon", "build", "--target", "native"], cwd=ROOT, check=True)
        base = ROOT / "_build/native/debug/build/cmd/main/main"
        cls.binary = next((p for p in (base.with_suffix(".exe"), base) if p.is_file()), None)
        if cls.binary is None:
            raise FileNotFoundError("moon build produced no native CLI at " + str(base))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="joint-cli-", dir=ROOT / "_build")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)

    def run_cli(self, *args):
        return subprocess.run([str(self.binary)] + [str(a) for a in args], cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")

    def test_normalize_logger_can_be_reused_without_import_options(self):
        canonical, summary, stress = (self.path / n for n in ("loads.csv", "summary.json", "stress.csv"))
        p = self.run_cli("normalize", "samples/logger-loads.csv", "--time-column", "Clock", "--force-column", "Load", "--time-unit", "ms", "--force-unit", "kN", "--delimiter", "semicolon", "--skip-rows", "2", "--decimal-separator", "comma", "--csv", canonical, "--json", summary)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(canonical.read_text(encoding="utf-8"), "time_s,force_n\n0,0\n1,5000\n2,0\n")
        self.assertEqual(json.loads(summary.read_text(encoding="utf-8")), {"input_samples": 3, "time_start_s": 0, "time_end_s": 2, "minimum_force_n": 0, "maximum_force_n": 5000})
        p = self.run_cli("history", "samples/joint.json", canonical, "--stress", stress)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(stress.read_text(encoding="utf-8"), "time_s,stress_mpa\n0,200\n1,220\n2,200\n")

    def test_normalize_checks_input_without_a_joint_model(self):
        p = self.run_cli("normalize", "samples/separated.csv")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Samples:", p.stdout)

    def test_normalize_preserves_inputs_and_rejects_shared_outputs(self):
        source = self.path / "loads.csv"
        original = (ROOT / "samples/loads.csv").read_bytes()
        source.write_bytes(original)
        p = self.run_cli("normalize", source, "--csv", str(source.parent) + "/./" + source.name)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(source.read_bytes(), original)
        output = self.path / "result.csv"
        output.write_text("existing", encoding="utf-8")
        p = self.run_cli("normalize", source, "--csv", output, "--json", output)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_normalize_invalid_source_clears_both_old_exports(self):
        source, csv, summary = (self.path / n for n in ("bad.csv", "loads.csv", "summary.json"))
        source.write_text("metadata\ntime_s,force_n\n0,0\n1,-1\n", encoding="utf-8")
        for path in (csv, summary):
            path.write_text("stale", encoding="utf-8")
        p = self.run_cli("normalize", source, "--skip-rows", "1", "--csv", csv, "--json", summary)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("line 4", p.stderr)
        self.assertFalse(csv.exists())
        self.assertFalse(summary.exists())

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

    def test_measurement_column_mapping_and_units(self):
        loads, stress = self.path / "instrument.csv", self.path / "stress.csv"
        loads.write_text('note;Load;Clock\n"sensor; A";0;0\n"sensor B";5;1000\n', encoding="utf-8")
        p = self.run_cli("history", "samples/joint.json", loads, "--time-column", "Clock", "--force-column", "Load", "--time-unit", "ms", "--force-unit", "kN", "--delimiter", "semicolon", "--stress", stress)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(stress.read_text(encoding="utf-8"), "time_s,stress_mpa\n0,200\n1,220\n")

    def test_preamble_and_decimal_comma_preserve_numeric_input(self):
        source, stress = self.path / "locale.csv", self.path / "stress.csv"
        source.write_text('instrument export\nsep=;\nClock;Load\n0,0;0,0\n1000,0;5,0\n', encoding="utf-8")
        p = self.run_cli("history", "samples/joint.json", source, "--time-column", "Clock", "--force-column", "Load", "--time-unit", "ms", "--force-unit", "kN", "--delimiter", "semicolon", "--skip-rows", "2", "--decimal-separator", "comma", "--stress", stress)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(stress.read_text(encoding="utf-8"), "time_s,stress_mpa\n0,200\n1,220\n")

    def test_preamble_keeps_source_line_number_on_invalid_value(self):
        source, stress = self.path / "invalid.csv", self.path / "stress.csv"
        source.write_text('instrument export\nsep=;\ntime_s;force_n\n0;1.234,5\n', encoding="utf-8")
        stress.write_text("stale", encoding="utf-8")
        p = self.run_cli("history", "samples/joint.json", source, "--delimiter", "semicolon", "--skip-rows", "2", "--decimal-separator", "comma", "--stress", stress)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("line 4", p.stderr)
        self.assertFalse(stress.exists())

    def test_unknown_input_unit_clears_old_export(self):
        stress = self.path / "stress.csv"
        stress.write_text("old result", encoding="utf-8")
        p = self.run_cli("history", "samples/joint.json", "samples/loads.csv", "--force-unit", "kg", "--stress", stress)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("force-unit", p.stderr)
        self.assertFalse(stress.exists())

    def test_outputs_cannot_alias_each_other(self):
        output = self.path / "same.txt"
        output.write_text("preserve", encoding="utf-8")
        p = self.run_cli("analyze", "samples/joint.json", "--force", "5000", "--json", output, "--svg", output)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
