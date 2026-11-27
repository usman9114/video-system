#!/usr/bin/env python3
"""Original upbeat acoustic bed for Trip Memories (royalty-free by construction, numpy only, $0).

Strummed steel-string guitar (Karplus-Strong, I-V-vi-IV in G) + soft kick, clap on 2 and 4, 16th shaker.
Energy per section: "low" = guitar only (soft, sparse strums), "mid" = guitar + shaker, "high" = full kit.
Tempo is fixed so the renderer can put cuts on the beat: beat() returns the beat length in seconds.
Usage: make_upbeat(total_s, [(t0, t1, "low"|"mid"|"high"), ...], out_wav, bpm=112)
"""
import wave
from pathlib import Path

import numpy as np

SR = 48000
# open-position voicings (MIDI, low→high): G, D, Em, C
CHORDS = [[43, 47, 50, 55, 59, 67], [50, 57, 62, 66], [40, 47, 52, 55, 59, 64], [48, 52, 55, 60, 64]]
# 8th-note strum pattern over one bar: D . D U . U D U  (1 = down, -1 = up, 0 = rest)
PATTERN = [1, 0, 1, -1, 0, -1, 1, -1]


def beat(bpm: float = 112) -> float:
    return 60.0 / bpm


def _pluck(freq: float, dur: float, rng, bright: float = 0.6, decay: float = 0.996) -> np.ndarray:
    """Karplus-Strong string, vectorised one period at a time."""
    n_per = max(int(SR / freq), 2)
    total = int(dur * SR)
    buf = rng.uniform(-1, 1, n_per).astype(np.float32)
    # pluck brightness: one-pole low-pass on the excitation
    for _ in range(int((1 - bright) * 4)):
        buf = 0.5 * (buf + np.roll(buf, 1))
    out = np.empty(total + n_per, np.float32)
    pos = 0
    while pos < total:
        out[pos:pos + n_per] = buf
        buf = decay * 0.5 * (buf + np.roll(buf, -1))
        pos += n_per
    out = out[:total]
    out *= np.linspace(1, 0, total) ** 0.4          # natural fade so strums don't pile up
    return out


def _kick(rng):
    t = np.arange(int(0.35 * SR)) / SR
    f = 50 + 70 * np.exp(-t * 28)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)).astype(np.float32)


def _noise_hit(rng, dur, decay, hp=True):
    t = np.arange(int(dur * SR)) / SR
    x = rng.normal(0, 1, len(t)).astype(np.float32)
    if hp:
        x = x - np.convolve(x, np.ones(8) / 8, mode="same")   # crude high-pass: shaker/clap brightness
    return x * np.exp(-t * decay)


def make_upbeat(total: float, sections, path: Path, bpm: float = 112, seed: int = 3) -> Path:
    rng = np.random.default_rng(seed)
    n = int(total * SR) + SR
    L = np.zeros(n, np.float32)
    R = np.zeros(n, np.float32)
    b = beat(bpm)
    eighth = b / 2

    def energy(t):
        for t0, t1, e in sections:
            if t0 <= t < t1:
                return e
        return sections[-1][2] if sections else "mid"

    def add(sig, t, gl, gr):
        i = int(t * SR)
        if i >= n:
            return
        j = min(i + len(sig), n)
        L[i:j] += sig[: j - i] * gl
        R[i:j] += sig[: j - i] * gr

    kick, clap = _kick(rng), _noise_hit(rng, 0.18, 22)
    bar_s = 4 * b
    for bar in range(int(total / bar_s) + 1):
        chord = CHORDS[bar % 4]
        for k, d in enumerate(PATTERN):
            t = bar * bar_s + k * eighth
            if t >= total:
                break
            e = energy(t)
            if d and not (e == "low" and k % 2):     # low energy: only on-beat down strums
                strings = chord if d > 0 else chord[::-1][:4]
                vel = (0.9 if d > 0 else 0.55) * (0.6 if e == "low" else 1.0) * rng.uniform(0.85, 1.0)
                for s_i, m in enumerate(strings):     # strum: ~9 ms between strings
                    f = 440 * 2 ** ((m - 69) / 12)
                    p = _pluck(f, 1.4, rng, bright=0.75 if d > 0 else 0.9) * vel * 0.16
                    pan = 0.35 + 0.3 * (s_i / max(len(strings) - 1, 1))
                    add(p, t + s_i * 0.009 + rng.uniform(0, 0.004), 1 - pan * 0.5, 0.5 + pan * 0.5)
            if e == "high":
                if k in (0, 4):
                    add(kick, t, 0.55, 0.55)
                if k in (2, 6):
                    add(clap, t, 0.16, 0.2)
            if e in ("mid", "high"):
                for sub in (0, 1):                    # 16th shaker
                    add(_noise_hit(rng, 0.06, 70), t + sub * eighth / 2, 0.035 * (1.3 if sub == 0 else 0.8), 0.045)
    mix = np.stack([L, R], 1)[: int(total * SR)]
    # soft body: gentle low-shelf-ish smoothing + normalise with headroom
    mix = np.tanh(mix * 1.4) / 1.4
    mix /= np.max(np.abs(mix)) + 1e-9
    fade = int(1.2 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 0.89 * 32767).astype("<i2").tobytes())
    return path


if __name__ == "__main__":
    import sys
    make_upbeat(float(sys.argv[1]) if len(sys.argv) > 1 else 20, [(0, 6, "low"), (6, 12, "mid"), (12, 99, "high")],
                Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/upbeat.wav"))
