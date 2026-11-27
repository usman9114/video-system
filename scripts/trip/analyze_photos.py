#!/usr/bin/env python3
"""Stage 1 of Trip Memories: ChatGPT (owner's plan, vision) analyses every photo, N in parallel, against a JSON schema.

    python3 scripts/trip/analyze_photos.py trips/athens/photos --hint "My trip to Athens, May 2026" [--parallel 5]

Writes trips/<trip>/analysis.json: one entry per photo (EXIF date/GPS + ChatGPT's structured notes).
ChatGPT's place guesses are LEADS: the storyteller must not state uncertain places/facts as fact.
"""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ExifTags

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = Path(__file__).with_name("photo_schema.json")


def exif(p: Path) -> dict:
    try:
        raw = Image.open(p).getexif()
        tags = {ExifTags.TAGS.get(k, k): v for k, v in raw.items()}
        gps = raw.get_ifd(0x8825) if hasattr(raw, "get_ifd") else {}
        def deg(v, ref):
            d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
            return -d if ref in ("S", "W") else d
        latlon = None
        if gps and 2 in gps and 4 in gps:
            latlon = [round(deg(gps[2], gps.get(1, "N")), 5), round(deg(gps[4], gps.get(3, "E")), 5)]
        return {"datetime": str(tags.get("DateTime", "")), "gps": latlon, "size": list(Image.open(p).size)}
    except Exception as e:
        return {"error": str(e)}


def analyse(p: Path, hint: str) -> dict:
    meta = exif(p)
    prompt = (f"You are a travel-documentary researcher. Trip context from the traveller: {hint!r}. "
              f"Photo metadata: {json.dumps(meta)}. Look carefully at the attached photo and fill the JSON schema. "
              "Identify the place only if you are reasonably sure (say 'unknown' otherwise, and set confidence honestly). "
              "Describe people neutrally; never guess names or identities. The animation_prompt must keep every face "
              "and body unchanged and describe only subtle, physically plausible motion (camera, light, crowd, water, flags, foliage).")
    r = subprocess.run([sys.executable, "-m", "lane.chatgpt", "ask", prompt, "--image", str(p), "--schema", str(SCHEMA),
                        "--search", "--json"], cwd=ROOT, capture_output=True, text=True, timeout=600)
    try:
        data = json.loads(r.stdout).get("data")
    except Exception:
        data = None
    return {"photo": str(p.relative_to(ROOT)), "exif": meta, "analysis": data, "error": None if data else (r.stderr or r.stdout)[-500:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("photos_dir")
    ap.add_argument("--hint", required=True)
    ap.add_argument("--parallel", type=int, default=5)
    a = ap.parse_args()
    d = (ROOT / a.photos_dir).resolve()
    photos = sorted([p for p in d.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic", ".webp")])
    with ThreadPoolExecutor(max_workers=a.parallel) as ex:
        res = list(ex.map(lambda p: analyse(p, a.hint), photos))
    out = d.parent / "analysis.json"
    out.write_text(json.dumps({"hint": a.hint, "photos": res}, indent=1))
    ok = sum(1 for r in res if r["analysis"])
    print(f"{ok}/{len(res)} photos analysed → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
