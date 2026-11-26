#!/usr/bin/env python3
"""Build a clean master from the WFP-branded source:
  - cut before the end card (trim_end)
  - remove the top-right logo (ffmpeg delogo)
  - replace the burned-in subtitles: frosted, darkened panel over the old subtitle area + new captions
    generated from Whisper word timestamps (assets/transcripts/*.words.json)
  - loudness-normalise audio (two-pass EBU R128) and gently high-pass it
  - encode at high quality (x264 veryslow, CRF 14)

Usage:
  python3 scripts/clean_master.py SOURCE.mp4 TRANSCRIPT.words.json OUT.mp4 [--config templates/clean_master.json]
      [--preview SECONDS]   # quick render of the first N seconds (fast preset)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def probe(path: str) -> tuple[int, int]:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height", "-of", "csv=p=0", path], text=True)
    w, h = out.strip().split(",")
    return int(w), int(h)


def ass_time(t: float) -> str:
    t = max(t, 0)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _join(tokens: list[str]) -> str:
    out = ""
    for t in tokens:
        out += t if (not out or t.startswith(("-", ",", ".", "'"))) else " " + t
    return out


def _balance(text: str, max_chars: int) -> str:
    """Split one caption into 1-2 lines of similar length (no orphan words)."""
    if len(text) <= max_chars:
        return text
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    best = min(spaces, key=lambda i: max(i, len(text) - i - 1))
    return text[:best] + "\\N" + text[best + 1:]


def build_cards(transcript: dict, max_chars: int, max_lines: int, trim_end: float) -> list[tuple[float, float, str]]:
    """Group words into caption cards: break at sentence ends, at commas once a card is long enough, and
    before a card would exceed max_lines * max_chars. Each card is then line-balanced."""
    words = [w for s in transcript["segments"] for w in s["words"] if w["s"] < trim_end]
    limit = max_chars * max_lines
    cards, cur = [], []
    for i, w in enumerate(words):
        tok = w["w"].strip()
        if cur and len(_join([x["w"].strip() for x in cur] + [tok])) > limit:
            cards.append(cur)
            cur = []
        cur.append(w)
        text = _join([x["w"].strip() for x in cur])
        if tok.endswith((".", "?", "!")) or (tok.endswith(",") and len(text) > max_chars * 0.9):
            cards.append(cur)
            cur = []
    if cur:
        cards.append(cur)
    res = []
    for j, c in enumerate(cards):
        start = c[0]["s"]
        nxt = cards[j + 1][0]["s"] if j + 1 < len(cards) else min(c[-1]["e"] + 0.4, trim_end)
        end = nxt if nxt - c[-1]["e"] < 0.6 else c[-1]["e"] + 0.25
        res.append((start, min(end, trim_end), _balance(_join([x["w"].strip() for x in c]), max_chars)))
    return res


def write_ass(cards, cfg, size, path: Path) -> None:
    c, p = cfg["captions"], cfg["subtitle_panel"]
    W, H = size
    bx, by = cfg["base_size"]
    sx, sy = W / bx, H / by
    cx, cy = (p["x"] + p["w"] / 2) * sx, (p["y"] + p["h"] / 2) * sy
    fs = round(c["size"] * sy)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{c['font']},{fs},{c['color']},&H000000FF,{c['outline_color']},&H00000000,0,0,0,0,100,100,0,0,1,{c['outline']},{c['shadow']},5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = [f"Dialogue: 0,{ass_time(a)},{ass_time(b)},Cap,,0,0,0,,{{\\pos({cx:.0f},{cy:.0f})\\fad(80,80)}}{t}"
          for a, b, t in cards]
    path.write_text(head + "\n".join(ev) + "\n")


def panel_mask(cfg, size, path: Path) -> tuple[int, int, int, int]:
    p = cfg["subtitle_panel"]
    bx, by = cfg["base_size"]
    sx, sy = size[0] / bx, size[1] / by
    x, y, w, h = [round(v) for v in (p["x"] * sx, p["y"] * sy, p["w"] * sx, p["h"] * sy)]
    x, y, w, h = x - x % 2, y - y % 2, w - w % 2, h - h % 2
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=round(p["radius"] * sx), fill=255)
    m.save(path)
    return x, y, w, h


def loudnorm_params(src: str, end: float, a: dict) -> dict:
    af = f"highpass=f={a['highpass_hz']},loudnorm=I={a['lufs']}:TP={a['true_peak']}:LRA={a['lra']}:print_format=json"
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-t", str(end), "-i", src, "-af", af, "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, re.S).group(0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("transcript")
    ap.add_argument("out")
    ap.add_argument("--config", default=str(ROOT / "templates" / "clean_master.json"))
    ap.add_argument("--preview", type=float, default=0)
    ap.add_argument("--logo-patch", help="inpainted crop video from jobs/inpaint-logo (replaces delogo)")
    a = ap.parse_args()

    cfg = json.loads(Path(a.config).read_text())
    W, H = probe(a.source)
    bx, by = cfg["base_size"]
    sx, sy = W / bx, H / by
    end = a.preview or cfg["trim_end"]
    tmp = Path(tempfile.mkdtemp(prefix="clean_"))

    cards = build_cards(json.loads(Path(a.transcript).read_text()), cfg["captions"]["max_chars_per_line"],
                        cfg["captions"]["max_lines"], cfg["trim_end"])
    ass = tmp / "captions.ass"
    write_ass(cards, cfg, (W, H), ass)
    (Path(a.out).with_suffix(".captions.ass")).write_text(ass.read_text())
    mask = tmp / "mask.png"
    px, py, pw, ph = panel_mask(cfg, (W, H), mask)
    lg = cfg["logo_box"]
    lx, ly, lw, lh = (round(v) for v in (lg["x"] * sx, lg["y"] * sy, lg["w"] * sx, lg["h"] * sy))
    pn = cfg["subtitle_panel"]

    if a.logo_patch:
        pc = cfg["logo_patch_crop"]
        cx, cy = round(pc["x"] * sx), round(pc["y"] * sy)
        feather = tmp / "patch_mask.png"
        pm = Image.new("L", (round(pc["w"] * sx), round(pc["h"] * sy)), 0)
        ImageDraw.Draw(pm).rectangle([lx - cx - 3, ly - cy - 3, lx - cx + lw + 3, ly - cy + lh + 3], fill=255)
        from PIL import ImageFilter
        pm.filter(ImageFilter.GaussianBlur(4)).save(feather)
        logo = (f"[2:v]format=rgba[pt];[3:v]format=gray,scale={pm.width}:{pm.height}[pmk];[pt][pmk]alphamerge[patch];"
                f"[0:v][patch]overlay={cx}:{cy}:format=auto:shortest=1,split[base][src];")
        extra = ["-i", a.logo_patch, "-loop", "1", "-i", str(feather)]
    else:
        logo = f"[0:v]delogo=x={lx}:y={ly}:w={lw}:h={lh},split[base][src];"
        extra = []
    vf = (
        logo +
        f"[src]crop={pw}:{ph}:{px}:{py},gblur=sigma={pn['blur_sigma'] * sx},"
        f"eq=brightness=-{pn['darken'] * 0.5}:saturation=0.8,format=yuva420p[blur];"
        f"[1:v]format=gray,scale={pw}:{ph}[m];[blur][m]alphamerge[panel];"
        f"[base][panel]overlay={px}:{py}:format=auto,"
        f"ass='{ass}':fontsdir=/usr/share/fonts,format=yuv420p[v]"
    )
    au = cfg["audio"]
    if a.preview:
        af = f"highpass=f={au['highpass_hz']},loudnorm=I={au['lufs']}:TP={au['true_peak']}:LRA={au['lra']}"
        enc = ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]
    else:
        ln = loudnorm_params(a.source, end, au)
        af = (f"highpass=f={au['highpass_hz']},loudnorm=I={au['lufs']}:TP={au['true_peak']}:LRA={au['lra']}:"
              f"measured_I={ln['input_i']}:measured_TP={ln['input_tp']}:measured_LRA={ln['input_lra']}:"
              f"measured_thresh={ln['input_thresh']}:offset={ln['target_offset']}:linear=true")
        e = cfg["encode"]
        enc = ["-c:v", "libx264", "-preset", e["preset"], "-crf", str(e["crf"]), "-profile:v", "high",
               "-tune", "film", "-g", "60", "-bf", "3"]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-t", str(end), "-i", a.source,
           "-loop", "1", "-i", str(mask), *extra, "-filter_complex", vf, "-map", "[v]", "-map", "0:a",
           "-af", af + ",aresample=48000", *enc, "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-b:a", cfg["encode"]["audio_bitrate"], "-shortest", "-movflags", "+faststart", a.out]
    subprocess.run(cmd, check=True)
    print(f"wrote {a.out}  ({len(cards)} caption cards, {W}x{H})")


if __name__ == "__main__":
    sys.exit(main())
