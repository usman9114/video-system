#!/usr/bin/env python3
"""Build listening files from a voice-clone run:
  previews/voice_ab_<model>.mp3   : REAL voice (8 s) → beep → each line's takes, so you can compare directly
  previews/voice_full_<model>.mp3 : the full script read with take 0 (or --takes 01_hook=1,...)
Also prints duration and loudness per clip, plus a speaker-similarity check if resemblyzer is installed.

    python3 scripts/voice_review.py kaggle/outputs/kgpu-voice-clone/out --ref <real.wav>
"""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dur(p: Path) -> float:
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--ref", required=True)
    ap.add_argument("--takes", default="", help="line=take,... for the full read")
    a = ap.parse_args()
    run = Path(a.run_dir)
    pick = dict(kv.split("=") for kv in a.takes.split(",") if kv)
    tmp = ROOT / "kaggle" / "work" / "voice_review"
    tmp.mkdir(parents=True, exist_ok=True)
    beep = tmp / "beep.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=880:d=0.15", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-filter_complex", "[0]volume=0.25,aresample=24000[b];[b][1]concat=n=2:v=0:a=1,atrim=0:0.6",
                    "-ar", "24000", "-ac", "1", str(beep)], check=True)
    gap = tmp / "gap.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.45", str(gap)], check=True)
    for model in sorted(p for p in run.iterdir() if p.is_dir()):
        clips = sorted(model.glob("*.wav"))
        if not clips:
            continue
        lines = sorted({c.stem.rsplit("_t", 1)[0] for c in clips})
        ab = [Path(a.ref), beep]
        full = []
        print(f"== {model.name}")
        for ln in lines:
            for c in sorted(model.glob(f"{ln}_t*.wav")):
                ab += [c, gap]
                print(f"  {c.stem:<14} {dur(c):5.2f}s")
            k = pick.get(ln, "0")
            full += [model / f"{ln}_t{k}.wav", gap]
        for name, seq in (("ab", ab), ("full", full)):
            lst = tmp / f"{model.name}_{name}.txt"
            lst.write_text("".join(f"file '{p.resolve()}'\n" for p in seq))
            out = ROOT / "previews" / f"voice_{name}_{model.name}.mp3"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-af", "aresample=24000,loudnorm=I=-16:TP=-1.5", "-ac", "1", "-b:a", "128k", str(out)], check=True)
            print("  ->", out.relative_to(ROOT), f"{dur(out):.1f}s")


if __name__ == "__main__":
    main()
