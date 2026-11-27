#!/usr/bin/env python3
"""Documentary-style bed for Trip Memories (original, royalty-free, numpy only, $0).

Sparse piano notes (decaying sine + harmonics, soft attack) over a slow-attack pad and a low string drone; no drums,
no strumming. A-minor colours (Am - F - C - G, two bars each at 80 bpm). Energy per section only changes how many
piano notes play and how open the pad is: low = a note every ~2 bars, mid = every 1-2 beats, high = most beats
(single notes, never chords/arpeggio strums). Light reverb tail. Silence from `silence_from` (ending card).
Usage: make_doc(total_s, [(t0, t1, "low"|"mid"|"high"), ...], out_wav, bpm=80, silence_from=None)
"""
import wave
from pathlib import Path

import numpy as np

SR = 48000
CHORDS = [(57, 60, 64, 67), (53, 57, 60, 64), (48, 55, 60, 64), (55, 59, 62, 66)]   # Am9ish, Fmaj7, C, G
DRONE = [33, 29, 36, 31]                                                              # A1, F1, C2, G1
SCALE = [0, 2, 4, 7, 9]                                                               # pentatonic-ish above each root
PIANO_GAIN = {"low": 0.55, "mid": 0.8, "high": 0.95}
PAD_GAIN = {"low": 0.5, "mid": 0.75, "high": 0.95}
NOTE_P = {"low": 0.16, "mid": 0.45, "high": 0.7}      # chance of a note per beat


def beat(bpm: float = 80) -> float:
    return 60.0 / bpm


def _hz(m): return 440 * 2 ** ((m - 69) / 12)


def _piano(m, dur, vel):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = _hz(m)
    out = np.zeros(n, np.float32)
    for h, a in enumerate((1.0, 0.5, 0.28, 0.14, 0.07, 0.04), 1):
        fh = f * h * np.sqrt(1 + 0.0004 * h * h)                      # slight string inharmonicity
        out += (a * np.sin(2 * np.pi * fh * t) * np.exp(-t * (1.1 + 0.9 * h))).astype(np.float32)
    att = np.minimum(t / 0.012, 1.0)                                  # soft hammer
    return out * att * np.exp(-t * 0.35) * vel * np.minimum((dur - t) / 0.5, 1.0)


def _swell(sig, att, rel):
    n = len(sig)
    env = np.minimum(np.arange(n) / (att * SR), 1) * np.minimum(np.arange(n)[::-1] / (rel * SR), 1)
    return sig * (env ** 1.5)


def _reverb(x, rng, secs=2.6, mix=0.28):
    n = int(secs * SR)
    ir = rng.normal(0, 1, (2, n)) * np.exp(-np.arange(n) / (0.32 * SR))
    ir[:, :int(0.02 * SR)] = 0
    ir /= np.sqrt((ir ** 2).sum(1, keepdims=True))
    out = np.empty_like(x)
    m = 1 << int(np.ceil(np.log2(x.shape[0] + n)))
    for c in range(2):
        wet = np.fft.irfft(np.fft.rfft(x[:, c], m) * np.fft.rfft(ir[c], m), m)[: x.shape[0]]
        out[:, c] = x[:, c] * (1 - mix) + wet * mix * 2.2
    return out


def make_doc(total, sections, path: Path, bpm: float = 80, silence_from=None, seed: int = 11) -> Path:
    rng = np.random.default_rng(seed)
    n = int(total * SR)
    pad = np.zeros((n + 6 * SR, 2), np.float32)
    pno = np.zeros_like(pad)
    b = beat(bpm)
    bar = 4 * b

    def energy(t):
        for t0, t1, e in sections:
            if t0 <= t < t1:
                return e
        return sections[-1][2] if sections else "mid"

    def put(buf, sig, t, pan=0.5):
        i = int(t * SR)
        if i >= n:
            return
        j = min(i + len(sig), len(buf))
        buf[i:j, 0] += sig[: j - i] * (1 - pan * 0.6)
        buf[i:j, 1] += sig[: j - i] * (0.4 + pan * 0.6)

    phrase = 2 * bar                                                 # chord changes every two bars
    for k in range(int(total / phrase) + 1):
        t0 = k * phrase
        e = energy(t0)
        ch, dr = CHORDS[k % 4], DRONE[k % 4]
        L = phrase + 3.0                                             # overlap: long release into the next chord
        t = np.arange(int(L * SR)) / SR
        for j, m in enumerate(ch):                                   # soft pad: detuned sine pairs, slow attack
            s = sum(np.sin(2 * np.pi * _hz(m) * (1 + d) * t + ph) for d, ph in ((0.0, 0), (0.0035, 1.3), (-0.003, 2.1)))
            s = s + 0.25 * np.sin(2 * np.pi * _hz(m + 12) * t)
            put(pad, _swell(s.astype(np.float32), 2.2, 3.0) * 0.045 * PAD_GAIN[e], t0, 0.3 + 0.4 * j / 3)
        vib = 1 + 0.0015 * np.sin(2 * np.pi * 4.7 * t + k)           # low string drone: bowed-ish, filtered saw
        ph = 2 * np.pi * _hz(dr) * np.cumsum(vib) / SR
        d = sum(np.sin(h * ph) / h ** 1.3 for h in range(1, 9))
        put(pad, _swell(d.astype(np.float32), 3.0, 3.5) * 0.10 * (0.8 + 0.2 * PAD_GAIN[e]), t0, 0.5)
    for bt in range(int(total / b)):                                 # sparse piano: single notes, humanised
        t = bt * b + rng.uniform(0, 0.05)
        if t >= total:
            break
        e = energy(t)
        on_strong = bt % 4 == 0
        if rng.random() < NOTE_P[e] * (1.6 if on_strong else 0.8):
            ch = CHORDS[int(t / phrase) % 4]
            m = ch[0] + 12 + int(rng.choice(SCALE)) + (12 if (e == "high" and rng.random() < 0.4) else 0)
            put(pno, _piano(m, 5.0, PIANO_GAIN[e] * rng.uniform(0.6, 0.95)), t, rng.uniform(0.25, 0.75))
    mix = _reverb(pno[: n + 3 * SR] * 0.55 + pad[: n + 3 * SR], rng)[:n]
    mix /= np.max(np.abs(mix)) + 1e-9
    fi = int(1.5 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)[:, None]
    end = int((silence_from if silence_from is not None else total - 2.0) * SR)
    fo = min(int(1.2 * SR), end)
    mix[end - fo:end] *= np.linspace(1, 0, fo)[:, None]
    mix[end:] = 0
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 0.8 * 32767).astype("<i2").tobytes())
    return path


if __name__ == "__main__":
    import sys
    make_doc(float(sys.argv[1]) if len(sys.argv) > 1 else 15, [(0, 5, "low"), (5, 10, "mid"), (10, 99, "high")],
             Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/doc.wav"), silence_from=float(sys.argv[1]) if len(sys.argv) > 1 else 15)
