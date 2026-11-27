#!/usr/bin/env python3
"""Client for our own Modal lip-sync API (modal_apps/lipsync_web.py), over plain HTTPS.

    python3 -m lane.modal_lipsync health
    python3 -m lane.modal_lipsync download [--variants student,teacher]          # CPU, fills the weights Volume
    python3 -m lane.modal_lipsync wait <call_id>
    python3 -m lane.modal_lipsync lipsync --video face.mp4 --audio voice.mp3 --out out.mp4 [--mode student|teacher]

Auth: `x-api-key` is a network secret injected by the proxy (we send a placeholder). Costs are logged to
reports/modal-usage.jsonl (GPU seconds × L40S rate, reported by the worker). Free credits: $30/month.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from urllib import error, request

API = "https://nubuqqrr--video-system-lipsync-api.us-east.modal.run"
ROOT = Path(__file__).resolve().parent.parent
USAGE = ROOT / "reports" / "modal-usage.jsonl"


def call(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(API + path, data=data, method=method,
                          headers={"x-api-key": "proxy-injected", "Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except error.HTTPError as e:
        sys.exit(f"{method} {path}: HTTP {e.code} {e.read()[:400]!r}")


def wait(call_id: str, every: float = 10, limit: float = 3600) -> dict:
    t0 = time.time()
    while True:
        r = call("GET", f"/result/{call_id}", timeout=60)
        if r.get("status") != "running":
            return r
        if time.time() - t0 > limit:
            sys.exit(f"timeout waiting for {call_id}")
        print(f"  [{int(time.time() - t0)}s] running", flush=True)
        time.sleep(every)


def log(rec):
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    rec["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with USAGE.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    d = sub.add_parser("download")
    d.add_argument("--variants", default="student,teacher")
    w = sub.add_parser("wait")
    w.add_argument("call_id")
    l = sub.add_parser("lipsync")
    l.add_argument("--video", required=True)
    l.add_argument("--audio", required=True)
    l.add_argument("--out", required=True)
    l.add_argument("--mode", default="student")
    wn = sub.add_parser("wan", help="Wan 2.2 image/text-to-video")
    wn.add_argument("--prompt", required=True)
    wn.add_argument("--image")
    wn.add_argument("--model", default="ti2v-5B", choices=["ti2v-5B", "i2v-A14B"])
    wn.add_argument("--size")
    wn.add_argument("--frame-num", type=int)
    wn.add_argument("--steps", type=int)
    wn.add_argument("--seed", type=int, default=42)
    wn.add_argument("--out", required=True)
    sub.add_parser("fastwan-download", help="one-time: FastWan2.2-TI2V-5B weights → Modal volume")
    fw = sub.add_parser("fastwan", help="FastWan batch: one GPU session animates every item")
    fw.add_argument("--items", required=True,
                    help='JSON file: [{"image","prompt","out","seconds"?,"seed"?,"orient"?,"focus_x"?,"focus_y"?}]')
    fw.add_argument("--steps", type=int, default=3)
    fw.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()
    if a.cmd == "fastwan-download":
        cid = call("POST", "/fastwan/download", {})["call_id"]
        print("call", cid, flush=True)
        r = wait(cid, every=20, limit=3600)
        print(json.dumps(r, indent=1)[:2000])
        return
    if a.cmd == "fastwan":
        items = json.loads(Path(a.items).read_text())
        body = {"steps": a.steps, "fps": a.fps, "items": []}
        for it in items:
            b = {k: v for k, v in it.items() if k not in ("image", "out")}
            b["image_b64"] = base64.b64encode(Path(it["image"]).read_bytes()).decode()
            body["items"].append(b)
        cid = call("POST", "/fastwan/batch", body, timeout=300)["call_id"]
        print("call", cid, flush=True)
        r = wait(cid, every=20, limit=3600)
        log({"op": "fastwan", "n": len(items), "steps": a.steps, "call_id": cid, "ok": r.get("ok"),
             "load_seconds": r.get("load_seconds"), "gpu_seconds": r.get("gpu_seconds"), "usd": r.get("usd")})
        if not r.get("ok"):
            print(str(r.get("log", r))[-3000:])
            sys.exit("fastwan failed")
        for it, res in zip(items, r["items"]):
            Path(it["out"]).parent.mkdir(parents=True, exist_ok=True)
            Path(it["out"]).write_bytes(base64.b64decode(res["video_b64"]))
            print(f"wrote {it['out']}  {res['frames']} frames  {res['seconds']}s")
        print(f"batch: load {r.get('load_seconds')}s, gpu {r.get('gpu_seconds')}s ≈ ${r.get('usd')}")
        return
    if a.cmd == "wan":
        body = {"model": a.model, "prompt": a.prompt, "seed": a.seed}
        if a.image:
            body["image_b64"] = base64.b64encode(Path(a.image).read_bytes()).decode()
        for k, v in (("size", a.size), ("frame_num", a.frame_num), ("steps", a.steps)):
            if v:
                body[k] = v
        cid = call("POST", "/wan/generate", body, timeout=300)["call_id"]
        print("call", cid, flush=True)
        r = wait(cid, every=20, limit=3600)
        log({"op": "wan", "model": a.model, "call_id": cid, "ok": r.get("ok"), "gpu_seconds": r.get("gpu_seconds"),
             "usd": r.get("usd")})
        if not r.get("ok"):
            print(r.get("log", "")[-3000:])
            sys.exit("wan failed")
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_bytes(base64.b64decode(r["video_b64"]))
        print(f"wrote {a.out}  gpu {r.get('gpu_seconds')}s ≈ ${r.get('usd')}")
        return
    if a.cmd == "health":
        print(call("GET", "/health"))
    elif a.cmd == "download":
        print(call("POST", "/download", {"variants": a.variants}))
    elif a.cmd == "wait":
        r = wait(a.call_id)
        r.pop("video_b64", None)
        print(json.dumps(r, indent=1)[:3000])
    else:
        body = {"video_b64": base64.b64encode(Path(a.video).read_bytes()).decode(),
                "audio_b64": base64.b64encode(Path(a.audio).read_bytes()).decode(), "mode": a.mode}
        cid = call("POST", "/lipsync", body, timeout=300)["call_id"]
        print("call", cid, flush=True)
        r = wait(cid)
        log({"op": "tbdub", "mode": a.mode, "call_id": cid, "ok": r.get("ok"), "gpu_seconds": r.get("gpu_seconds"),
             "usd": r.get("usd")})
        if not r.get("ok"):
            print(r.get("log", "")[-3000:])
            sys.exit("lipsync failed")
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_bytes(base64.b64decode(r["video_b64"]))
        print(f"wrote {a.out}  gpu {r.get('gpu_seconds')}s ≈ ${r.get('usd')}")


if __name__ == "__main__":
    main()
