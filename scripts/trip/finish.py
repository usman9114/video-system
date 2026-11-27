#!/usr/bin/env python3
"""FFmpeg finishing pass for Trip Memories (open-source only, $0): film-look grade + pro audio ducking.

Video: lut3d at 40% strength (a gentle film LUT generated here: soft S-curve, lifted blacks, cool shadows / warm highlights,
       -8% saturation in the extremes) + subtle vignette + light sharpening for phone viewing.
Audio: music ducked under the voice with sidechaincompress (smooth, like an editor's ducking) instead of gain steps,
       a high-pass + presence lift on the voice, then EBU R128 loudnorm to -14 LUFS / -1.5 dBTP (social platforms).
Usage: python3 scripts/trip/finish.py <render.mp4> <trip_dir> <out.mp4>
       (the renderer writes <trip>/work/stem_music.wav and stem_vo.wav)
"""
import subprocess
import sys
from pathlib import Path

import numpy as np


def film_lut(path: Path, n: int = 33) -> Path:
    g = np.linspace(0, 1, n)
    b, gg, r = np.meshgrid(g, g, g, indexing="ij")          # .cube order: R fastest, then G, then B
    rgb = np.stack([r, gg, b], -1)
    luma = (rgb @ np.array([0.2126, 0.7152, 0.0722]))[..., None]
    s = 0.5 + (rgb - 0.5) * 1.06                             # gentle contrast
    s = s + 0.05 * np.sin(2 * np.pi * (rgb - 0.5)) * -0.25   # soft S toe/shoulder
    s = 0.03 + s * 0.97                                       # lifted blacks (film base)
    shadow, high = np.clip(1 - luma * 2.2, 0, 1), np.clip(luma * 1.8 - 0.8, 0, 1)
    s = s + shadow * np.array([-0.012, 0.004, 0.018]) + high * np.array([0.018, 0.006, -0.014])
    sat = 1 - 0.08 * (shadow + high)                          # calmer saturation at the extremes
    s = luma + (s - luma) * sat
    s = np.clip(s, 0, 1)
    with open(path, "w") as f:
        f.write(f'TITLE "trip film"\nLUT_3D_SIZE {n}\n')
        for v in s.reshape(-1, 3):
            f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
    return path


def main():
    src, trip, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    work = trip / "work"
    lut = film_lut(work / "film.cube")
    # v2 critic: LUT at ~40% strength, saturation ~1.0, vignette 5-8%, mild unsharp
    vf = (f"split[o][g];[g]lut3d=file={lut}:interp=tetrahedral[l];[o][l]blend=all_mode=normal:all_opacity=0.4,"
          "eq=saturation=0.98,vignette=angle=PI/9:mode=forward,unsharp=3:3:0.3:3:3:0.0,format=yuv420p")
    af = ("[2:a]highpass=f=80,equalizer=f=3200:t=q:w=1.2:g=2,asplit=2[vo][key];"
          "[1:a][key]sidechaincompress=threshold=0.05:ratio=3:attack=150:release=500:makeup=1[duck];"
          "[duck][vo]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,alimiter=limit=0.79:level=false[a]")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src), "-i", str(work / "stem_music.wav"), "-i",
           str(work / "stem_vo.wav"), "-filter_complex", f"[0:v]{vf}[v];{af}", "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-r", "30", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-shortest", str(out)]
    subprocess.run(cmd, check=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
