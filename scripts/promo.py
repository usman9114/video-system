#!/usr/bin/env python3
"""Render a promo video from a JSON spec (scripts/videos/*.json) + design template (templates/promo_*.json).

    python3 scripts/promo.py scripts/videos/01_n8n.json [--final] [--still 3.0,12.5] [--source SRC --logo-patch MKV]

Segment types: talk (real footage + word-highlight captions), workflow (animated automation graphic),
list (staggered checklist), end (CTA card with a real photo of the owner).
Footage comes from a "plate" (source with the logo inpainted, no captions); it's built once if missing.
No new dependencies: Pillow + numpy + ffmpeg.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# ---------- helpers ----------
def hexc(h: str, a: int = 255) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def clamp01(x: float) -> float:
    return min(max(x, 0.0), 1.0)


class Fonts:
    def __init__(self, paths: dict):
        self.paths, self.cache = paths, {}

    def __call__(self, kind: str, size: int):
        k = (kind, size)
        if k not in self.cache:
            self.cache[k] = ImageFont.truetype(self.paths[kind], size)
        return self.cache[k]


def text_w(font, s: str) -> float:
    return font.getlength(s)


# ---------- plate ----------
def make_plate(source: str, patch: str, cfg_path: Path, out: Path) -> None:
    cfg = json.loads(cfg_path.read_text())
    w, h = map(int, subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                              "stream=width,height", "-of", "csv=p=0:s=x", source], text=True).strip().split("x"))
    bx, by = cfg["base_size"]
    sx, sy = w / bx, h / by
    pc, lg = cfg["logo_patch_crop"], cfg["logo_box"]
    cx, cy = round(pc["x"] * sx), round(pc["y"] * sy)
    lx, ly, lw, lh = (round(v) for v in (lg["x"] * sx, lg["y"] * sy, lg["w"] * sx, lg["h"] * sy))
    pw, ph = round(pc["w"] * sx), round(pc["h"] * sy)
    m = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(m).rectangle([lx - cx - 3, ly - cy - 3, lx - cx + lw + 3, ly - cy + lh + 3], fill=255)
    tmp = Path(tempfile.mkdtemp()) / "feather.png"
    m.filter(ImageFilter.GaussianBlur(4)).save(tmp)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", source, "-i", patch, "-loop", "1", "-i", str(tmp),
                    "-filter_complex", f"[1:v]format=rgba[p];[2:v]format=gray,scale={pw}:{ph}[k];[p][k]alphamerge[pa];"
                    f"[0:v][pa]overlay={cx}:{cy}:format=auto:eof_action=pass[v]",
                    "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "slow", "-crf", "8", "-pix_fmt", "yuv444p",
                    "-c:a", "copy", str(out)], check=True)


def read_frames(plate: str, t0: float, t1: float, crop: list, fps: int):
    x, y, w, h = crop
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", plate, "-t", f"{t1 - t0:.3f}",
                          "-vf", f"fps={fps},crop={w}:{h}:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    arr = np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)
    return arr


def grab(plate: str, t: float) -> Image.Image:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", plate, "-frames:v", "1",
                          "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    import io
    return Image.open(io.BytesIO(raw)).convert("RGB")


# ---------- captions ----------
def card_words(words: list, max_chars: int, max_lines: int) -> list[list[dict]]:
    limit = max_chars * max_lines
    cards, cur = [], []
    for w in words:
        tok = w["w"].strip()
        txt = " ".join(x["w"].strip() for x in cur + [w])
        if cur and len(txt) > limit:
            cards.append(cur)
            cur = []
        cur.append(w)
        txt = " ".join(x["w"].strip() for x in cur)
        if tok.endswith((".", "?", "!")) or (tok.endswith(",") and len(txt) > max_chars * 0.8):
            cards.append(cur)
            cur = []
    if cur:
        cards.append(cur)
    return cards


def split_lines(ws: list[dict], max_chars: int) -> list[list[dict]]:
    txt = " ".join(w["w"].strip() for w in ws)
    if len(txt) <= max_chars or len(ws) < 2:
        return [ws]
    best, bi = 1e9, 1
    for i in range(1, len(ws)):
        a = len(" ".join(w["w"].strip() for w in ws[:i]))
        b = len(" ".join(w["w"].strip() for w in ws[i:]))
        if max(a, b) < best:
            best, bi = max(a, b), i
    return [ws[:bi], ws[bi:]]


# ---------- renderer ----------
class Renderer:
    def __init__(self, tpl: dict, spec: dict, plate: str):
        self.t, self.s, self.plate = tpl, spec, plate
        self.W, self.H = tpl["size"]
        self.fps = tpl["fps"]
        self.C = {k: hexc(v) for k, v in tpl["colors"].items()}
        self.F = Fonts(tpl["fonts"])
        self.bg = self._make_bg()
        self.T = 0.0
        self.words = []
        if spec.get("transcript"):
            tr = json.loads((ROOT / spec["transcript"]).read_text())
            self.words = [w for sgm in tr["segments"] for w in sgm["words"]]

    def _make_bg(self) -> Image.Image:
        step = 90
        self.grid_step = step
        im = Image.new("RGBA", (self.W + step, self.H + step), self.C["bg"])
        d = ImageDraw.Draw(im)
        for x in range(0, self.W + 2 * step, step):
            d.line([(x, 0), (x, self.H + step)], fill=self.C["bg_grid"], width=1)
        for y in range(0, self.H + 2 * step, step):
            d.line([(0, y), (self.W + step, y)], fill=self.C["bg_grid"], width=1)
        self.grid = im
        im = Image.new("RGBA", (self.W, self.H), self.C["bg"])
        # soft vignette glow in accent at the top
        glow = Image.new("L", (self.W, self.H), 0)
        ImageDraw.Draw(glow).ellipse([-200, -500, self.W + 200, 500], fill=70)
        glow = glow.filter(ImageFilter.GaussianBlur(120))
        self.glow = glow
        self.tint = Image.new("RGBA", (self.W, self.H), self.C["accent_dark"])
        return im

    def bg_at(self, T: float) -> Image.Image:
        """Background with the grid drifting slowly (12 px/s) so no frame is ever fully static."""
        off = (T * 12.0) % self.grid_step
        g = self.grid.crop((int(off), int(off * 0.5), int(off) + self.W, int(off * 0.5) + self.H))
        return Image.composite(self.tint, g, self.glow)

    # ---- text helpers
    def text_center(self, layer, txt, font, y, color, alpha=1.0, dy=0.0, x=None):
        d = ImageDraw.Draw(layer)
        w = text_w(font, txt)
        xx = (self.W - w) / 2 if x is None else x
        c = color[:3] + (int(color[3] * clamp01(alpha)),)
        d.text((xx, y + dy), txt, font=font, fill=c)

    def headline(self, layer, lines, t, y0=170, size=78):
        f = self.F("black", size)
        for i, ln in enumerate(lines):
            p = ease((t - 0.08 - i * 0.18) / 0.4)
            col = self.C["text"] if i == 0 else self.C["accent"]
            self.text_center(layer, ln, f, y0 + i * (size + 14), col, p, (1 - p) * 30)

    # ---- segments
    def seg_talk(self, seg, frames, i, t):
        tp = self.t["talk"]
        n = len(frames)
        z = tp["zoom_from"] + (tp["zoom_to"] - tp["zoom_from"]) * (i / max(n - 1, 1))
        src = Image.fromarray(frames[i])
        sw, sh = src.size
        fw, fh = self.W, tp["frame_h"]
        ax, ay = tp["zoom_anchor"]
        scale = fw / sw * z                      # output px per source px
        vis_w, vis_h = fw / scale, fh / scale    # source px visible
        x0 = min(max(ax - vis_w * (ax / sw), 0), sw - vis_w)
        y0 = min(max(ay - vis_h * (ay / sh), 0), sh - vis_h)
        img = src.transform((fw, fh), Image.AFFINE, (1 / scale, 0, x0, 0, 1 / scale, y0), resample=Image.BICUBIC)
        canvas = self.bg_at(self.T)
        canvas.paste(img, (0, 0))
        # fade footage into the caption band
        fade = tp["band_fade_px"]
        grad = Image.new("L", (1, fade))
        for yy in range(fade):
            grad.putpixel((0, yy), int(255 * (yy / fade) ** 1.6))
        grad = grad.resize((self.W, fade))
        band = Image.new("RGBA", (self.W, fade), self.C["bg"])
        canvas.paste(band, (0, fh - fade), grad)
        if seg.get("headline"):
            g = Image.new("L", (1, 520))
            for yy in range(520):
                g.putpixel((0, yy), int(215 * (1 - yy / 520) ** 1.3))
            canvas.paste(Image.new("RGBA", (self.W, 520), self.C["bg"]), (0, 0), g.resize((self.W, 520)))
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        if seg.get("headline"):
            self.headline(layer, seg["headline"], t, y0=seg.get("headline_y", 110))
        if seg.get("chips"):
            self.chips(layer, seg, t)
        if seg.get("strip"):
            self.strip(layer, seg, t)
        if seg.get("lower_third"):
            self.lower_third(layer, t)
        self.captions(layer, seg, seg["_vin"] + t)
        canvas.alpha_composite(layer)
        return canvas

    def chips(self, layer, seg, t):
        """Pain/feature chips beside the head (left column), each popping on its spoken word."""
        c = seg["chips"]
        d = ImageDraw.Draw(layer)
        f = self.F("bold", c.get("size", 34))
        good = c.get("icon", "check") == "check"
        ic = self.C["accent"] if good else self.C["bad"]
        x, y = c.get("x", 34), c.get("y", 150)
        if c.get("title"):
            a = ease((t - 0.1) / 0.3)
            ft = self.F("bold", 26)
            tw = text_w(ft, c["title"].upper())
            d.rounded_rectangle([x, y - 54, x + tw + 36, y - 10], radius=22, fill=self.C["bg"][:3] + (int(215 * a),))
            d.text((x + 18, y - 47), c["title"].upper(), font=ft, fill=self.C["accent"][:3] + (int(255 * a),))
        for k, item in enumerate(c["items"]):
            at = seg["_chip_t"][k] if seg.get("_chip_t") else 0.3 + 0.6 * k
            p = ease((t - at) / 0.28)
            if p <= 0:
                y += 96
                continue
            w = text_w(f, item) + 104
            xx = x - (1 - p) * 60
            d.rounded_rectangle([xx, y, xx + w, y + 80], radius=22, fill=self.C["bg"][:3] + (int(215 * p),),
                                outline=ic[:3] + (int(160 * p),), width=2)
            d.ellipse([xx + 18, y + 20, xx + 58, y + 60], fill=ic[:3] + (int(255 * p),))
            (self.check if good else self.cross)(d, xx + 38, y + 40, 10, self.C["bg"][:3] + (int(255 * p),))
            d.text((xx + 74, y + 18), item, font=f, fill=self.C["text"][:3] + (int(255 * p),))
            y += 96

    def strip(self, layer, seg, t):
        """Compact workflow panel over the torso: nodes light up across the segment (or on spoken words)."""
        st = seg["strip"]
        labels = st["labels"]
        n = len(labels)
        a = ease((t - st.get("at", 0.2)) / 0.35)
        if a <= 0:
            return
        top = st.get("y", 820)
        pan = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        dp = ImageDraw.Draw(pan)
        dp.rounded_rectangle([40, top, self.W - 40, top + 210], radius=30, fill=self.C["bg"][:3] + (int(225 * a),),
                             outline=self.C["card_edge"][:3] + (int(255 * a),), width=2)
        layer.alpha_composite(pan)
        d = ImageDraw.Draw(layer)
        size, gap = 104, (self.W - 80) / n
        xs = [40 + gap * (k + 0.5) for k in range(n)]
        cy = top + 78
        u = clamp01((t - st.get("at", 0.2)) / max(seg["dur"] - st.get("at", 0.2) - 0.6, 0.5))
        c = u * n
        for k in range(n - 1):
            xa, xb = xs[k] + size / 2, xs[k + 1] - size / 2
            d.line([(xa, cy), (xb, cy)], fill=self.C["card_edge"][:3] + (int(255 * a),), width=4)
            fl = clamp01(c - k - 0.7) / 0.3 if c - k > 0.7 else 0
            if fl > 0:
                d.line([(xa, cy), (xa + (xb - xa) * clamp01(fl), cy)], fill=self.C["accent"], width=4)
        fl_ = self.F("semibold", 24)
        for k, x in enumerate(xs):
            lit = c >= k
            box = [x - size / 2, cy - size / 2, x + size / 2, cy + size / 2]
            d.rounded_rectangle(box, radius=24, fill=self.C["card"][:3] + (int(255 * a),),
                                outline=(self.C["accent"] if lit else self.C["card_edge"])[:3] + (int(255 * a),), width=4)
            col = (self.C["text"] if lit else self.C["muted"])[:3] + (int(255 * a),)
            self.icon_small(d, st.get("icons", [0, 1, 2, 3])[k % 4], x, cy, col)
            lab = labels[k]
            d.text((x - text_w(fl_, lab) / 2, cy + size / 2 + 8), lab, font=fl_, fill=col)

    def icon_small(self, d, k, x, y, col):
        s = 0.55
        if k == 0:
            d.rounded_rectangle([x - 26, y - 18, x + 26, y + 18], radius=5, outline=col, width=4)
            d.line([(x - 23, y - 14), (x, y + 4), (x + 23, y - 14)], fill=col, width=4)
        elif k == 1:
            f = self.F("black", 34)
            d.text((x - text_w(f, "AI") / 2, y - 22), "AI", font=f, fill=col)
        elif k == 2:
            d.ellipse([x - 22, y - 26, x + 22, y - 10], outline=col, width=4)
            d.arc([x - 22, y - 8, x + 22, y + 8], 0, 180, fill=col, width=4)
            d.arc([x - 22, y + 10, x + 22, y + 26], 0, 180, fill=col, width=4)
            d.line([(x - 22, y - 18), (x - 22, y + 18)], fill=col, width=4)
            d.line([(x + 22, y - 18), (x + 22, y + 18)], fill=col, width=4)
        else:
            d.rounded_rectangle([x - 26, y - 20, x + 26, y + 14], radius=10, outline=col, width=4)
            d.polygon([(x - 10, y + 13), (x - 16, y + 26), (x, y + 13)], fill=col)

    def lower_third(self, layer, t):
        a = ease(t / 0.35) * (1 - ease((t - 3.4) / 0.3))
        if a <= 0:
            return
        d = ImageDraw.Draw(layer)
        fn, ft = self.F("bold", 40), self.F("medium", 28)
        name, title = self.s["name"], self.s["title"]
        w = max(text_w(fn, name), text_w(ft, title)) + 64
        x = 40 - (1 - a) * 60
        y = 820
        d.rounded_rectangle([x, y, x + w, y + 118], radius=22, fill=self.C["bg"][:3] + (int(225 * a),))
        d.rounded_rectangle([x, y, x + 8, y + 118], radius=4, fill=self.C["accent"][:3] + (int(255 * a),))
        d.text((x + 32, y + 18), name, font=fn, fill=self.C["text"][:3] + (int(255 * a),))
        d.text((x + 32, y + 68), title, font=ft, fill=self.C["muted"][:3] + (int(255 * a),))

    def captions(self, layer, seg, ts):
        cp = self.t["captions"]
        cards = seg["_cards"]
        cur = None
        for ci, c in enumerate(cards):
            start = c[0]["s"]
            end = cards[ci + 1][0]["s"] if ci + 1 < len(cards) else c[-1]["e"] + 0.5
            if start - 0.05 <= ts < end:
                cur = c
                break
        if cur is None:
            return
        f = self.F("bold", cp["size"])
        lines = split_lines(cur, cp["max_chars_per_line"])
        lh = cp["size"] + cp["line_gap"]
        y = cp["y_center"] - len(lines) * lh / 2
        a = ease((ts - cur[0]["s"] + 0.05) / 0.12)
        d = ImageDraw.Draw(layer)
        emph = set(seg.get("emphasis", []))
        for ln in lines:
            words = [w["w"].strip() for w in ln]
            total = text_w(f, " ".join(words))
            x = (self.W - total) / 2
            for w, tok in zip(ln, words):
                active = w["s"] - 0.03 <= ts < w["e"] + 0.05
                said = ts >= w["s"]
                if active or (tok in emph and said):
                    col = self.C["accent"]
                else:
                    col = self.C["text"] if said else self.C["muted"]
                d.text((x, y), tok, font=f, fill=col[:3] + (int(255 * a),))
                x += text_w(f, tok + " ")
            y += lh

    def seg_workflow(self, seg, i, t):
        dur = seg["dur"]
        canvas = self.bg_at(self.T)
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        self.headline(layer, seg["headline"], t, y0=300)
        p0, p1 = seg["progress"]
        p = p0 + (p1 - p0) * clamp01((t - 0.35) / max(dur - 0.9, 0.5))
        self.workflow_graphic(layer, p, t, seg.get("done") and t > dur - 1.1, seg.get("labels"), seg.get("done_text"))
        canvas.alpha_composite(layer)
        return canvas

    def workflow_graphic(self, layer, p, t, done, labels=None, done_text=None):
        d = ImageDraw.Draw(layer)
        labels = labels or ["New email", "AI sorts it", "CRM updated", "Team notified"]
        cy, size, gap = 790, 190, 250
        xs = [self.W / 2 + (k - 1.5) * gap for k in range(4)]
        c = p * 4.0
        appear = ease(t / 0.5)
        # connectors
        for k in range(3):
            xa, xb = xs[k] + size / 2, xs[k + 1] - size / 2
            d.line([(xa, cy), (xb, cy)], fill=self.C["card_edge"][:3] + (int(255 * appear),), width=6)
            fill = clamp01(c - k - 0.6) / 0.4 if c - k > 0.6 else 0
            fill = clamp01(fill)
            if fill > 0:
                d.line([(xa, cy), (xa + (xb - xa) * fill, cy)], fill=self.C["accent"], width=6)
                if fill < 1:
                    px = xa + (xb - xa) * fill
                    d.ellipse([px - 11, cy - 11, px + 11, cy + 11], fill=self.C["text"])
        # nodes
        for k, x in enumerate(xs):
            lit = c >= k
            pop = ease((c - k) / 0.25) if lit else 0
            s = size * (1 + 0.06 * math.sin(math.pi * pop)) if lit else size
            box = [x - s / 2, cy - s / 2, x + s / 2, cy + s / 2]
            if lit:
                glow = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
                ImageDraw.Draw(glow).rounded_rectangle([b + o for b, o in zip(box, (-14, -14, 14, 14))], radius=50,
                                                       fill=self.C["accent"][:3] + (int(90 * pop),))
                layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(18)))
                d = ImageDraw.Draw(layer)
            d.rounded_rectangle(box, radius=40, fill=self.C["card"][:3] + (int(255 * appear),),
                                outline=(self.C["accent"] if lit else self.C["card_edge"])[:3] + (int(255 * appear),), width=5)
            col = self.C["text"] if lit else self.C["muted"]
            self.icon(d, k, x, cy, col[:3] + (int(255 * appear),))
            fl = self.F("semibold", 30)
            self.text_center(layer, labels[k], fl, cy + size / 2 + 26, (self.C["text"] if lit else self.C["muted"]),
                             appear, x=x - text_w(fl, labels[k]) / 2)
        if done:
            fb = self.F("bold", 40)
            msg = done_text or "Automated. No copy-paste."
            w = text_w(fb, msg) + 120
            a = ease((t % 100) and 1.0)
            x0 = (self.W - w) / 2
            y0 = 1050
            d.rounded_rectangle([x0, y0, x0 + w, y0 + 86], radius=43, fill=self.C["accent"][:3] + (235,))
            self.check(d, x0 + 52, y0 + 43, 18, self.C["bg"])
            d.text((x0 + 88, y0 + 19), msg, font=fb, fill=self.C["bg"])

    def icon(self, d, k, x, y, col):
        if k == 0:   # envelope
            d.rounded_rectangle([x - 46, y - 32, x + 46, y + 32], radius=8, outline=col, width=6)
            d.line([(x - 42, y - 26), (x, y + 6), (x + 42, y - 26)], fill=col, width=6, joint="curve")
        elif k == 1:  # AI
            f = self.F("black", 58)
            w = text_w(f, "AI")
            d.text((x - w / 2, y - 38), "AI", font=f, fill=col)
            for dx, dy, r in ((44, -40, 9), (52, -18, 5)):
                d.ellipse([x + dx - r, y + dy - r, x + dx + r, y + dy + r], fill=col)
        elif k == 2:  # database
            d.ellipse([x - 40, y - 46, x + 40, y - 18], outline=col, width=6)
            d.arc([x - 40, y - 14, x + 40, y + 14], 0, 180, fill=col, width=6)
            d.arc([x - 40, y + 18, x + 40, y + 46], 0, 180, fill=col, width=6)
            d.line([(x - 40, y - 32), (x - 40, y + 32)], fill=col, width=6)
            d.line([(x + 40, y - 32), (x + 40, y + 32)], fill=col, width=6)
        else:         # chat bubble
            d.rounded_rectangle([x - 46, y - 36, x + 46, y + 26], radius=18, outline=col, width=6)
            d.polygon([(x - 20, y + 24), (x - 30, y + 46), (x - 2, y + 24)], fill=col)
            for dx in (-22, 0, 22):
                d.ellipse([x + dx - 6, y - 11, x + dx + 6, y + 1], fill=col)

    def check(self, d, x, y, r, col):
        d.line([(x - r, y), (x - r / 3, y + r * 0.7), (x + r, y - r * 0.8)], fill=col, width=7, joint="curve")

    def cross(self, d, x, y, r, col):
        d.line([(x - r, y - r), (x + r, y + r)], fill=col, width=7)
        d.line([(x - r, y + r), (x + r, y - r)], fill=col, width=7)

    def seg_list(self, seg, i, t):
        canvas = self.bg_at(self.T)
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        fk = self.F("bold", 40)
        a = ease(t / 0.3)
        self.text_center(layer, seg["kicker"].upper(), fk, seg.get("kicker_y", 330), self.C["accent"], a, (1 - a) * 20)
        fi = self.F("bold", 56)
        n = len(seg["items"])
        step = (seg["dur"] - 0.8) / n
        y = seg.get("y0", 470)
        for k, item in enumerate(seg["items"]):
            at = seg["_item_t"][k] if seg.get("_item_t") else 0.25 + k * step
            p = ease((t - at) / 0.3)
            if p <= 0:
                y += seg.get("step_y", 190)
                continue
            x0 = 90 + (1 - p) * 50
            d.rounded_rectangle([x0, y, self.W - 90 + (1 - p) * 50, y + 150], radius=34,
                                fill=self.C["card"][:3] + (int(255 * p),), outline=self.C["card_edge"][:3] + (int(255 * p),), width=3)
            good = seg["icon"] == "check"
            ic = self.C["accent"] if good else self.C["bad"]
            d.ellipse([x0 + 38, y + 39, x0 + 110, y + 111], fill=ic[:3] + (int(255 * p),))
            (self.check if good else self.cross)(d, x0 + 74, y + 75, 16, self.C["bg"][:3] + (int(255 * p),))
            d.text((x0 + 140, y + 44), item, font=fi, fill=self.C["text"][:3] + (int(255 * p),))
            y += seg.get("step_y", 190)
        canvas.alpha_composite(layer)
        return canvas

    def seg_image(self, seg, i, t):
        """Ken Burns on a still (ChatGPT B-roll photo): cover-fit, slow zoom + drift, bottom gradient for captions."""
        if "_img" not in seg:
            seg["_img"] = Image.open(ROOT / seg["image"]).convert("RGB")
        im = seg["_img"]
        u = clamp01(t / max(seg["dur"], 0.1))
        z0, z1 = seg.get("zoom", [1.0, 1.10])
        z = z0 + (z1 - z0) * u
        scale = max(self.W / im.width, self.H / im.height) * z
        vw, vh = self.W / scale, self.H / scale
        fx, fy = seg.get("focus", [0.5, 0.5])
        dx = seg.get("pan", 0.0) * (u - 0.5)
        x0 = min(max(im.width * (fx + dx) - vw / 2, 0), im.width - vw)
        y0 = min(max(im.height * fy - vh / 2, 0), im.height - vh)
        frame = im.transform((self.W, self.H), Image.AFFINE, (1 / scale, 0, x0, 0, 1 / scale, y0), resample=Image.BICUBIC)
        canvas = frame.convert("RGBA")
        g = Image.new("L", (1, self.H))
        for yy in range(self.H):
            g.putpixel((0, yy), int(235 * clamp01((yy - self.H * 0.55) / (self.H * 0.42)) ** 1.3))
        if seg.get("headline"):   # top scrim so headlines stay readable on bright photos
            for yy in range(int(self.H * 0.45)):
                v = int(225 * (1 - yy / (self.H * 0.45)) ** 1.4)
                g.putpixel((0, yy), max(g.getpixel((0, yy)), v))
        shade = Image.new("RGBA", (self.W, self.H), self.C["bg"])
        canvas = Image.composite(shade, canvas, g.resize((self.W, self.H)))
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        if seg.get("kicker"):
            fk = self.F("bold", 38)
            a = ease((t - 0.2) / 0.35)
            w = text_w(fk, seg["kicker"].upper()) + 56
            d = ImageDraw.Draw(layer)
            x = (self.W - w) / 2
            d.rounded_rectangle([x, 120, x + w, 190], radius=35, fill=self.C["bg"][:3] + (int(200 * a),))
            self.text_center(layer, seg["kicker"].upper(), fk, 133, self.C["accent"], a)
        if seg.get("headline"):
            self.headline(layer, seg["headline"], t, y0=seg.get("headline_y", 230))
        canvas.alpha_composite(layer)
        return canvas

    def seg_end(self, seg, i, t):
        canvas = self.bg_at(self.T)
        layer = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        if "_photo" not in seg:
            fr = grab(self.plate, seg["photo_src_t"])
            sx = fr.width / 864
            cx, cy, r = 432 * sx, 330 * sx, 190 * sx
            ph = fr.crop((int(cx - r), int(cy - r), int(cx + r), int(cy + r))).resize((300, 300), Image.LANCZOS)
            m = Image.new("L", (300, 300), 0)
            ImageDraw.Draw(m).ellipse([0, 0, 299, 299], fill=255)
            seg["_photo"], seg["_mask"] = ph, m
        a = ease(t / 0.4)
        ring = 312
        x0, y0 = (self.W - ring) // 2, 190
        d.ellipse([x0, y0, x0 + ring, y0 + ring], fill=self.C["accent"][:3] + (int(255 * a),))
        if a > 0.05:
            ph = seg["_photo"].copy().convert("RGBA")
            ph.putalpha(seg["_mask"].point(lambda v: int(v * a)))
            layer.alpha_composite(ph, (x0 + 6, y0 + 6))
        d = ImageDraw.Draw(layer)
        fn, ft = self.F("bold", 40), self.F("medium", 30)
        self.text_center(layer, self.s["name"], fn, 530, self.C["text"], a)
        self.text_center(layer, self.s["title"], ft, 582, self.C["muted"], a)
        self.headline(layer, seg["headline"], t - 0.25, y0=700, size=80)
        fs = self.F("semibold", 44)
        b = ease((t - 0.9) / 0.4)
        self.text_center(layer, seg["sub"], fs, 910, self.C["muted"], b, (1 - b) * 20)
        c = ease((t - 1.3) / 0.4)
        fb = self.F("bold", 46)
        w = text_w(fb, seg["button"]) + 120
        bx = (self.W - w) / 2
        by = 1050 + (1 - c) * 30
        pulse = 1 + 0.03 * math.sin(max(t - 1.7, 0) * 4) if t > 1.7 else 1
        pw = w * pulse
        bx2 = (self.W - pw) / 2
        d.rounded_rectangle([bx2, by, bx2 + pw, by + 104], radius=52, fill=self.C["accent"][:3] + (int(255 * c),))
        d.text((bx + 60, by + 26), seg["button"], font=fb, fill=self.C["bg"][:3] + (int(255 * c),))
        canvas.alpha_composite(layer)
        return canvas


# ---------- timeline / audio ----------
def build_timeline(spec, r: Renderer):
    t = 0.0
    cp = r.t["captions"]
    for seg in spec["segments"]:
        if seg["type"] == "talk":
            a0, a1 = seg["src"]
            vin = seg.get("video_in", a0)
            seg["_vin"], seg["_pre"] = vin, vin - a0
            seg["dur"] = a1 - vin
            ws = [w for w in r.words if a0 - 0.05 <= w["s"] < a1]
            seg["_cards"] = card_words(ws, cp["max_chars_per_line"], cp["max_lines"])
        if seg.get("vo"):
            vd = ROOT / spec["vo_dir"]
            mp3 = vd / f"{seg['vo']}.mp3"
            dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                                  "-of", "csv=p=0", str(mp3)]))
            al = json.loads((vd / f"{seg['vo']}.align.json").read_text())["words"]
            f0, f1 = seg.get("vo_from", 0.0), seg.get("vo_to", dur)
            al = [dict(w, s=w["s"] - f0, e=w["e"] - f0) for w in al if f0 - 0.01 <= w["s"] < f1]
            lead = seg.get("lead", 0.0 if seg["type"] == "face" else 0.12)
            seg["_vo_mp3"], seg["_lead"], seg["_vo_from"], seg["_vo_to"] = str(mp3), lead, f0, f1
            seg["dur"] = round(lead + (f1 - f0) + seg.get("tail", 0.0 if seg["type"] == "face" else 0.18), 3)
            seg["_vin"] = -lead                       # captions use t + _vin == time inside the VO line
            seg["_cards"] = card_words(al, cp["max_chars_per_line"], cp["max_lines"])
            if seg.get("chips") and seg["chips"].get("item_words"):
                def findc(word):
                    return next((w["s"] for w in al if word.lower() in w["w"].lower()), None)
                seg["_chip_t"] = [(findc(x) if findc(x) is not None else 0.3 + 0.6 * k) + lead - 0.06
                                  for k, x in enumerate(seg["chips"]["item_words"])]
            if seg.get("item_words"):
                def find(word):
                    return next((w["s"] for w in al if word.lower() in w["w"].lower()), None)
                seg["_item_t"] = [(find(x) if find(x) is not None else 0.3 + k) + lead - 0.08
                                  for k, x in enumerate(seg["item_words"])]
        seg["_t0"] = t
        t += seg["dur"]
    return t


def make_music(total: float, spec, path: Path, sr: int = 48000, card_db=-27.0, talk_db=-38.0):
    """Original ambient pad (Am-F-C-G), synthesized here, so it's royalty-free by construction."""
    n = int(total * sr)
    tt = np.arange(n) / sr
    out = np.zeros((n, 2), np.float32)
    chords = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 55, 60, 64], [55, 59, 62, 67]]
    bar = 2.4
    for b in range(int(total / bar) + 2):
        notes = chords[b % 4]
        s0 = b * bar
        i0, i1 = int(max(s0 - 0.3, 0) * sr), int(min(s0 + bar + 0.9, total) * sr)
        if i0 >= n:
            break
        seg_t = tt[i0:i1] - s0
        env = np.clip((seg_t + 0.3) / 0.9, 0, 1) * np.clip((bar + 0.9 - seg_t) / 1.0, 0, 1)
        for j, m in enumerate(notes + [notes[0] - 12]):
            f = 440 * 2 ** ((m - 69) / 12)
            for ch, det in ((0, -0.6), (1, 0.6)):
                ph = 2 * np.pi * (f + det) * tt[i0:i1]
                tone = np.sin(ph) + 0.18 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)
                out[i0:i1, ch] += (0.10 if j < 4 else 0.16) * env * tone
    # gentle low-pass for warmth (FFT brick-wall with soft roll-off; numpy only)
    spec_ = np.fft.rfft(out, axis=0)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    spec_ *= (1 / (1 + (freqs / 1400.0) ** 4))[:, None]
    out = np.fft.irfft(spec_, n=n, axis=0).astype(np.float32)
    out /= np.max(np.abs(out)) + 1e-9
    gain = np.full(n, 10 ** (card_db / 20), np.float32)
    for seg in spec["segments"]:
        if seg["type"] == "talk" or seg.get("vo"):
            seg.setdefault("_pre", 0.0)
            i0 = int(max(seg["_t0"] - seg["_pre"] - 0.15, 0) * sr)
            i1 = int(min(seg["_t0"] + seg["dur"] + 0.1, total) * sr)
            gain[i0:i1] = 10 ** (talk_db / 20)
    k = int(0.25 * sr)
    gain = np.convolve(gain, np.ones(k) / k, mode="same")
    fade = np.clip(tt / 0.6, 0, 1) * np.clip((total - tt) / 1.2, 0, 1)
    out *= (gain * fade)[:, None]
    pcm = (np.clip(out, -1, 1) * 32767).astype("<i2")
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def build_audio(spec, src_audio: str, total: float, tmp: Path, tpl: dict, final: bool) -> Path:
    music = tmp / "music.wav"
    make_music(total, spec, music)
    inputs, parts = ["-i", str(music)], []
    fd = tpl["audio"]["speech_fade_ms"] / 1000
    k = 1
    for seg in spec["segments"]:
        if seg.get("vo"):
            inputs += ["-i", seg["_vo_mp3"]]
            parts.append(f"[{k}:a]atrim={seg['_vo_from']}:{seg['_vo_to']},asetpts=PTS-STARTPTS,afade=t=in:d=0.01,"
                         f"aresample=48000,aformat=channel_layouts=stereo,adelay={int((seg['_t0'] + seg['_lead']) * 1000)}:all=1[s{k}]")
            k += 1
            continue
        if seg["type"] != "talk":
            continue
        a0, a1 = seg["src"]
        start = seg["_t0"] - seg["_pre"]
        inputs += ["-i", src_audio]
        parts.append(f"[{k}:a]atrim={a0}:{a1},asetpts=PTS-STARTPTS,highpass=f=70,afade=t=in:d={fd},"
                     f"afade=t=out:st={a1 - a0 - fd}:d={fd},adelay={int(start * 1000)}:all=1[s{k}]")
        k += 1
    mix = "".join(f"[s{i}]" for i in range(1, k))
    au = tpl["audio"]
    raw = tmp / "mix_raw.wav"
    fc = ";".join(parts) + f";{mix}amix=inputs={k - 1}:normalize=0[sp];[sp][0:a]amix=inputs=2:normalize=0,aresample=48000[out]"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", fc,
                    "-map", "[out]", "-t", f"{total:.3f}", "-c:a", "pcm_s24le", str(raw)], check=True)
    # two-pass LINEAR loudnorm: one gain for the whole mix, so the music bed stays quiet relative to speech
    # (single-pass loudnorm is dynamic and pumps quiet music-only parts up; see docs/LESSONS.md)
    ln = f"loudnorm=I={au['lufs']}:TP={au['true_peak']}:LRA=11"
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(raw), "-af", ln + ":print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    import re as _re
    m = json.loads(_re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err, _re.S).group(0))
    af = (f"{ln}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,"
          f"alimiter=limit={10 ** (au['true_peak'] / 20):.3f}:level=false,aresample=48000")
    out = tmp / "mix.wav"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-af", af,
                    "-c:a", "pcm_s16le", str(out)], check=True)
    return out


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--still", help="comma-separated output times: write PNG stills instead of a video")
    ap.add_argument("--source", default="source/original_small.mp4")
    ap.add_argument("--logo-patch", default="kaggle/work/original_small/inpainted.mkv")
    ap.add_argument("--plate")
    a = ap.parse_args()

    spec = json.loads((ROOT / a.spec).read_text())
    tpl = json.loads((ROOT / spec["template"]).read_text())
    base = Path(a.source).stem
    plate = Path(a.plate) if a.plate else ROOT / "kaggle" / "work" / base / "plate.mp4"
    if not plate.exists():
        print("building plate (logo inpainted, no captions) ...", flush=True)
        make_plate(str(ROOT / a.source), str(ROOT / a.logo_patch), ROOT / "templates" / "clean_master.json", plate)
    r = Renderer(tpl, spec, str(plate))
    total = build_timeline(spec, r)
    fps = r.fps
    print(f"{spec['id']}: {len(spec['segments'])} segments, {total:.2f}s", flush=True)

    def seg_frames(seg):
        if seg["type"] == "talk":
            return read_frames(str(plate), seg["_vin"], seg["_vin"] + seg["dur"], tpl["talk"]["source_crop"], fps)
        if seg["type"] == "face":   # lip-synced clip (already cropped to source_crop size), aligned with the VO line
            v = str(ROOT / seg["video"])
            w, h = tpl["talk"]["source_crop"][2:]
            t0 = seg.get("video_off", 0.0) + seg.get("_vo_from", 0.0)
            return read_frames(v, t0, t0 + seg["dur"] + 0.1, [0, 0, w, h], fps)
        return None

    def frame_at(seg, i, frames):
        t = i / fps
        r.T = seg["_t0"] + t
        if seg["type"] in ("talk", "face"):
            return r.seg_talk(seg, frames, min(i, len(frames) - 1), t)
        fr = getattr(r, "seg_" + seg["type"])(seg, i, t)
        if seg.get("vo") and seg.get("captions", True):
            lay = Image.new("RGBA", (r.W, r.H), (0, 0, 0, 0))
            r.captions(lay, seg, t + seg["_vin"])
            fr.alpha_composite(lay)
        return fr

    if a.still:
        outdir = ROOT / "previews" / f"{spec['id']}_stills"
        outdir.mkdir(parents=True, exist_ok=True)
        for ts in map(float, a.still.split(",")):
            seg = next(s for s in spec["segments"] if s["_t0"] <= ts < s["_t0"] + s["dur"])
            i = int((ts - seg["_t0"]) * fps)
            frames = seg_frames(seg)
            frame_at(seg, i, frames).convert("RGB").save(outdir / f"t{ts:05.2f}.png")
        print("stills ->", outdir)
        return

    tmp = Path(tempfile.mkdtemp(prefix="promo_"))
    audio = build_audio(spec, str(ROOT / a.source), total, tmp, tpl, a.final)
    enc = tpl["encode"]["final" if a.final else "preview"]
    out = ROOT / ("exports" if a.final else "previews") / f"{spec['id']}{'' if a.final else '_preview'}.mp4"
    W, H = tpl["size"]
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-i", str(audio), "-c:v", "libx264",
                          "-preset", enc["preset"], "-crf", str(enc["crf"]), "-pix_fmt", "yuv420p", "-profile:v", "high",
                          "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    nframes = 0
    for seg in spec["segments"]:
        frames = seg_frames(seg)
        n = round((seg["_t0"] + seg["dur"]) * fps) - round(seg["_t0"] * fps)
        for i in range(n):
            p.stdin.write(frame_at(seg, i, frames).convert("RGB").tobytes())
            nframes += 1
        print(f"  {seg['type']:<8} {seg['dur']:.2f}s", flush=True)
    p.stdin.close()
    p.wait()
    print(f"wrote {out} ({nframes} frames, {total:.2f}s)")


if __name__ == "__main__":
    main()
