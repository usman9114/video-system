#!/usr/bin/env python3
"""ChatGPT writes, a script checks, ChatGPT fixes: loop a trip storyboard until it passes the hard rules.

  CHATGPT_EFFORT=high python3 scripts/trip/storyboard_loop.py <in.json> <out.json> <rules.json> [--rounds 3]

rules.json: {"words":[min,max], "seconds":[min,max], "wps_max":2.4,
             "subjects":{"keyword":["photo_stem",...]},   # a line naming keyword must play over one of these photos
             "forbidden":["Thistle Chapel"], "facts_file":"trips/x/landmark_facts.md", "notes":"extra direction"}
Checks: total words/seconds, words per line <= wps_max x its shots' seconds, every named subject visible on its
shots, forbidden words, every line has shots, last line is not a fact. Exits 0 when clean.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lane import chatgpt  # noqa: E402


def check(d, R):
    S = {s["n"]: s for s in d["shots"]}
    stem = lambda p: Path(p).stem
    errs = []
    words = sum(len(l["text"].split()) for l in d["lines"])
    secs = sum(s["seconds"] for s in d["shots"])
    if not R["words"][0] <= words <= R["words"][1]:
        errs.append(f"total words {words}, need {R['words'][0]}-{R['words'][1]}")
    if not R["seconds"][0] <= secs <= R["seconds"][1]:
        errs.append(f"total seconds {secs:.1f}, need {R['seconds'][0]}-{R['seconds'][1]}")
    for l in d["lines"]:
        sh = [S[n] for n in l.get("shots", []) if n in S]
        if not sh:
            errs.append(f"L{l['id']} has no valid shots"); continue
        dur, w = sum(s["seconds"] for s in sh), len(l["text"].split())
        if w > R["wps_max"] * dur:
            errs.append(f"L{l['id']}: {w} words over {dur:.1f}s (max {int(R['wps_max'] * dur)}): shorten or add shots")
        photos = {stem(s["photo"]) for s in sh}
        for kw, allowed in R["subjects"].items():
            if re.search(rf"\b{re.escape(kw)}", l["text"], re.I) and not photos & set(allowed):
                errs.append(f"L{l['id']} names '{kw}' but plays over {sorted(photos)}; must be on {allowed}")
        for f in R.get("forbidden", []):
            if f.lower() in l["text"].lower():
                errs.append(f"L{l['id']} mentions '{f}' (not visible in any photo): remove")
    return errs, words, secs


def main():
    src, dst, rules = map(Path, sys.argv[1:4])
    rounds = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else 3
    d, R = json.loads(src.read_text()), json.loads(rules.read_text())
    facts = (ROOT / R["facts_file"]).read_text()[:5000] if R.get("facts_file") else ""
    for k in range(rounds + 1):
        errs, w, s = check(d, R)
        print(f"round {k}: {len(errs)} problem(s), {w} words, {s:.1f}s")
        for e in errs:
            print("   -", e)
        if not errs:
            break
        if k == rounds:
            break
        P = (f"Fix ONLY these problems in the storyboard JSON and return the full corrected JSON (same schema, no prose). "
             f"Keep everything that is not broken. Problems:\n- " + "\n- ".join(errs) +
             f"\nDirection notes: {R.get('notes', '')}\nAllowed facts (only these): {facts}\nStoryboard: {json.dumps(d)}")
        r = chatgpt.ask(P, timeout=1500)["text"]
        d = json.loads(r[r.find("{"):r.rfind("}") + 1])
    dst.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    print("PASS" if not errs else "STILL FAILING", "->", dst)
    sys.exit(0 if not errs else 1)


if __name__ == "__main__":
    main()
