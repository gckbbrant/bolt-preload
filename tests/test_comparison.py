"""Exercise custom paired inputs and failure boundaries with both native CLIs."""
import json
import argparse
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
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

    def run_config(self, text, *extra):
        config = self.path / "comparison.json"
        config.write_text(text, encoding="utf-8")
        elsewhere = self.path / "another working directory"
        elsewhere.mkdir(exist_ok=True)
        return subprocess.run([
            sys.executable, str(ROOT / "scripts/compare_joints.py"), "--config", str(config),
        ] + list(extra), cwd=elsewhere, capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_config_relative_paths_column_units_and_explicit_override(self):
        self.loads.write_text('logger export\nsep=;\nNote;Load;Clock\n"sensor; A";0,0;0,0\n"sensor B";5,0;1000,0\n"sensor C";0,0;2000,0\n', encoding="utf-8")
        settings = {
            "profile": "joint.json", "loads": "loads.csv", "sn": "sn.json",
            "fatigue": os.path.relpath(FATIGUE, self.path), "output": "new results/report.json",
            "time_column": "Clock", "force_column": "Load", "time_unit": "ms",
            "force_unit": "kN", "delimiter": "semicolon", "stiff_stiffness": 800000,
            "skip_rows": 2, "decimal_separator": "comma",
        }
        p = self.run_config(json.dumps(settings), "--stiff-stiffness", "600000")
        self.assertEqual(p.returncode, 0, p.stderr)
        report = json.loads((self.path / "new results/report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["cases"]["stiff_joint"]["maximum_stress_mpa"], 225)
        self.assertEqual(report["cases"]["stiff_joint"]["stress_samples"][1]["time_s"], 1)
        self.assertEqual(report["load_format"]["force_unit"], "kN")
        self.assertEqual(report["load_format"]["skip_rows"], 2)
        self.assertEqual(report["load_format"]["decimal_separator"], "comma")
        self.assertEqual(report["load_summary"], {"input_samples": 3, "time_start_s": 0, "time_end_s": 2, "minimum_force_n": 0, "maximum_force_n": 5000})
        self.assertEqual(report["data_source"], str(self.loads))

    def test_sensor_config_calibrates_once_and_records_parameters(self):
        self.loads.write_text("Clock;Bridge\n0;2.5\n1000;1.5\n2000;2.5\n", encoding="utf-8")
        config = {
            "profile": "joint.json", "loads": "loads.csv", "sn": "sn.json",
            "fatigue": str(FATIGUE), "output": "report.json",
            "time_column": "Clock", "force_column": "Bridge", "time_unit": "ms",
            "force_unit": "kN", "delimiter": "semicolon", "force_zero": 2.5, "force_gain": -5,
        }
        p = self.run_config(json.dumps(config), "--force-gain=-4e0")
        self.assertEqual(p.returncode, 0, p.stderr)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(report["load_format"]["force_zero"], 2.5)
        self.assertEqual(report["load_format"]["force_gain"], -4)
        self.assertEqual(report["load_summary"]["maximum_force_n"], 4000)
        self.assertEqual(report["cases"]["stiff_joint"]["maximum_stress_mpa"], 216)
        self.assertEqual(report["cases"]["soft_joint"]["maximum_stress_mpa"], 232)
        self.assertAlmostEqual(report["soft_to_stiff_damage_ratio"], 16)
        self.assertEqual(report["input_sha256"]["loads"], hashlib.sha256(self.loads.read_bytes()).hexdigest())

    def sensor_preset(self):
        preset = self.path / "input preset.json"
        preset.write_text(json.dumps({"schema_version": 1, "kind": "load", "time_column": "Clock", "force_column": "Bridge", "time_unit": "ms", "force_unit": "kN", "delimiter": "semicolon", "force_zero": 2.5, "force_gain": -5}), encoding="utf-8")
        self.loads.write_text("Clock;Bridge\n0;2.5\n1000;1.5\n2000;2.5\n", encoding="utf-8")
        return preset

    def test_preset_comparison_and_cli_precedence_from_another_directory(self):
        preset = self.sensor_preset()
        settings = {"profile": "joint.json", "loads": "loads.csv", "sn": "sn.json", "fatigue": str(FATIGUE), "output": "report.json", "input_config": preset.name, "force_gain": -4}
        p = self.run_config(json.dumps(settings), "--force-gain", "-3")
        self.assertEqual(p.returncode, 0, p.stderr)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(report["load_summary"]["maximum_force_n"], 3000)
        self.assertEqual(report["load_format"]["force_gain"], -3)
        self.assertEqual(report["load_format"]["force_zero"], 2.5)
        self.assertEqual(report["load_format"]["force_unit"], "kN")
        self.assertEqual(report["canonical_load_format"]["force_unit"], "N")
        self.assertEqual(report["canonical_load_format"]["force_gain"], 1)
        self.assertEqual(report["input_sha256"]["input_config"], hashlib.sha256(preset.read_bytes()).hexdigest())
        p = self.run_config(json.dumps(settings))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8"))["load_summary"]["maximum_force_n"], 4000)
        del settings["force_gain"]
        p = self.run_config(json.dumps(settings))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8"))["load_summary"]["maximum_force_n"], 5000)

    def test_input_preset_cannot_be_overwritten(self):
        preset = self.sensor_preset()
        original = preset.read_bytes()
        p = self.run_comparison("--input-config", str(preset), "--output", str(preset))
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(preset.read_bytes(), original)

    def test_invalid_preset_is_not_hidden_by_comparison_override(self):
        preset = self.sensor_preset()
        settings = json.loads(preset.read_text(encoding="utf-8"))
        settings["force_gain"] = 0
        preset.write_text(json.dumps(settings), encoding="utf-8")
        self.output.write_text("stale", encoding="utf-8")
        p = self.run_comparison("--input-config", str(preset), "--force-gain", "-5")
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("gain", p.stderr)
        self.assertFalse(self.output.exists())

    def test_preset_snapshot_survives_source_change_before_normalization(self):
        preset = self.sensor_preset()
        original = preset.read_bytes()
        spec = importlib.util.spec_from_file_location("paired_script", ROOT / "scripts/compare_joints.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = argparse.Namespace(config=None, profile=self.profile, loads=self.loads, sn=self.sn, fatigue=FATIGUE, output=self.output, input_config=preset)
        module.configuration(args, ROOT)
        build = module.executable
        changed = []
        def change_during_build(root):
            binary = build(root)
            if root == ROOT and not changed:
                preset.write_text('{"schema_version":1,"kind":"load","force_gain":0}', encoding="utf-8")
                changed.append(True)
            return binary
        with mock.patch.object(module, "executable", side_effect=change_during_build):
            report = module.compare(ROOT, FATIGUE, self.profile, self.loads, self.sn, args)
        self.assertTrue(changed)
        self.assertEqual(report["input_sha256"]["input_config"], hashlib.sha256(original).hexdigest())
        self.assertEqual(report["load_format"]["force_gain"], -5)
        self.assertEqual(report["cases"]["stiff_joint"]["maximum_stress_mpa"], 220)
        self.assertEqual(report["cases"]["soft_joint"]["maximum_stress_mpa"], 240)

    def test_config_rejects_unknown_duplicate_and_bad_values(self):
        for text in (
            '{"force_unitt": "kN"}', '{"time_unit": "s", "time_unit": "ms"}',
            '{"force_unit": "kg"}', '{"stiff_stiffness": true}',
            '{"bin_width": 0}', '{"loads": null}', '[]',
            '{"skip_rows": -1}', '{"skip_rows": 1.5}', '{"skip_rows": true}',
            '{"decimal_separator": "locale"}',
            '{"force_zero": true}', '{"force_gain": 0}', '{"force_gain": "2"}',
            '{"force_zero": 1e309}', '{"force_gain": 1e309}',
        ):
            p = self.run_config(text)
            self.assertEqual(p.returncode, 2, p.stderr)
            self.assertNotIn("Traceback", p.stderr)

    def test_config_cannot_overwrite_itself(self):
        text = json.dumps({"output": "comparison.json"})
        p = self.run_config(text)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual((self.path / "comparison.json").read_text(encoding="utf-8"), text)

    def test_comparison_uses_one_snapshot_even_when_source_files_change(self):
        spec = importlib.util.spec_from_file_location("paired_script", ROOT / "scripts/compare_joints.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = argparse.Namespace(config=None, profile=self.profile, loads=self.loads, sn=self.sn, fatigue=FATIGUE, output=self.output)
        module.configuration(args, ROOT)
        original = {"profile": self.profile.read_bytes(), "loads": self.loads.read_bytes(), "sn": self.sn.read_bytes()}
        original_run = module.run
        changed = []
        def change_after_history(binary, root, *arguments):
            result = original_run(binary, root, *arguments)
            if arguments[0] == "history" and not changed:
                self.loads.write_bytes((ROOT / "samples/separated.csv").read_bytes())
                self.sn.write_text('[{"amplitude_mpa": 1, "cycles_to_failure": 100}, {"amplitude_mpa": 2, "cycles_to_failure": 10}]', encoding="utf-8")
                changed.append(True)
            return result
        with mock.patch.object(module, "run", side_effect=change_after_history):
            report = module.compare(ROOT, FATIGUE, self.profile, self.loads, self.sn, args)
        self.assertTrue(changed)
        self.assertEqual(report["cases"]["stiff_joint"]["maximum_stress_mpa"], 220)
        self.assertEqual(report["cases"]["soft_joint"]["maximum_stress_mpa"], 240)
        self.assertEqual(report["sn_points"], json.loads(original["sn"].decode("utf-8")))
        self.assertEqual(report["input_sha256"], {key: hashlib.sha256(value).hexdigest() for key, value in original.items()})

    def test_invalid_loads_stop_before_building_the_fatigue_tool(self):
        spec = importlib.util.spec_from_file_location("paired_script", ROOT / "scripts/compare_joints.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = argparse.Namespace(config=None, profile=self.profile, loads=self.loads, sn=self.sn, fatigue=FATIGUE, output=self.output)
        module.configuration(args, ROOT)
        self.loads.write_text("time_s,force_n\n0,0\n0,5000\n", encoding="utf-8")
        with mock.patch.object(module, "executable", wraps=module.executable) as build:
            with self.assertRaisesRegex(RuntimeError, "line 3"):
                module.compare(ROOT, FATIGUE, self.profile, self.loads, self.sn, args)
        self.assertEqual(build.call_args_list, [mock.call(ROOT)])


if __name__ == "__main__":
    unittest.main()
