#!/usr/bin/env python3
"""Build lip-synced face clips for every face segment of a video spec, using templates/production.json ONLY.

    python3 scripts/make_faces.py scripts/videos/01_n8n_v6.json [--only 04_more,06_cta] [--dry-run]

For each face segment with "video": "auto": cut a continuous, NON-reversed stretch of the clean plate
(footage.clean_ranges_s) at least as long as the VO line + margin, spreading lines across the ranges so the same
moment isn't reused back to back; send it with the VO to the lip-sync engine in production.lipsync (TBDub teacher on
Modal); save to kaggle/work/lipsync/<spec id>/<vo>.mp4. Jobs run in parallel. Costs are logged by lane.modal_lipsync.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dur(p: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))


def plan(spec: dict, prod: dict, only: set[str] | None) -> list[dict]:
    """Best-fit footage allocation: longest lines first into UNUSED clean stretches; if none fits, reuse a stretch at
    the start farthest from every start already used (so no two lines open on the same frames). Never reverses."""
    fo = prod["footage"]
    if prod["rules"]["allow_reversed_footage"]["value"]:
        sys.exit("config allows reversed footage; this tool never reverses")
    ranges = [tuple(r) for r in fo["clean_ranges_s"]]
    free = [list(r) for r in ranges]               # unused tail per range
    used_starts: list[float] = []
    lines = []
    for seg in spec["segments"]:
        if seg["type"] == "face" and seg.get("video", "auto") == "auto" and (not only or seg["vo"] in only):
            lines.append((seg["vo"], dur(ROOT / spec["vo_dir"] / f"{seg['vo']}.mp3") + fo["min_margin_s"]))
    jobs = {}
    for vo, need in sorted(lines, key=lambda x: -x[1]):
        fits = [i for i, (a, b) in enumerate(free) if b - a >= need]
        if fits:
            i = min(fits, key=lambda j: (free[j][1] - free[j][0]) - need)      # tightest fit keeps big gaps free
            start = free[i][0]
            free[i][0] = round(start + need, 2)
        else:
            cands = []
            for i, (a, b) in enumerate(ranges):
                if b - a < need:
                    continue
                for k in range(0, 21):
                    st = a + (b - need - a) * k / 20
                    cands.append((min([abs(st - u) for u in used_starts] or [99]), i, st))
            if not cands:
                sys.exit(f"no clean footage range is long enough for {vo} ({need:.1f}s)")
            _, i, start = max(cands)
        used_starts.append(start)
        jobs[vo] = {"vo": vo, "start": round(start, 2), "end": round(start + need, 2), "range": i}
    return [jobs[vo] for vo, _ in lines]


def run(job: dict, spec: dict, prod: dict) -> str:
    fo, ls = prod["footage"], prod["lipsync"]
    out_dir = ROOT / "kaggle" / "work" / "lipsync" / spec["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    src = out_dir / f"{job['vo']}_src.mp4"
    x, y, w, h = fo["source_crop"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(job["start"]), "-i", str(ROOT / fo["plate"]),
                    "-t", str(job["end"] - job["start"]), "-an", "-vf", f"crop={w}:{h}:{x}:{y},fps={fo['fps']},format=yuv420p",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "12", str(src)], check=True)
    out = out_dir / f"{job['vo']}.mp4"
    r = subprocess.run([sys.executable, "-m", "lane.modal_lipsync", "lipsync", "--video", str(src),
                        "--audio", str(ROOT / spec["vo_dir"] / f"{job['vo']}.mp3"), "--out", str(out), "--mode", ls["mode"]],
                       cwd=ROOT, capture_output=True, text=True)
    last = [l for l in r.stdout.splitlines() if not l.strip().startswith("[")][-1:] or [r.stderr[-300:]]
    return f"{job['vo']} ({job['start']}-{job['end']}s): {last[0]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--only")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    spec = json.loads((ROOT / a.spec).read_text())
    prod = json.loads((ROOT / "templates" / "production.json").read_text())
    if prod["lipsync"]["engine"] != "tbdub" or prod["lipsync"]["where"] != "modal":
        sys.exit("make_faces.py currently implements lipsync engine=tbdub on modal only")
    jobs = plan(spec, prod, set(a.only.split(",")) if a.only else None)
    for j in jobs:
        print(f"plan {j['vo']}: footage {j['start']}-{j['end']}s (range {j['range']})")
    if a.dry_run:
        return
    with ThreadPoolExecutor(max_workers=6) as ex:
        for line in ex.map(lambda j: run(j, spec, prod), jobs):
            print(line, flush=True)


if __name__ == "__main__":
    main()
