"""Portable paired artifacts are computed by both native CLIs."""
import hashlib
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FATIGUE = Path(os.environ.get("FATIGUE_PROJECT", str(ROOT.parent / "fatigue-spectrum"))).resolve()


class ComparisonBundle(unittest.TestCase):
    def setUp(self):
        (ROOT / "_build").mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="bundle-", dir=ROOT / "_build")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.bundle = self.path / "portable results"

    def run_bundle(self, *extra):
        return subprocess.run([sys.executable, str(ROOT / "scripts/compare_joints.py"), "--fatigue", str(FATIGUE), "--bundle", str(self.bundle)] + [str(x) for x in extra], cwd=self.path, capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_bundle_files_hashes_and_moved_native_reuse(self):
        p = self.run_bundle()
        self.assertEqual(p.returncode, 0, p.stderr)
        manifest = json.loads((self.bundle / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["kind"], "joint-comparison")
        self.assertEqual(len(manifest["files"]), 14)
        for entry in manifest["files"]:
            self.assertEqual(entry["sha256"], hashlib.sha256((self.bundle / entry["path"]).read_bytes()).hexdigest())
        self.assertFalse((self.bundle / "input-loads.csv").exists())
        self.assertFalse((self.bundle / "input-config.json").exists())
        moved = self.path / "moved results"
        shutil.move(str(self.bundle), moved)
        report = json.loads((moved / "comparison.json").read_text(encoding="utf-8"))
        self.assertNotIn(str(self.path), (moved / "comparison.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_input_sha256"], report["input_sha256"])
        cli_base = FATIGUE / "_build/native/debug/build/cmd/main/main"
        binary = next(p for p in (cli_base.with_suffix(".exe"), cli_base) if p.is_file())
        for case, original in report["cases"].items():
            output = self.path / (case + "-reused.json")
            p = subprocess.run([str(binary), "from-cycles", str(moved / (case + "-cycles.csv")), "--sn", str(moved / "sn.json"), "--json", str(output)], cwd=self.path, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            reused = json.loads(output.read_text(encoding="utf-8"))
            for key in ("cycles", "spectrum", "damage"):
                self.assertEqual(reused[key], original[key])
            self.assertNotIn("input_samples", reused)
            original_file = json.loads((moved / (case + "-fatigue.json")).read_text(encoding="utf-8"))
            self.assertEqual(original_file["input_file"], case + "-stress.csv")

    def test_default_json_and_bundle_have_identical_calculations(self):
        p = self.run_bundle()
        self.assertEqual(p.returncode, 0, p.stderr)
        output = self.path / "old-mode.json"
        p = subprocess.run([sys.executable, str(ROOT / "scripts/compare_joints.py"), "--fatigue", str(FATIGUE), "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        old, new = [json.loads(p.read_text(encoding="utf-8")) for p in (output, self.bundle / "comparison.json")]
        for key in ("cases", "load_format", "canonical_load_format", "load_summary", "input_sha256", "soft_to_stiff_damage_ratio"):
            self.assertEqual(old[key], new[key])

    def test_bundle_config_paths_and_cli_import_override(self):
        config = self.path / "comparison.json"
        settings = {"fatigue": str(FATIGUE), "sn": str(FATIGUE / "samples/sn.json"), "loads": str(ROOT / "samples/sensor-loads.csv"), "input_config": str(ROOT / "samples/sensor-input.json"), "bundle": "config results/saved", "force_gain": -4}
        config.write_text(json.dumps(settings), encoding="utf-8")
        p = subprocess.run([sys.executable, str(ROOT / "scripts/compare_joints.py"), "--config", str(config), "--force-gain", "-3"], cwd=self.path, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        directory = self.path / settings["bundle"]
        report = json.loads((directory / "comparison.json").read_text(encoding="utf-8"))
        self.assertEqual(report["load_summary"]["maximum_force_n"], 3000)
        self.assertEqual(report["load_format"]["force_gain"], -3)
        self.assertEqual(report["canonical_load_format"]["force_gain"], 1)
        self.assertIn("input_config", report["input_sha256"])
        self.assertNotIn("input-config.json", [p.name for p in directory.iterdir()])

    def test_existing_nonempty_empty_and_file_targets_are_preserved(self):
        for kind in ("nonempty", "empty", "file"):
            target = self.path / kind
            if kind == "file":
                target.write_text("keep", encoding="utf-8")
            else:
                target.mkdir()
                if kind == "nonempty":
                    (target / "keep.txt").write_text("keep", encoding="utf-8")
            p = self.run_bundle("--bundle", target)
            self.assertEqual(p.returncode, 2, p.stderr)
            if kind == "empty":
                self.assertEqual(list(target.iterdir()), [])
            else:
                self.assertEqual((target if kind == "file" else target / "keep.txt").read_text(encoding="utf-8"), "keep")
        self.assertEqual(list(self.path.glob(".joint-bundle-*")), [])

    def test_failed_calculations_leave_no_bundle(self):
        narrow = self.path / "narrow.json"
        narrow.write_text('[{"amplitude_mpa":1,"cycles_to_failure":100},{"amplitude_mpa":2,"cycles_to_failure":10}]', encoding="utf-8")
        for options in (("--loads", ROOT / "samples/separated.csv"), ("--sn", narrow)):
            p = self.run_bundle(*options)
            self.assertEqual(p.returncode, 2, p.stderr)
            self.assertFalse(self.bundle.exists())
            self.assertEqual(list(self.path.glob(".joint-bundle-*")), [])

    def test_constant_load_bundle_preserves_empty_cycles(self):
        loads = self.path / "constant.csv"
        loads.write_text("time_s,force_n\n0,5000\n1,5000\n", encoding="utf-8")
        p = self.run_bundle("--loads", loads)
        self.assertEqual(p.returncode, 0, p.stderr)
        report = json.loads((self.bundle / "comparison.json").read_text(encoding="utf-8"))
        self.assertIsNone(report["soft_to_stiff_damage_ratio"])
        for case in report["cases"]:
            self.assertEqual((self.bundle / (case + "-cycles.csv")).read_text(encoding="utf-8"), "range_mpa,mean_mpa,count,start_index,end_index\n")

    def test_dangling_symlink_target_is_not_followed(self):
        missing = self.path / "missing target"
        try:
            self.bundle.symlink_to(missing, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation is unavailable on this host")
        p = self.run_bundle()
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertTrue(self.bundle.is_symlink())
        self.assertFalse(missing.exists())

    def test_bundle_output_conflict_and_input_overlap_preserve_inputs(self):
        output = self.path / "keep.json"
        output.write_text("keep", encoding="utf-8")
        p = self.run_bundle("--output", output)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "keep")
        original = (ROOT / "samples/loads.csv").read_bytes()
        for target in (ROOT / "samples/loads.csv", ROOT, ROOT.parent):
            p = self.run_bundle("--bundle", target)
            self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual((ROOT / "samples/loads.csv").read_bytes(), original)

    def script(self):
        spec = importlib.util.spec_from_file_location("compare_bundle", ROOT / "scripts/compare_joints.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def args(self, module):
        args = argparse.Namespace(config=None, profile=None, loads=None, sn=None, fatigue=FATIGUE, output=None, bundle=self.bundle, input_config=None)
        profile, loads, sn, _, _, _ = module.configuration(args, ROOT)
        return profile, loads, sn, args

    def test_transfer_error_cleans_only_its_new_directory(self):
        module = self.script()
        profile, loads, sn, args = self.args(module)
        replace = Path.replace
        def fail_during_transfer(path, target):
            if target == self.bundle / "load-summary.json":
                raise OSError("simulated transfer failure")
            return replace(path, target)
        with mock.patch.object(Path, "replace", autospec=True, side_effect=fail_during_transfer):
            with self.assertRaisesRegex(OSError, "transfer failure"):
                module.write_bundle(ROOT, FATIGUE, profile, loads, sn, args)
        self.assertFalse(self.bundle.exists())
        self.assertEqual(list(self.path.glob(".joint-bundle-*")), [])

    def test_target_created_during_calculation_is_preserved(self):
        module = self.script()
        profile, loads, sn, args = self.args(module)
        calculate = module.compare
        def concurrent_creator(*pos, **kw):
            report = calculate(*pos, **kw)
            self.bundle.mkdir()
            return report
        with mock.patch.object(module, "compare", side_effect=concurrent_creator):
            with self.assertRaises(FileExistsError):
                module.write_bundle(ROOT, FATIGUE, profile, loads, sn, args)
        self.assertEqual(list(self.bundle.iterdir()), [])
        self.assertEqual(list(self.path.glob(".joint-bundle-*")), [])


if __name__ == "__main__":
    unittest.main()
