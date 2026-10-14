"""Compare two joint stiffnesses using a load history and a supplied S-N curve.

No Python dependencies. Requires the sibling fatigue-spectrum project and moon.
"""
import argparse
import json
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


def write_report(output, report):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, prefix="comparison-", suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(str(temporary), str(output))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def compare(root, fatigue, profile_path, loads, sn, args):
    bolt_cli, fatigue_cli = executable(root), executable(fatigue)
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    cases = {}
    with tempfile.TemporaryDirectory(prefix="joint-comparison-", dir=root / "_build") as directory:
        working = Path(directory)
        for name, stiffness in (("stiff_joint", args.stiff_stiffness), ("soft_joint", args.soft_stiffness)):
            current = dict(profile, joint_stiffness_n_per_mm=stiffness)
            current_path = working / (name + ".json")
            stress_path = working / (name + "-stress.csv")
            history_path = working / (name + "-history.json")
            fatigue_path = working / (name + "-fatigue.json")
            current_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
            run(bolt_cli, root, "history", current_path, loads, "--stress", stress_path, "--json", history_path)
            run(fatigue_cli, fatigue, "analyze", stress_path, "--sn", sn, "--bin-width", args.bin_width, "--json", fatigue_path)
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
        "data_source": "samples/loads.csv: synthetic illustrative loads, not measured equipment data" if args.loads is None else str(loads),
        "sn_source": "fatigue-spectrum/samples/sn.json: illustrative N=1e10/amplitude^4, not certified material data" if args.sn is None else str(sn),
        "sn_points": json.loads(sn.read_text(encoding="utf-8-sig")),
        "mean_stress_model": "none",
        "interpretation": "Compare the linear joint response and uncorrected Miner model only; this is not a measured fatigue-life result.",
        "cases": cases,
        "soft_to_stiff_damage_ratio": ratio,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fatigue", type=Path, help="fatigue-spectrum project directory; default is the sibling project")
    parser.add_argument("--profile", type=Path, help="joint profile JSON; default samples/joint.json")
    parser.add_argument("--loads", type=Path, help="time_s,force_n CSV; default synthetic samples/loads.csv")
    parser.add_argument("--sn", type=Path, help="S-N JSON; default synthetic fatigue-spectrum/samples/sn.json")
    parser.add_argument("--stiff-stiffness", type=positive, default=800000, help="stiffer joint stiffness in N/mm")
    parser.add_argument("--soft-stiffness", type=positive, default=300000, help="softer joint stiffness in N/mm")
    parser.add_argument("--bin-width", type=positive, default=10, help="display range-bin width in MPa")
    parser.add_argument("--output", type=Path, default=Path("samples/comparison.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fatigue = args.fatigue.resolve() if args.fatigue else root.parent / "fatigue-spectrum"
    if args.stiff_stiffness <= args.soft_stiffness:
        parser.error("--stiff-stiffness must exceed --soft-stiffness")
    profile_path = args.profile.resolve() if args.profile else root / "samples/joint.json"
    loads = args.loads.resolve() if args.loads else root / "samples/loads.csv"
    sn = args.sn.resolve() if args.sn else fatigue / "samples/sn.json"
    output = args.output if args.output.is_absolute() else root / args.output
    for input_path in (profile_path, loads, sn):
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
