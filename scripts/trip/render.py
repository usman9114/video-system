#!/usr/bin/env python3
"""Trip Memories renderer: storyline.json (+ optional hero clips + narration) → 9:16 1080x1920 30 fps film.

Realism-first (templates/production.json → realism_gate):
  * photos of people: smooth real-camera-style moves on the FULL-RES photo (no generative motion);
  * hero scenes: a FastWan clip ONLY if one was picked in <trip>/work/hero_pick.json (passed the gate); otherwise the
    same camera move on the still (fallback, never a borderline AI shot);
  * one grade + light grain across all shots so stills and clips match.
Usage: python3 scripts/trip/render.py trips/greece [--out exports/trip_greece.mp4] [--preview]
"""
import argparse, json, math, re, subprocess, sys, wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
W, H, FPS = 1080, 1920, 30
DISSOLVE = 0.6
TITLE_S = 2.6
FONT_MED = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
FONT_SEMI = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"
ACT_GAIN_DB = {"low": -24.0, "mid": -22.0, "high": -20.0}
DUCK_DB = -31.0


def ease(x: float) -> float:          # gentle ease-in-out, like a slider/gimbal move
    x = min(max(x, 0.0), 1.0)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def redact(im: Image.Image, boxes) -> Image.Image:
    """Blur private details (number plates…) in upright full-res coords, soft-edged so it looks like a real blur."""
    for b in boxes or []:
        reg = im.crop(b).filter(ImageFilter.GaussianBlur(28))
        m = Image.new("L", reg.size, 0)
        ImageDraw.Draw(m).rounded_rectangle((8, 8, reg.width - 8, reg.height - 8), 24, fill=255)
        im.paste(reg, b[:2], m.filter(ImageFilter.GaussianBlur(6)))
    return im


def load_photo(path: Path, max_h: int = 3840, boxes=None, orientation=None) -> Image.Image:
    src = Image.open(path)
    if orientation is not None:         # framing.json override: some phone selfies carry a mirror tag on pixels that
        ex = src.getexif()              # are already un-mirrored (text would read backwards after exif_transpose)
        ex[0x0112] = int(orientation)
        src.info["exif"] = ex.tobytes()
        src = ImageOps.exif_transpose(src) if int(orientation) != 1 else src.copy()
    else:
        src = ImageOps.exif_transpose(src)
    im = redact(src.convert("RGB"), boxes)
    if im.height > max_h:
        im = im.resize((round(im.width * max_h / im.height), max_h), Image.LANCZOS)
    return im


def move_boxes(move: str, iw: int, ih: int, focus_x: float = 0.5, pan=None):
    """Start/end crop boxes (x0,y0,w,h) with 9:16 aspect, derived from the storyline's camera_move text."""
    m = move.lower()
    full_h = min(ih, iw * 16 / 9)
    full_w = full_h * 9 / 16

    def box(scale, cx, cy):
        w, h = full_w / scale, full_h / scale
        x = min(max(cx * iw - w / 2, 0), iw - w)
        y = min(max(cy * ih - h / 2, 0), ih - h)
        return (x, y, w, h)

    lateral = re.search(r"lateral|pan", m)
    if lateral:
        travel = 0.5 if iw / ih > 1.0 else 0.12          # landscape: real pan; portrait: small drift
        a, b = pan if pan else (0.5 - travel / 2, 0.5 + travel / 2)
        if "right-to-left" in m and not pan:
            a, b = b, a
        s = 1.03
        return box(s, a, 0.5), box(s * (1.03 if "push" in m else 1.0), b, 0.5)
    if "tilt-up" in m or "tilt up" in m:
        return box(1.12, focus_x, 0.62), box(1.12, focus_x, 0.40)
    if "pull-out" in m or "pull out" in m:
        return box(1.12, focus_x, 0.45), box(1.0, focus_x, 0.5)
    return box(1.0, focus_x, 0.5), box(1.08, focus_x, 0.5)      # push-in (default)


def lerp_box(b0, b1, k):
    return tuple(a + (b - a) * k for a, b in zip(b0, b1))


def still_frame(im, b):
    x, y, w, h = b
    return im.resize((W, H), Image.BICUBIC, box=(x, y, x + w, y + h), reducing_gap=2.0)


class Clip:
    """FastWan hero clip (already 9:16). Time-stretched by frame blending if the scene is longer than the clip."""
    def __init__(self, path: Path):
        p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
        w, h = map(int, p.stdout.strip().split(","))
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        self.f = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)

    def at(self, k: float) -> Image.Image:                    # k = 0..1 over the clip
        pos = k * (len(self.f) - 1)
        i = int(pos)
        j = min(i + 1, len(self.f) - 1)
        a = pos - i
        fr = self.f[i] if a < 1e-3 else (self.f[i] * (1 - a) + self.f[j] * a).astype(np.uint8)
        return Image.fromarray(fr)


def grade(im: Image.Image, rng) -> np.ndarray:
    a = np.asarray(im).astype(np.float32)
    a = (a - 128) * 1.04 + 128 + np.array([2.5, 1.0, -2.0])      # touch of contrast + warmth, same for all shots
    a += rng.normal(0, 2.2, (H, W, 1))                            # light luma grain unifies stills and clips
    return np.clip(a, 0, 255).astype(np.uint8)


def draw_caption(fr: Image.Image, txt: str, alpha: float, big=False, y=None):
    if not txt or alpha <= 0:
        return fr
    size = 92 if big else 56
    font = ImageFont.truetype(FONT_SEMI if big else FONT_MED, size)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    tw = font.getlength(txt)
    yy = y if y is not None else H - 330
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text(((W - tw) / 2, yy + 3), txt, font=font, fill=(0, 0, 0, int(170 * alpha)))
    sh = sh.filter(ImageFilter.GaussianBlur(6))
    d.text(((W - tw) / 2, yy), txt, font=font, fill=(255, 255, 255, int(255 * alpha)))
    out = fr.convert("RGBA")
    out.alpha_composite(sh)
    out.alpha_composite(lay)
    return out.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trip")
    ap.add_argument("--out")
    ap.add_argument("--preview", action="store_true", help="stills at scene midpoints only")
    a = ap.parse_args()
    trip = ROOT / a.trip
    sl = json.loads((trip / "storyline.json").read_text())
    picks = json.loads((trip / "work/hero_pick.json").read_text()) if (trip / "work/hero_pick.json").exists() else {}
    focus = json.loads((trip / "work/focus.json").read_text()) if (trip / "work/focus.json").exists() else {}
    redactions = json.loads((trip / "redact.json").read_text()) if (trip / "redact.json").exists() else {}
    framing = json.loads((trip / "framing.json").read_text()) if (trip / "framing.json").exists() else {}
    focus.update(framing.get("focus_x", {}))
    vo_dir = trip / "work/vo"
    acts = {x["name"]: x for x in sl["acts"]}

    # ---- timeline -------------------------------------------------------------------------------------------
    scenes = []
    t = 0.0
    for i, sc in enumerate(sl["scenes"]):
        name = Path(sc["photo"]).stem
        dur = sc["seconds"] + (sl["ending"]["seconds"] if i == len(sl["scenes"]) - 1 else 0)
        dis = sc.get("transition_in") == "dissolve" and i > 0
        start = t - (DISSOLVE if dis else 0)
        if i == 1:                                     # title card between cold open and act 1
            start = t + TITLE_S - DISSOLVE
            title = (t - DISSOLVE, start + DISSOLVE)
            scenes[0]["end"] = start + DISSOLVE        # cold open keeps moving (blurred) under the title
            scenes[0]["dur"] = scenes[0]["end"] - scenes[0]["start"]
        vo = next(iter(sorted(vo_dir.glob(f"{i:02d}_{name}_t*.mp3"))), None)
        scenes.append(dict(sc=sc, name=name, start=start, end=start + dur, dur=dur, dissolve=dis or i == 1,
                           vo=vo, act=sc["act"], ending=i == len(sl["scenes"]) - 1))
        t = start + dur
    total = t
    print(f"timeline {total:.2f}s, {len(scenes)} scenes, title {title[0]:.2f}-{title[1]:.2f}s")

    # ---- per-scene sources -----------------------------------------------------------------------------------
    for s in scenes:
        s["im"] = load_photo(ROOT / s["sc"]["photo"], boxes=redactions.get(s["name"]),
                             orientation=framing.get("orientation", {}).get(s["name"]))
        pick = picks.get(s["name"])
        s["clip"] = Clip(ROOT / pick) if (s["sc"].get("hero") and pick) else None
        if s["clip"] is not None:     # hero clip: gentle push on the clip itself (crop in clip space)
            ch, cw = s["clip"].f.shape[1:3]
            s["b0"], s["b1"] = (0, 0, cw, ch), (cw * 0.025, ch * 0.025, cw * 0.95, ch * 0.95)
        else:
            s["b0"], s["b1"] = move_boxes(s["sc"]["camera_move"], *s["im"].size, focus.get(s["name"], 0.5),
                                          framing.get("pan_x", {}).get(s["name"]))
        print(f"  {s['start']:6.2f}-{s['end']:6.2f}  {s['name']:10s} {'HERO' if s['clip'] is not None else 'move'}"
              f"  vo={'y' if s['vo'] else '-'}  {s['sc']['caption']}")

    def scene_frame(s, tt):
        k = (tt - s["start"]) / s["dur"]
        b = lerp_box(s["b0"], s["b1"], ease(k))
        if s["clip"] is not None:
            src = s["clip"].at(min(max(k, 0), 1))
            x, y, w, h = b
            return src.resize((W, H), Image.LANCZOS, box=(x, y, x + w, y + h)).filter(
                ImageFilter.UnsharpMask(radius=1.6, percent=45, threshold=2))
        return still_frame(s["im"], b)

    def caption_alpha(s, tt):
        a0, a1 = s["start"] + (0.9 if s["dissolve"] else 0.5), s["start"] + min(s["sc"]["seconds"], s["dur"]) - 0.35
        return min(max((tt - a0) / 0.4, 0), 1) * min(max((a1 - tt) / 0.3, 0), 1)

    def frame(tt):
        live = [s for s in scenes if s["start"] <= tt < s["end"]] or [scenes[-1]]
        img = None
        for s in live:
            fr = scene_frame(s, tt)
            fr = draw_caption(fr, s["sc"].get("caption"), caption_alpha(s, tt))
            if s["ending"]:
                e0 = s["start"] + s["sc"]["seconds"]
                ea = min(max((tt - e0 - 0.3) / 0.6, 0), 1) * min(max((total - 0.9 - tt) / 0.6, 0), 1)
                fr = draw_caption(fr, sl["ending"]["caption"], ea, y=H // 2 - 40)
            if img is None:
                img = fr
            else:                                   # dissolve: later scene fades in over the earlier one
                k = min(max((tt - s["start"]) / DISSOLVE, 0), 1)
                img = Image.blend(img, fr, ease(k))
        if title[0] <= tt < title[1]:               # title over the softened cold-open frame
            k_in = min(max((tt - title[0]) / DISSOLVE, 0), 1)
            k_out = min(max((title[1] - tt) / DISSOLVE, 0), 1)
            base = scene_frame(scenes[0], tt).filter(ImageFilter.GaussianBlur(14))
            base = Image.blend(base, Image.new("RGB", (W, H), (12, 12, 14)), 0.45)
            base = draw_caption(base, sl["title"], 1.0, big=True, y=H // 2 - 90)
            base = draw_caption(base, sl.get("subtitle", ""), 0.85, y=H // 2 + 30)
            img = Image.blend(img, base, ease(min(k_in, k_out)))
        fade = min(tt / 0.5, 1) * min(max((total - tt) / 1.0, 0), 1)
        if fade < 1:
            img = Image.blend(Image.new("RGB", (W, H)), img, fade)
        return img

    out = ROOT / (a.out or f"exports/trip_{trip.name}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    if a.preview:
        pv = out.with_suffix("")
        pv.mkdir(parents=True, exist_ok=True)
        for s in scenes:
            m = (s["start"] + s["end"]) / 2
            Image.fromarray(grade(frame(m), rng)).save(pv / f"{m:05.2f}_{s['name']}.jpg", quality=88)
        Image.fromarray(grade(frame((title[0] + title[1]) / 2), rng)).save(pv / "title.jpg", quality=88)
        print("previews →", pv)
        return

    # ---- audio: original synthesized bed (royalty-free) with act energy + ducking under narration -----------
    from promo import make_music
    tmp = trip / "work"
    mus = tmp / "music.wav"
    make_music(total, {"segments": []}, mus, card_db=0.0, talk_db=0.0)
    with wave.open(str(mus)) as w:
        sr = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, 2).astype(np.float32)
    n = len(pcm)
    g = np.zeros(n, np.float32)
    for s in scenes:
        i0, i1 = int(s["start"] * sr), int(min(s["end"], total) * sr)
        g[i0:i1] = ACT_GAIN_DB[acts[s["act"]]["music_energy"]]
    vo_track = np.zeros((n, 2), np.float32)
    for s in scenes:
        if not s["vo"]:
            continue
        v = subprocess.run(["ffmpeg", "-v", "error", "-i", str(s["vo"]), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                           capture_output=True, check=True).stdout
        v = np.frombuffer(v, np.float32)
        s["vo_t"] = s["start"] + (0.9 if s["dissolve"] else 0.5)
        i0 = int(s["vo_t"] * sr)
        i1 = min(i0 + len(v), n)
        vo_track[i0:i1] += v[: i1 - i0, None]
        g[max(i0 - int(0.3 * sr), 0):min(i1 + int(0.3 * sr), n)] = DUCK_DB
    k = int(0.4 * sr)
    g = np.convolve(g, np.ones(k) / k, mode="same")
    mix = pcm / 32768 * (10 ** (g / 20))[:, None] * 6.0 + vo_track
    raw = tmp / "mix_raw.wav"
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype("<i2").tobytes())
    aud = tmp / "mix.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
                    str(aud)], check=True)

    # ---- video ---------------------------------------------------------------------------------------------
    nf = int(round(total * FPS))
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", str(aud), "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                          str(out)], stdin=subprocess.PIPE)
    for i in range(nf):
        p.stdin.write(grade(frame(i / FPS), rng).tobytes())
        if i % 150 == 0:
            print(f"  frame {i}/{nf}", flush=True)
    p.stdin.close()
    p.wait()
    print(f"wrote {out} ({nf} frames, {total:.2f}s)")


if __name__ == "__main__":
    main()
