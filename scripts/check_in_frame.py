#!/usr/bin/env python3
"""Rule check: whatever the narrator names must be visible in frame while he says it
(templates/production.json → rules.narration_subject_in_frame, LESSONS #87).

  python3 scripts/check_in_frame.py <video.mp4> --line <align.json>@<offset_s> [--line ...] [--out report.json]

Each --line is an ElevenLabs alignment file (keys w/s/e per word) plus the time in the video where that line starts.
Lines are split into phrases at punctuation; for each phrase a frame is grabbed at its start and end and sent with the
phrase text to ChatGPT vision (lane.chatgpt, $0). Output: per phrase subject / visible yes|partly|no|offscreen / fix.
Exit code 1 if any phrase is "no" (so a render script can stop and fix before delivery).
"""
import argparse, json, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lane import chatgpt  # noqa: E402

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["phrases"],
    "properties": {"phrases": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["idx", "subject", "visible", "why", "fix"],
        "properties": {"idx": {"type": "integer"}, "subject": {"type": "string"},
                       "visible": {"type": "string", "enum": ["yes", "partly", "no", "offscreen_phrased", "none_named"]},
                       "why": {"type": "string"}, "fix": {"type": "string"}}}}}}


def phrases(align: Path, offset: float):
    words = json.loads(align.read_text())["words"]
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.,;:!?]$", w["w"]):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return [{"text": " ".join(x["w"] for x in p), "t0": p[0]["s"] + offset, "t1": p[-1]["e"] + offset} for p in out]


def grab(video: Path, t: float, path: Path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(t, 0):.2f}", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=360:-2", str(path)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--line", action="append", required=True, help="align.json@offset_seconds")
    ap.add_argument("--out")
    a = ap.parse_args()
    video = Path(a.video)
    ph = []
    for spec in a.line:
        f, _, off = spec.rpartition("@")
        ph += phrases(Path(f), float(off))
    with tempfile.TemporaryDirectory() as tmp:
        imgs, lines = [], []
        for i, p in enumerate(ph):
            for tag, t in (("a", p["t0"] + 0.1), ("b", p["t1"] - 0.1)):
                im = Path(tmp) / f"p{i:02d}{tag}.jpg"
                grab(video, t, im)
                imgs.append(str(im))
            lines.append(f'{i}: "{p["text"]}" ({p["t0"]:.1f}-{p["t1"]:.1f} s) -> images p{i:02d}a (start), p{i:02d}b (end)')
        sp = Path(tmp) / "schema.json"
        sp.write_text(json.dumps(SCHEMA))
        prompt = ("Rule: whatever the narrator names must be clearly visible in frame while he says it; places that are not "
                  "shown must be phrased as off-screen ('down the hill', 'in the museum'). Images are attached in order, two per "
                  "phrase (start, end). For each phrase name the subject he refers to, judge visibility "
                  "(yes / partly / no / offscreen_phrased / none_named), say why in <15 words and give one concrete fix "
                  "(reorder sentence, reword, camera move timing, crop, different shot) or 'none'.\n" + "\n".join(lines))
        r = chatgpt.ask(prompt, images=imgs, schema=str(sp), timeout=900)
    res = r["data"]["phrases"]
    for p, x in zip(ph, sorted(res, key=lambda d: d["idx"])):
        x.update(text=p["text"], t0=round(p["t0"], 2), t1=round(p["t1"], 2))
        print(f'{x["t0"]:5.1f}-{x["t1"]:5.1f}s  {x["visible"]:<17} {x["text"]}  | {x["fix"]}')
    bad = [x for x in res if x["visible"] == "no"]
    if a.out:
        Path(a.out).write_text(json.dumps({"video": str(video), "phrases": res, "pass": not bad}, indent=1))
    print("PASS" if not bad else f"FAIL: {len(bad)} phrase(s) name something not in frame")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
