#!/usr/bin/env python3
"""ElevenLabs lane: instant voice clone (IVC) of the owner + TTS for script lines.

    python3 -m lane.elevenlabs whoami
    python3 -m lane.elevenlabs clone assets/voice/owner_voice_sample_full.wav --name "Usman (owner clone)"
    python3 -m lane.elevenlabs say --voice <voice_id> --line 01_hook="Doing the same task..." --out kaggle/outputs/voice-11l
    python3 -m lane.elevenlabs say --voice <voice_id> --job <job.json> --out DIR    # job.json {"lines": {...}}

Auth: the API key is a network secret on the cloud environment. The proxy injects it as the `xi-api-key` header on
api.elevenlabs.io; we send a placeholder. Owner consent to clone their own voice: 2026-11-27 ("use AI from day 1").
The voice ID is stored in assets/voice/elevenlabs_voice.json (not secret).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from urllib import request, error

API = "https://api.elevenlabs.io"
ROOT = Path(__file__).resolve().parent.parent
VOICE_FILE = ROOT / "assets" / "voice" / "elevenlabs_voice.json"
HDR = {"xi-api-key": "proxy-injected"}


def call(method: str, path: str, body: bytes | None = None, ctype: str | None = None, accept="application/json"):
    h = dict(HDR, Accept=accept)
    if ctype:
        h["Content-Type"] = ctype
    req = request.Request(API + path, data=body, method=method, headers=h)
    try:
        with request.urlopen(req, timeout=180) as r:
            return r.read(), r.headers
    except error.HTTPError as e:
        sys.exit(f"elevenlabs {method} {path}: HTTP {e.code} {e.read()[:400]!r}")


def whoami():
    raw, _ = call("GET", "/v1/user/subscription")
    d = json.loads(raw)
    print(json.dumps({k: d.get(k) for k in ("tier", "character_count", "character_limit", "can_use_instant_voice_cloning",
                                              "next_character_count_reset_unix", "status")}, indent=1))


def clone(sample: str, name: str):
    b = "----kgpu" + uuid.uuid4().hex
    parts = []
    for k, v in (("name", name), ("description", "Owner's own voice, cloned with consent for their Upwork videos"),
                 ("remove_background_noise", "false")):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    data = Path(sample).read_bytes()
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="files"; filename="{Path(sample).name}"\r\n'
                 f"Content-Type: audio/wav\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    raw, _ = call("POST", "/v1/voices/add", b"".join(parts), f"multipart/form-data; boundary={b}")
    vid = json.loads(raw)["voice_id"]
    VOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    VOICE_FILE.write_text(json.dumps({"voice_id": vid, "name": name, "sample": sample,
                                      "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1) + "\n")
    print(vid)


def say(voice: str, lines: dict, out: str, model: str, stability: float, similarity: float, style: float):
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    for name, text in lines.items():
        body = json.dumps({"text": text, "model_id": model,
                           "voice_settings": {"stability": stability, "similarity_boost": similarity, "style": style,
                                              "use_speaker_boost": True}}).encode()
        raw, _ = call("POST", f"/v1/text-to-speech/{voice}?output_format=mp3_44100_192", body, "application/json",
                      accept="audio/mpeg")
        (o / f"{name}.mp3").write_bytes(raw)
        print(f"{name}: {len(raw) // 1024} KB")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami")
    c = sub.add_parser("clone")
    c.add_argument("sample")
    c.add_argument("--name", default="Owner clone")
    s = sub.add_parser("say")
    s.add_argument("--voice", default=None)
    s.add_argument("--line", action="append", default=[], help="name=text")
    s.add_argument("--job")
    s.add_argument("--out", required=True)
    s.add_argument("--model", default="eleven_multilingual_v2")
    s.add_argument("--stability", type=float, default=0.45)
    s.add_argument("--similarity", type=float, default=0.9)
    s.add_argument("--style", type=float, default=0.15)
    a = ap.parse_args()
    if a.cmd == "whoami":
        whoami()
    elif a.cmd == "clone":
        clone(a.sample, a.name)
    else:
        voice = a.voice or json.loads(VOICE_FILE.read_text())["voice_id"]
        lines = dict(x.split("=", 1) for x in a.line)
        if a.job:
            lines.update(json.loads(Path(a.job).read_text())["lines"])
        say(voice, lines, a.out, a.model, a.stability, a.similarity, a.style)


if __name__ == "__main__":
    main()
