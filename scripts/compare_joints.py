"""Run the paired tools on a synthetic load history and two joint stiffnesses.

No Python dependencies. Requires the sibling fatigue-spectrum project and moon.
"""
import argparse
import json
import subprocess
from pathlib import Path


def executable(root):
    subprocess.run(["moon", "build", "--target", "native"], cwd=root, check=True)
    base = root / "_build/native/debug/build/cmd/main/main"
    for binary in (base.with_suffix(".exe"), base):
        if binary.is_file():
            return binary
    raise FileNotFoundError("moon build produced no native CLI at " + str(base))


def run(binary, root, *args):
    subprocess.run([str(binary)] + [str(arg) for arg in args], cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fatigue", type=Path, help="fatigue-spectrum project directory; default is the sibling project")
    parser.add_argument("--output", type=Path, default=Path("samples/comparison.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    fatigue = args.fatigue.resolve() if args.fatigue else root.parent / "fatigue-spectrum"
    bolt_cli, fatigue_cli = executable(root), executable(fatigue)
    working = root / "_build/joint-comparison"
    working.mkdir(exist_ok=True)
    profile = json.loads((root / "samples/joint.json").read_text(encoding="utf-8"))
    loads = root / "samples/loads.csv"
    sn = fatigue / "samples/sn.json"
    cases = {}
    for name, stiffness in (("stiff_joint", 800000), ("soft_joint", 300000)):
        current = dict(profile, joint_stiffness_n_per_mm=stiffness)
        current_path = working / (name + ".json")
        stress_path = working / (name + "-stress.csv")
        history_path = working / (name + "-history.json")
        fatigue_path = working / (name + "-fatigue.json")
        current_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        run(bolt_cli, root, "history", current_path, loads, "--stress", stress_path, "--json", history_path)
        run(fatigue_cli, fatigue, "analyze", stress_path, "--sn", sn, "--bin-width", "10", "--json", fatigue_path)
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
    report = {
        "command": "python scripts/compare_joints.py --fatigue ../fatigue-spectrum",
        "data_source": "samples/loads.csv: synthetic illustrative loads, not measured equipment data",
        "sn_source": "fatigue-spectrum/samples/sn.json: illustrative N=1e10/amplitude^4, not certified material data",
        "sn_points": json.loads(sn.read_text(encoding="utf-8")),
        "mean_stress_model": "none",
        "interpretation": "Compare the linear joint response and uncorrected Miner model only; this is not a measured fatigue-life result.",
        "cases": cases,
        "soft_to_stiff_damage_ratio": soft_damage / stiff_damage,
    }
    output = args.output if args.output.is_absolute() else root / args.output
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, result in cases.items():
        print("{}: clamp_min={} N, stress_max={} MPa, damage={:.12g}".format(name, result["minimum_clamp_force_n"], result["maximum_stress_mpa"], result["damage"]["total_damage"]))
    print("Model damage ratio: {:.12g}".format(report["soft_to_stiff_damage_ratio"]))


if __name__ == "__main__":
    main()
