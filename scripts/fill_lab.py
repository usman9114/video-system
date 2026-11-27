#!/usr/bin/env python3
"""Fill lab: run pre-render gap-filling passes (RIFE interpolation, Real-ESRGAN upscale) on Kaggle's 2x T4.
Settings: templates/production.json -> fill_lab (owner rule: config only).

    python3 scripts/fill_lab.py kaggle/work/lipsync/01_n8n_automation_v6 --preset lipsync
    python3 scripts/fill_lab.py broll/wan/hero_a.mp4 broll/wan/hero_b.mp4 --preset hero_clip
    python3 scripts/fill_lab.py <same inputs> --preset lipsync --collect     # just copy the last run's outputs

Outputs go to <input dir>_filled/ (same file names), never over the originals, plus fill.json with timings and
per-GPU utilisation. Lip-sync clips must pass the SyncNet before/after gate before an edit points at them.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KOUT = ROOT / "kaggle" / "outputs" / "kgpu-fill-lab" / "out"


def frames(p: Path) -> int:
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.strip()
    return int(o) if o.isdigit() else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--preset", required=True)
    ap.add_argument("--collect", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((ROOT / "templates" / "production.json").read_text())["fill_lab"]
    if not cfg["enabled"]:
        sys.exit("fill_lab disabled in templates/production.json")
    pre = cfg["presets"][a.preset]
    files = []
    for i in map(Path, a.inputs):
        files += sorted(i.glob("*.mp4")) if i.is_dir() else [i]
    if len({f.name for f in files}) != len(files):
        sys.exit("fill-lab: clip names must be unique")
    man = {"interpolate": cfg["interpolate"], "upscale": cfg["upscale"], "encode": cfg["encode"],
           "clips": [{"name": f.name, "frames": frames(f), **{k: v for k, v in pre.items() if k != "why"}} for f in files]}
    first = Path(a.inputs[0])
    dest = (first if first.is_dir() else first.parent).with_name((first if first.is_dir() else first.parent).name + "_filled")

    if not a.collect:
        bundle = ROOT / "kaggle" / "build" / "fill-lab-input"
        shutil.rmtree(bundle, ignore_errors=True)
        bundle.mkdir(parents=True)
        for f in files:
            shutil.copy2(f, bundle / f.name)
        (bundle / "manifest.json").write_text(json.dumps(man, indent=1))
        subprocess.run([str(ROOT / "bin" / "kgpu"), "run", str(ROOT / "jobs" / "fill-lab"), "--input", str(bundle),
                        "--timeout-min", str(cfg["timeout_min"])], check=True)

    dest.mkdir(parents=True, exist_ok=True)
    for f in files:
        if (KOUT / f.name).exists():
            shutil.copy2(KOUT / f.name, dest / f.name)
    shutil.copy2(KOUT / "fill.json", dest / "fill.json")
    res = json.loads((KOUT / "fill.json").read_text())
    for n, c in res["clips"].items():
        print(f"{n}: {c['in']} -> {c['out']} ({' + '.join(c['ops'])}) {c['seconds']} s on gpu{c['gpu']}")
    print("gpu util:", res["gpu_util"], "| total", res["total_s"], "s | missing", res["missing"], "->", dest)


if __name__ == "__main__":
    main()
