#!/usr/bin/env python3
"""Lip-sync clean-up step (config: templates/production.json -> "lipsync_postfix").
Usage: python3 scripts/fix_lipsync.py <lipsync_dir> [--only 03_who]
Writes <dir>/fixed/<vo>.mp4 (audio stream-copied, bit-identical) + fixed/report.json.
 1. frozen duplicate frames  -> 50/50 blend of the neighbours (no RIFE / optical flow)
 2. one-frame jump cuts (splices in the source plate) -> hard punch-in toggle (1.0 <-> punch_scale)
"""
import argparse, json, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def probe(p):
    o = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(p)]).decode().strip().split(",")
    n, d = o[2].split("/")
    return int(o[0]), int(o[1]), float(n) / float(d)


def read_frames(p, w, h):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(p), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def gray_small(frames, w, h, sw=216):
    sh = int(round(h * sw / w))
    out = np.empty((len(frames), sh, sw), np.float32)
    for i, f in enumerate(frames):
        out[i] = np.asarray(Image.fromarray(f).convert("L").resize((sw, sh), Image.BILINEAR), np.float32)
    return out


def analyse(g, cfg):
    d = np.abs(g[1:] - g[:-1]).mean(axis=(1, 2))      # d[i] = diff(frame i, i+1)
    med = float(np.median(d))
    n = len(d)
    frozen, splices = [], []
    for i in range(n):
        lo = d[i - 1] if i > 0 else None
        hi = d[i + 1] if i + 1 < n else None
        nb = [x for x in (lo, hi) if x is not None]
        if d[i] < cfg["frozen_diff_max"] and nb and all(x > cfg["frozen_neighbour_ratio"] * med for x in nb):
            frozen.append(i + 1)                       # frame i+1 duplicates frame i
        if d[i] > max(cfg["splice_min_diff"], cfg["splice_ratio"] * med) and nb and all(x < cfg["splice_neighbour_max"] for x in nb):
            splices.append(i + 1)                      # first frame after the cut
    return frozen, splices, med


def punch(f, s):
    h, w = f.shape[:2]
    cw, ch = w / s, h / s
    x0, y0 = (w - cw) / 2, (h - ch) / 2
    im = Image.fromarray(f).resize((w, h), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
    return np.asarray(im)


def process(src, dst, cfg):
    w, h, fps = probe(src)
    fr = read_frames(src, w, h)
    g = gray_small(fr, w, h)
    frozen, splices, med = analyse(g, cfg)
    out = fr.copy()
    for k in frozen:
        if 0 < k < len(fr) - 1:
            out[k] = ((fr[k - 1].astype(np.uint16) + fr[k + 1]) // 2).astype(np.uint8)
    spans, bounds = [], splices + [len(fr)]
    for j, s0 in enumerate(splices):
        if j % 2 == 0:                                 # alternate: punched, back to 1.0, ...
            spans.append([s0, bounds[j + 1] - 1])
            for i in range(s0, bounds[j + 1]):
                out[i] = punch(out[i], cfg["punch_scale"])
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-r", f"{fps}", "-i", "-", "-i", str(src), "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
                            "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", str(dst)],
                           stdin=subprocess.PIPE)
    enc.stdin.write(out.tobytes()); enc.stdin.close()
    if enc.wait():
        sys.exit(f"ffmpeg failed for {src}")
    return {"frames": len(fr), "median_diff": round(med, 3), "frozen_fixed": frozen, "splices": splices,
            "punch_spans": spans, "punch_scale": cfg["punch_scale"] if spans else 1.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir"); ap.add_argument("--only")
    a = ap.parse_args()
    cfg = json.loads((ROOT / "templates" / "production.json").read_text())["lipsync_postfix"]
    if cfg.get("mode") != "hard_toggle":
        sys.exit("only mode hard_toggle supported")
    d = Path(a.dir)
    d = d if d.is_absolute() else ROOT / d
    (d / "fixed").mkdir(exist_ok=True)
    rep = {}
    for p in sorted(d.glob("*.mp4")):
        if p.stem.endswith("_src") or (a.only and p.stem != a.only):
            continue
        rep[p.stem] = process(p, d / "fixed" / p.name, cfg)
        print(p.stem, rep[p.stem], flush=True)
    (d / "fixed" / "report.json").write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
