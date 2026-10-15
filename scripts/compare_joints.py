"""Compare two joint stiffnesses using a load history and a supplied S-N curve.

No Python dependencies. Requires the sibling fatigue-spectrum project and moon.
"""
import argparse
import json
import hashlib
import math
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def executable(root):
    subprocess.run(["moon", "build", "--target", "native"], cwd=root, check=True)
    base = root / "_build/native/debug/build/cmd/main/main"
    for binary in (base.with_suffix(".exe"), base):
        if binary.is_file():
            return binary
    raise FileNotFoundError("moon build produced no native CLI at " + str(base))


def run(binary, root, *args):
    result = subprocess.run([str(binary)] + [str(arg) for arg in args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "analysis failed with exit code {}".format(result.returncode))


def positive(text):
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return value


def nonnegative(text):
    value = int(text)
    if value < 0 or value > 2147483647:
        raise argparse.ArgumentTypeError("must be an integer between 0 and 2147483647")
    return value


def write_report(output, report):
    temporary = None
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, prefix="comparison-", suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(str(temporary), str(output))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def configuration(args, root):
    settings = {
        "stiff_stiffness": 800000, "soft_stiffness": 300000, "bin_width": 10,
        "time_column": "time_s", "force_column": "force_n",
        "time_unit": "s", "force_unit": "N", "delimiter": "comma",
        "skip_rows": 0, "decimal_separator": "dot",
    }
    paths = {"profile", "loads", "sn", "fatigue", "output"}
    config_path = args.config.resolve() if args.config else None
    supplied = {}
    if config_path is not None:
        def unique_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate configuration key: " + key)
                result[key] = value
            return result
        supplied = json.loads(config_path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_keys)
        if not isinstance(supplied, dict):
            raise ValueError("configuration must be a JSON object")
        unknown = set(supplied) - paths - set(settings)
        if unknown:
            raise ValueError("unknown configuration keys: " + ", ".join(sorted(unknown)))
        for key, value in supplied.items():
            if key in paths:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(key + " must be a nonempty file or directory path")
                settings[key] = (config_path.parent / value).resolve()
            else:
                settings[key] = value
    for key in paths | set(settings):
        value = getattr(args, key, None)
        if value is not None:
            settings[key] = value.resolve() if key in paths and key != "output" else value
    for key in ("stiff_stiffness", "soft_stiffness", "bin_width"):
        value = settings[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(key + " must be a number")
        settings[key] = positive(str(value))
    if settings["stiff_stiffness"] <= settings["soft_stiffness"]:
        raise ValueError("stiff_stiffness must exceed soft_stiffness")
    if isinstance(settings["skip_rows"], bool) or not isinstance(settings["skip_rows"], int):
        raise ValueError("skip_rows must be an integer")
    settings["skip_rows"] = nonnegative(str(settings["skip_rows"]))
    for key, allowed in (("time_unit", ("s", "ms")), ("force_unit", ("N", "kN")), ("delimiter", ("comma", "semicolon", "tab")), ("decimal_separator", ("dot", "comma"))):
        if settings[key] not in allowed:
            raise ValueError(key + " must be one of " + ", ".join(allowed))
    for key in ("time_column", "force_column"):
        if not isinstance(settings[key], str) or not settings[key].strip():
            raise ValueError(key + " must be a nonempty column name")
    if settings["time_column"] == settings["force_column"]:
        raise ValueError("time_column and force_column must be distinct")
    for key in settings.keys() - paths:
        setattr(args, key, settings[key])
    fatigue = settings.get("fatigue", root.parent / "fatigue-spectrum")
    args.input_loads_provided = args.loads is not None or "loads" in supplied
    args.input_sn_provided = args.sn is not None or "sn" in supplied
    return (
        settings.get("profile", root / "samples/joint.json"),
        settings.get("loads", root / "samples/loads.csv"),
        settings.get("sn", fatigue / "samples/sn.json"),
        fatigue, root / settings.get("output", Path("_build/comparison.json")), config_path,
    )


def compare(root, fatigue, profile_path, loads, sn, args):
    raw_inputs = {"profile": profile_path.read_bytes(), "loads": loads.read_bytes(), "sn": sn.read_bytes()}
    profile = json.loads(raw_inputs["profile"].decode("utf-8-sig"))
    sn_points = json.loads(raw_inputs["sn"].decode("utf-8-sig"))
    bolt_cli, fatigue_cli = executable(root), executable(fatigue)
    cases = {}
    with tempfile.TemporaryDirectory(prefix="joint-comparison-", dir=root / "_build") as directory:
        working = Path(directory)
        snapshot_loads = working / "input-loads.csv"
        snapshot_sn = working / "input-sn.json"
        snapshot_loads.write_bytes(raw_inputs["loads"])
        snapshot_sn.write_bytes(raw_inputs["sn"])
        for name, stiffness in (("stiff_joint", args.stiff_stiffness), ("soft_joint", args.soft_stiffness)):
            current = dict(profile, joint_stiffness_n_per_mm=stiffness)
            current_path = working / (name + ".json")
            stress_path = working / (name + "-stress.csv")
            history_path = working / (name + "-history.json")
            fatigue_path = working / (name + "-fatigue.json")
            current_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
            run(bolt_cli, root, "history", current_path, snapshot_loads, "--stress", stress_path, "--json", history_path,
                "--time-column", args.time_column, "--force-column", args.force_column,
                "--time-unit", args.time_unit, "--force-unit", args.force_unit, "--delimiter", args.delimiter,
                "--skip-rows", args.skip_rows, "--decimal-separator", args.decimal_separator)
            run(fatigue_cli, fatigue, "analyze", stress_path, "--sn", snapshot_sn, "--bin-width", args.bin_width, "--json", fatigue_path)
            history = json.loads(history_path.read_text(encoding="utf-8"))
            spectrum = json.loads(fatigue_path.read_text(encoding="utf-8"))
            if history.get("separation") is not None or spectrum["damage"].get("total_damage") is None:
                raise RuntimeError("comparison is outside the selected model or S-N coverage")
            cases[name] = {
                "profile": current,
                "load_fraction": history["load_fraction"],
                "separation_force_n": history["separation_force_n"],
                "minimum_clamp_force_n": min(s["clamp_force_n"] for s in history["samples"]),
                "maximum_stress_mpa": max(s["stress_mpa"] for s in history["samples"]),
                "stress_samples": history["samples"],
                "cycles": spectrum["cycles"],
                "spectrum": spectrum["spectrum"],
                "damage": spectrum["damage"],
            }
    stiff_damage = cases["stiff_joint"]["damage"]["total_damage"]
    soft_damage = cases["soft_joint"]["damage"]["total_damage"]
    ratio = soft_damage / stiff_damage if stiff_damage > 0 else None
    if ratio is not None and not math.isfinite(ratio):
        raise RuntimeError("damage ratio cannot be represented as a finite number")
    return {
        "command": subprocess.list2cmdline(["python"] + sys.argv) if os.name == "nt" else " ".join(shlex.quote(a) for a in ["python"] + sys.argv),
        "command_argv": ["python"] + sys.argv,
        "data_source": "samples/loads.csv: synthetic illustrative loads, not measured equipment data" if not args.input_loads_provided else str(loads),
        "sn_source": "fatigue-spectrum/samples/sn.json: illustrative N=1e10/amplitude^4, not certified material data" if not args.input_sn_provided else str(sn),
        "load_format": {key: getattr(args, key) for key in ("time_column", "force_column", "time_unit", "force_unit", "delimiter", "skip_rows", "decimal_separator")},
        "bin_width_mpa": args.bin_width,
        "sn_points": sn_points,
        "input_sha256": {key: hashlib.sha256(value).hexdigest() for key, value in raw_inputs.items()},
        "mean_stress_model": "none",
        "interpretation": "Compare the linear joint response and uncorrected Miner model only; this is not a measured fatigue-life result.",
        "cases": cases,
        "soft_to_stiff_damage_ratio": ratio,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="comparison JSON; its paths are relative to the config file; explicit options override it")
    parser.add_argument("--fatigue", type=Path, help="fatigue-spectrum project directory; default is the sibling project")
    parser.add_argument("--profile", type=Path, help="joint profile JSON; default samples/joint.json")
    parser.add_argument("--loads", type=Path, help="time_s,force_n CSV; default synthetic samples/loads.csv")
    parser.add_argument("--sn", type=Path, help="S-N JSON; default synthetic fatigue-spectrum/samples/sn.json")
    parser.add_argument("--stiff-stiffness", type=positive, help="stiffer joint stiffness in N/mm; default 800000")
    parser.add_argument("--soft-stiffness", type=positive, help="softer joint stiffness in N/mm; default 300000")
    parser.add_argument("--bin-width", type=positive, help="display range-bin width in MPa; default 10")
    parser.add_argument("--time-column", help="input time column; default time_s")
    parser.add_argument("--force-column", help="input force column; default force_n")
    parser.add_argument("--time-unit", choices=("s", "ms"), help="input time unit; default s")
    parser.add_argument("--force-unit", choices=("N", "kN"), help="input force unit; default N")
    parser.add_argument("--delimiter", choices=("comma", "semicolon", "tab"), help="CSV separator; default comma")
    parser.add_argument("--skip-rows", type=nonnegative, help="physical lines before the CSV header; default 0")
    parser.add_argument("--decimal-separator", choices=("dot", "comma"), help="input decimal separator; default dot")
    parser.add_argument("--output", type=Path, help="report path; default _build/comparison.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        profile_path, loads, sn, fatigue, output, config_path = configuration(args, root)
    except (OSError, ValueError, argparse.ArgumentTypeError) as error:
        parser.error(str(error))
    inputs = [profile_path, loads, sn] + ([config_path] if config_path else [])
    for input_path in inputs:
        if output.resolve() == input_path.resolve() or (output.exists() and input_path.exists() and output.samefile(input_path)):
            parser.error("output must not overwrite an input: " + str(input_path))
    try:
        if output.exists():
            output.unlink()
        report = compare(root, fatigue, profile_path, loads, sn, args)
        write_report(output, report)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(2, "compare_joints: {}\n".format(error))
    for name, result in report["cases"].items():
        print("{}: clamp_min={} N, stress_max={} MPa, damage={:.12g}".format(name, result["minimum_clamp_force_n"], result["maximum_stress_mpa"], result["damage"]["total_damage"]))
    ratio = report["soft_to_stiff_damage_ratio"]
    print("Model damage ratio: {:.12g}".format(ratio) if ratio is not None else "Model damage ratio: undefined (zero reference damage)")


if __name__ == "__main__":
    main()
