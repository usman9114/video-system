#!/usr/bin/env python3
"""Add breathing room to TTS lines in the edit (no new credits): insert silence after given words (Whisper word timings)
and optionally slow a line with atempo (pitch kept). Config: <trip>/vo_edit.json
{"lines": {"<line>": {"src": mp3, "words": "<whisper words.json>", "pause_after": {"down": 0.35}, "atempo": 0.96, "out": mp3}}}"""
import json, subprocess, sys
from pathlib import Path

cfg = json.loads(Path(sys.argv[1]).read_text())
for name, c in cfg["lines"].items():
    words = [w for s in json.loads(Path(c["words"]).read_text())["segments"] for w in s["words"]]
    cuts = []
    for key, sec in c.get("pause_after", {}).items():
        w = next(w for w in words if w["w"].strip().strip(".,!?").lower() == key.lower())
        nxt = words[words.index(w) + 1]["s"] if words.index(w) + 1 < len(words) else w["e"]
        cuts.append(((w["e"] + nxt) / 2, sec))         # cut in the middle of the existing gap
    cuts.sort()
    parts, t0, f = [], 0.0, []
    for i, (t, sec) in enumerate(cuts):
        f.append(f"[0:a]atrim={t0}:{t},asetpts=PTS-STARTPTS[a{i}]")
        f.append(f"aevalsrc=0:d={sec}:s=44100:c=stereo[s{i}]")
        parts += [f"[a{i}]", f"[s{i}]"]
        t0 = t
    f.append(f"[0:a]atrim={t0},asetpts=PTS-STARTPTS[last]")
    parts.append("[last]")
    chain = ";".join(f) + ";" + "".join(parts) + f"concat=n={len(parts)}:v=0:a=1[c]"
    tempo = c.get("atempo", 1.0)
    chain += f";[c]atempo={tempo}[o]" if tempo != 1.0 else ";[c]anull[o]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", c["src"], "-filter_complex", chain, "-map", "[o]",
                    "-ac", "2", "-ar", "44100", "-b:a", "192k", c["out"]], check=True)
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", c["out"]],
                       capture_output=True, text=True).stdout.strip()
    print(f"{name}: +{sum(s for _, s in cuts):.2f}s silence, atempo {tempo} -> {d}s  {c['out']}")
