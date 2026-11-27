#!/usr/bin/env python3
"""sync.so lane: lip-sync the owner's REAL footage to a new voice line (e.g. their ElevenLabs clone).

    python3 -m lane.syncso estimate --model sync-3 --seconds 11.4          # price + free-tier admission (no spend)
    python3 -m lane.syncso lipsync --video clip.mp4 --audio line.mp3 --out out.mp4 [--model sync-3]
                                   [--sync-mode cut_off] [--max-usd 0] [--yes]

API (from the official SDK `syncsdk` 0.5.0): base https://api.sync.so, header `x-api-key` (network secret injected by
the proxy; we send a placeholder). `POST /v2/generate` multipart: fields model + options (JSON string) + files
video/audio. Poll `GET /v2/generate/{id}` → status PENDING|PROCESSING|COMPLETED|FAILED|REJECTED, `outputUrl`.
Estimate: `POST /v2/generations/estimate` {model, duration} → estimatedGenerationCost (USD), durationCheck.limit,
admission {limit, used} (free tier: 3 generations/month, ≤ 15 s each, on 2026-11-27).
Models: sync-3 (best, $0.16/s) · lipsync-2-pro ($0.10/s) · lipsync-2 ($0.06/s).

Spend guard: a run is refused unless it's free-tier-admitted OR its estimate ≤ --max-usd (default 0 = free only).
Every call is logged to reports/syncso-usage.jsonl.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request

API = "https://api.sync.so"
ROOT = Path(__file__).resolve().parent.parent
USAGE = ROOT / "reports" / "syncso-usage.jsonl"
HDR = {"x-api-key": "proxy-injected"}


def call(method, path, body=None, ctype=None):
    h = dict(HDR, Accept="application/json")
    if ctype:
        h["Content-Type"] = ctype
    req = request.Request(API + path, data=body, method=method, headers=h)
    try:
        with request.urlopen(req, timeout=600) as r:
            return json.loads(r.read() or b"{}")
    except error.HTTPError as e:
        sys.exit(f"sync.so {method} {path}: HTTP {e.code} {e.read()[:600]!r}")


def log(rec):
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    rec["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with USAGE.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def duration(path: str) -> float:
    import subprocess
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]))


def estimate(model: str, seconds: float) -> dict:
    return call("POST", "/v2/generations/estimate", json.dumps({"model": model, "duration": round(seconds, 2)}).encode(),
                "application/json")


def lipsync(video: str, audio: str, out: str, model: str, sync_mode: str, max_usd: float, yes: bool, temperature):
    secs = min(duration(video), duration(audio)) if sync_mode == "cut_off" else duration(audio)
    est = estimate(model, secs)
    adm, dc = est.get("admission") or {}, est.get("durationCheck") or {}
    cost = est.get("estimatedGenerationCost")
    free_ok = adm.get("allowed") and adm.get("used", 0) < adm.get("limit", 0)
    print(f"{model}: {secs:.2f}s ≈ ${cost} | duration limit {dc.get('limit')}s | free generations used "
          f"{adm.get('used')}/{adm.get('limit')}")
    if not dc.get("allowed", True):
        sys.exit(f"refusing: {secs:.1f}s exceeds this plan's {dc.get('limit')}s limit per generation (split the clip)")
    if not free_ok and (cost is None or cost > max_usd):
        sys.exit(f"refusing: not free-tier-admitted and ${cost} > --max-usd {max_usd}")
    if not yes:
        sys.exit("dry run OK. Add --yes to generate.")
    b = "----sync" + uuid.uuid4().hex
    parts = []
    opts = {"sync_mode": sync_mode}
    if temperature is not None:
        opts["temperature"] = temperature
    for k, v in (("model", model), ("options", json.dumps(opts)), ("outputFileName", Path(out).stem)):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for field, p, mime in (("video", video, "video/mp4"), ("audio", audio, "audio/mpeg" if audio.endswith(".mp3") else "audio/wav")):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{field}"; filename="{Path(p).name}"\r\n'
                     f"Content-Type: {mime}\r\n\r\n".encode() + Path(p).read_bytes() + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    g = call("POST", "/v2/generate", b"".join(parts), f"multipart/form-data; boundary={b}")
    gid = g["id"]
    log({"op": "generate", "id": gid, "model": model, "seconds": round(secs, 2), "est_usd": cost, "free": bool(free_ok)})
    print("generation", gid, g.get("status"), flush=True)
    t0 = time.time()
    while True:
        time.sleep(8)
        g = call("GET", f"/v2/generate/{gid}")
        st = g.get("status")
        print(f"  [{int(time.time() - t0)}s] {st}", flush=True)
        if st in ("COMPLETED", "FAILED", "REJECTED", "NO_OP"):
            break
        if time.time() - t0 > 1500:
            sys.exit(f"timeout; check later: GET /v2/generate/{gid}")
    log({"op": "result", "id": gid, "status": st, "error": g.get("errorCode") or g.get("error")})
    if st != "COMPLETED":
        sys.exit(f"generation {st}: {g.get('errorCode')} {g.get('error')}")
    url = g["outputUrl"]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    try:
        with request.urlopen(request.Request(url), timeout=600) as r:
            Path(out).write_bytes(r.read())
    except Exception as e:
        sys.exit(f"download failed ({e}); output host may need allowlisting: {url.split('/')[2]} | id {gid}")
    print("wrote", out, f"({g.get('outputDuration')}s)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate")
    e.add_argument("--model", default="sync-3")
    e.add_argument("--seconds", type=float, required=True)
    l = sub.add_parser("lipsync")
    l.add_argument("--video", required=True)
    l.add_argument("--audio", required=True)
    l.add_argument("--out", required=True)
    l.add_argument("--model", default="sync-3")
    l.add_argument("--sync-mode", default="cut_off", help="cut_off|loop|bounce|silence|remap")
    l.add_argument("--temperature", type=float)
    l.add_argument("--max-usd", type=float, default=0.0)
    l.add_argument("--yes", action="store_true")
    g = sub.add_parser("status")
    g.add_argument("id")
    a = ap.parse_args()
    if a.cmd == "estimate":
        print(json.dumps(estimate(a.model, a.seconds), indent=1))
    elif a.cmd == "status":
        print(json.dumps(call("GET", f"/v2/generate/{a.id}"), indent=1))
    else:
        lipsync(a.video, a.audio, a.out, a.model, a.sync_mode, a.max_usd, a.yes, a.temperature)


if __name__ == "__main__":
    main()
