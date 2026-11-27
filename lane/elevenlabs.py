#!/usr/bin/env python3
"""ElevenLabs lane: the owner's voice clone + script narration, optimized for quality and credits.
Skill / playbook: .claude/skills/elevenlabs/SKILL.md

    python3 -m lane.elevenlabs prep  <audio/video> [--out assets/voice/ivc_sample.mp3]   # IVC-spec sample
    python3 -m lane.elevenlabs clone assets/voice/ivc_sample.mp3 --name "Usman - owner clone"
    python3 -m lane.elevenlabs say   --job scripts/videos/01_n8n_v2.voice.json --out kaggle/outputs/voice-11l/01
                                     [--draft] [--takes 2] [--model eleven_multilingual_v2] [--dry-run]
    python3 -m lane.elevenlabs usage                                                     # credits spent (local log)
    python3 -m lane.elevenlabs whoami                                                    # needs user_read permission

`say` features:
  - with-timestamps endpoint: saves <line>.mp3 + <line>.align.json (character timings → word timings for captions)
  - request stitching: each line passes previous_request_ids (max 3) so prosody stays continuous across lines
  - cache: identical (voice, model, settings, text, seed) is never paid for twice (kaggle/cache/elevenlabs/)
  - budget guard: refuses to exceed --max-chars per run and logs every call to reports/elevenlabs-usage.jsonl
  - --draft uses Flash v2.5 (0.5 credit/char) for timing and pacing passes; finals use Multilingual v2 (1 credit/char)

Auth: API key = network secret on the environment, injected by the proxy as `xi-api-key` on api.elevenlabs.io.
Required key permissions: Voices→Write (clone), Text to Speech→Access, optional User→Read (whoami).
Owner consent to clone their own voice: 2026-11-27.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request

API = "https://api.elevenlabs.io"
ROOT = Path(__file__).resolve().parent.parent
VOICE_FILE = ROOT / "assets" / "voice" / "elevenlabs_voice.json"
CACHE = ROOT / "kaggle" / "cache" / "elevenlabs"
USAGE = ROOT / "reports" / "elevenlabs-usage.jsonl"
HDR = {"xi-api-key": "proxy-injected"}

MODELS = {
    "final": "eleven_multilingual_v2",   # most stable with instant clones (ElevenLabs guidance)
    "draft": "eleven_flash_v2_5",        # 0.5 credit/char: timing and pacing drafts
    "expressive": "eleven_v3",           # audio tags like [excited]; test only, less stable with clones
}
CREDIT_PER_CHAR = {"eleven_multilingual_v2": 1.0, "eleven_v3": 1.0, "eleven_flash_v2_5": 0.5, "eleven_turbo_v2_5": 0.5}
DEFAULT_SETTINGS = {"stability": 0.45, "similarity_boost": 0.85, "style": 0.0, "use_speaker_boost": True, "speed": 1.0}


# ---------------- http ----------------
def call(method: str, path: str, body: bytes | None = None, ctype: str | None = None, accept="application/json"):
    h = dict(HDR, Accept=accept)
    if ctype:
        h["Content-Type"] = ctype
    req = request.Request(API + path, data=body, method=method, headers=h)
    try:
        with request.urlopen(req, timeout=300) as r:
            return r.read(), dict(r.headers)
    except error.HTTPError as e:
        msg = e.read()[:500]
        hint = ""
        if b"missing_permissions" in msg:
            hint = "\n  → edit the API key in ElevenLabs and enable the permission named above (key value stays the same)"
        sys.exit(f"elevenlabs {method} {path}: HTTP {e.code} {msg!r}{hint}")


def log_usage(rec: dict) -> None:
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    rec["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with USAGE.open("a") as f:
        f.write(json.dumps(rec) + "\n")


# ---------------- commands ----------------
def whoami():
    raw, _ = call("GET", "/v1/user/subscription")
    d = json.loads(raw)
    keys = ("tier", "character_count", "character_limit", "can_use_instant_voice_cloning", "next_character_count_reset_unix")
    print(json.dumps({k: d.get(k) for k in keys}, indent=1))


def prep(src: str, out: str, start: float | None, end: float | None):
    """IVC sample spec (ElevenLabs docs): single clean speaker, MP3 >=192 kbps, RMS about -23..-18 dB, true peak -3 dB.
    Long pauses are trimmed (cloning learns voice, not silence). 1-2 min ideal; less works but is weaker."""
    o = Path(out)
    o.parent.mkdir(parents=True, exist_ok=True)
    cut = (["-ss", str(start)] if start is not None else []) + (["-to", str(end)] if end is not None else [])
    af = ("highpass=f=60,silenceremove=start_periods=1:start_threshold=-45dB:stop_periods=-1:stop_duration=0.6:"
          "stop_threshold=-45dB,loudnorm=I=-20:TP=-3:LRA=9")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *cut, "-i", src, "-vn", "-af", af, "-ac", "1", "-ar", "44100",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(o)], check=True)
    d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(o)]))
    print(f"{o} ({d:.1f}s){'  ⚠ under 60 s: IVC works but 1-2 min is ideal' if d < 60 else ''}")


def clone(sample: str, name: str):
    b = "----el" + uuid.uuid4().hex
    parts = []
    for k, v in (("name", name), ("description", "Owner's own voice, cloned with consent for their Upwork videos"),
                 ("remove_background_noise", "false")):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    mime = "audio/mpeg" if sample.endswith(".mp3") else "audio/wav"
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="files"; filename="{Path(sample).name}"\r\n'
                 f"Content-Type: {mime}\r\n\r\n".encode() + Path(sample).read_bytes() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    raw, _ = call("POST", "/v1/voices/add", b"".join(parts), f"multipart/form-data; boundary={b}")
    vid = json.loads(raw)["voice_id"]
    VOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    VOICE_FILE.write_text(json.dumps({"voice_id": vid, "name": name, "sample": sample,
                                      "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=1) + "\n")
    log_usage({"op": "clone", "voice_id": vid, "chars": 0})
    print(vid)


def words_from_alignment(text: str, al: dict) -> list[dict]:
    """Character timings → word timings (same {w,s,e} format as our Whisper transcripts, so captions just work)."""
    chars, st, en = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, s0, e0 = [], "", None, None
    for c, s, e in zip(chars, st, en):
        if c.isspace():
            if cur:
                words.append({"w": cur, "s": s0, "e": e0})
            cur, s0 = "", None
            continue
        if s0 is None:
            s0 = s
        cur += c
        e0 = e
    if cur:
        words.append({"w": cur, "s": s0, "e": e0})
    return words


def say(voice: str, lines: dict, out: str, model: str, settings: dict, takes: int, seed0: int, max_chars: int,
        dry: bool, stitch: bool):
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    rate = CREDIT_PER_CHAR.get(model, 1.0)
    need = sum(len(t) for t in lines.values()) * takes
    print(f"{len(lines)} lines × {takes} take(s) = {need} chars ≈ {need * rate:.0f} credits on {model}")
    if need > max_chars:
        sys.exit(f"refusing: {need} chars > --max-chars {max_chars} (raise it deliberately)")
    if dry:
        return
    prev_ids: list[str] = []
    spent = 0
    for name, text in lines.items():
        for k in range(takes):
            seed = seed0 + k
            body = {"text": text, "model_id": model, "voice_settings": settings, "seed": seed,
                    "apply_text_normalization": "auto"}
            if stitch and prev_ids and model != "eleven_v3":
                body["previous_request_ids"] = prev_ids[-3:]
            key = hashlib.sha256(json.dumps([voice, body], sort_keys=True).encode()).hexdigest()[:20]
            hit = CACHE / f"{key}.json"
            if hit.exists():
                d = json.loads(hit.read_text())
                print(f"  {name}_t{k}: cache hit (0 credits)")
            else:
                raw, hdr = call("POST", f"/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128",
                                json.dumps(body).encode(), "application/json")
                d = json.loads(raw)
                d["request_id"] = hdr.get("request-id") or hdr.get("Request-Id") or ""
                hit.write_text(json.dumps(d))
                spent += len(text)
                log_usage({"op": "tts", "model": model, "chars": len(text), "credits": len(text) * rate,
                           "line": name, "take": k, "voice_id": voice})
                print(f"  {name}_t{k}: {len(text)} chars")
            (o / f"{name}_t{k}.mp3").write_bytes(base64.b64decode(d["audio_base64"]))
            al = d.get("normalized_alignment") or d.get("alignment")
            if al:
                (o / f"{name}_t{k}.align.json").write_text(json.dumps({"text": text, "words": words_from_alignment(text, al)}, indent=1))
            if k == 0 and d.get("request_id"):
                prev_ids.append(d["request_id"])
    print(f"done: {spent} chars billed ≈ {spent * rate:.0f} credits this run (see `usage`)")


def usage():
    if not USAGE.exists():
        print("no usage yet")
        return
    recs = [json.loads(x) for x in USAGE.read_text().splitlines() if x.strip()]
    by = {}
    for r in recs:
        by.setdefault(r.get("model", r["op"]), [0, 0.0])
        by[r.get("model", r["op"])][0] += r.get("chars", 0)
        by[r.get("model", r["op"])][1] += r.get("credits", 0)
    tot = sum(v[1] for v in by.values())
    for m, (c, cr) in by.items():
        print(f"{m:<26} {c:>7} chars  {cr:>8.0f} credits")
    print(f"{'TOTAL':<26} {'':>7}        {tot:>8.0f} credits  (Starter plan = 30,000/month)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami")
    sub.add_parser("usage")
    p = sub.add_parser("prep")
    p.add_argument("src")
    p.add_argument("--out", default=str(ROOT / "assets" / "voice" / "ivc_sample.mp3"))
    p.add_argument("--start", type=float)
    p.add_argument("--end", type=float)
    c = sub.add_parser("clone")
    c.add_argument("sample")
    c.add_argument("--name", default="Owner clone")
    s = sub.add_parser("say")
    s.add_argument("--voice")
    s.add_argument("--line", action="append", default=[], help="name=text")
    s.add_argument("--job", help='JSON {"lines": {name: text}, "settings": {...}}')
    s.add_argument("--out", required=True)
    s.add_argument("--model")
    s.add_argument("--draft", action="store_true", help="Flash v2.5 at half the credits")
    s.add_argument("--takes", type=int, default=1)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--max-chars", type=int, default=4000)
    s.add_argument("--no-stitch", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    for k in ("stability", "similarity_boost", "style", "speed"):
        s.add_argument("--" + k.replace("_", "-"), type=float)
    a = ap.parse_args()
    if a.cmd == "whoami":
        whoami()
    elif a.cmd == "usage":
        usage()
    elif a.cmd == "prep":
        prep(a.src, a.out, a.start, a.end)
    elif a.cmd == "clone":
        clone(a.sample, a.name)
    else:
        voice = a.voice or json.loads(VOICE_FILE.read_text())["voice_id"]
        lines, settings = {}, dict(DEFAULT_SETTINGS)
        if a.job:
            j = json.loads(Path(a.job).read_text())
            lines.update(j["lines"])
            settings.update(j.get("settings", {}))
        lines.update(dict(x.split("=", 1) for x in a.line))
        for k in ("stability", "similarity_boost", "style", "speed"):
            v = getattr(a, k)
            if v is not None:
                settings[k] = v
        model = a.model or (MODELS["draft"] if a.draft else MODELS["final"])
        say(voice, lines, a.out, model, settings, a.takes, a.seed, a.max_chars, a.dry_run, not a.no_stitch)


if __name__ == "__main__":
    main()
