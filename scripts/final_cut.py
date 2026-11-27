#!/usr/bin/env python3
"""Final-cut lab: send a finished master to Kaggle (2x T4, jobs/final-cut), then gate the measurements and write a
review report. Every setting comes from templates/production.json -> final_cut (owner rule: config only).

    python3 scripts/final_cut.py exports/01_n8n_automation_v6.mp4 --kind promo --spec scripts/videos/01_n8n_v6.json
    python3 scripts/final_cut.py exports/trip_greece.mp4 --kind trip --storyline trips/greece/storyline.json
    python3 scripts/final_cut.py <master> --kind promo --spec ... --collect      # re-gate the last Kaggle run, no GPU

Outputs: reports/final-cut/<id>.json + <id>.md (verdict per check), and when the face-detail touch-up ran:
exports/<id>_touched.mp4 + previews/<id>_side_by_side{,_face}.mp4. The touched cut is a CANDIDATE: it never
replaces the master (final_cut.touchup.auto_replace_master=false); the owner picks by eye.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOB = ROOT / "jobs" / "final-cut"
KOUT = ROOT / "kaggle" / "outputs" / "kgpu-final-cut" / "out"


def cfg_get(cfg: dict, dotted: str):
    v = cfg
    for k in dotted.split("."):
        v = v[k]
    return v


def build_manifest(cfg: dict, kind: str, mid: str, expected: str | None) -> dict:
    fc = cfg["final_cut"]
    chk = json.loads(json.dumps(fc["checks"]))
    qg = cfg["lipsync"]["quality_gate"]
    chk["loudness"]["target_lufs"] = cfg_get(cfg, fc["checks"]["loudness"]["target_lufs_from"])
    chk["loudness"]["true_peak_max_db"] = cfg_get(cfg, fc["checks"]["loudness"]["true_peak_max_db_from"])
    chk["lipsync"]["min_lse_c"] = round(qg["min_lse_c_vs_sync3"] * qg["baselines_2026_11_27"]["sync3_hookcta"]["lse_c"], 3)
    tu = json.loads(json.dumps(fc["touchup"]))
    fd = tu["face_detail"]
    fd["enabled"] = bool(fd["enabled"] and kind in fd["applies_to"])
    iq = cfg["inference_optimization"]["quality_gate"]
    fd["gate"]["face_ssim_min"] = iq["ssim_min"]
    fd["gate"]["syncnet_lse_c_drop_max_pct"] = iq["syncnet_lse_c_drop_max_pct"]
    return {"id": mid, "kind": kind, "language": "en", "expected_text": expected, "checks": chk, "touchup": tu}


def expected_from_spec(spec_path: Path) -> str:
    spec = json.loads(spec_path.read_text())
    parts = []
    for seg in spec["segments"]:
        if seg.get("vo"):
            al = ROOT / spec["vo_dir"] / f"{seg['vo']}.align.json"
            words = json.loads(al.read_text())["words"]
            f0, f1 = seg.get("vo_from", 0.0), seg.get("vo_to", 1e9)
            parts.append(" ".join(w["w"] for w in words if f0 - 0.01 <= w["s"] < f1))
    return " ".join(parts)


def expected_from_storyline(sl_path: Path) -> str:
    sl = json.loads(sl_path.read_text())
    return " ".join(s["narration"] for s in sl["scenes"] if s.get("narration"))


def norm(t: str) -> list[str]:
    t = t.lower().replace("&", " and ").replace("-", " ")
    return re.findall(r"[a-z0-9']+", t)


def wer(ref: list[str], hyp: list[str]) -> tuple[float, list[str]]:
    """Word error rate + a readable list of the differences (Levenshtein alignment)."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    i, j, diffs = n, m, []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            if ref[i - 1] != hyp[j - 1]:
                diffs.append(f"'{ref[i - 1]}' heard as '{hyp[j - 1]}'")
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            diffs.append(f"missing '{ref[i - 1]}'")
            i -= 1
        else:
            diffs.append(f"extra '{hyp[j - 1]}'")
            j -= 1
    return (d[n][m] / max(n, 1)), diffs[::-1]


def gate(man: dict, out: Path) -> dict:
    """Turn the raw Kaggle measurements into pass/warn/fail per check. Pure CPU, re-runnable."""
    chk = man["checks"]
    lab = json.loads((out / "lab.json").read_text())
    words = json.loads((out / "words.json").read_text()) if (out / "words.json").exists() else None
    res: dict = {"id": man["id"], "kind": man["kind"], "info": lab["info"], "checks": {},
                 "gpu": {"lanes": lab.get("lanes"), "util": lab.get("gpu_util"), "total_s": lab.get("total_s")}}
    C = res["checks"]
    dur = lab["info"]["duration"]

    L = lab.get("loudness")
    if L:
        lc = chk["loudness"]
        ok = abs(L["integrated_lufs"] - lc["target_lufs"]) <= lc["tolerance_lu"] and L["true_peak_db"] <= lc["true_peak_max_db"]
        C["loudness"] = {"status": "pass" if ok else "fail", **L, "target_lufs": lc["target_lufs"],
                         "true_peak_max_db": lc["true_peak_max_db"]}

    ign = chk["black"]["ignore_head_tail_s"]
    bl = [b for b in lab["black"] if b["start"] > ign and b["end"] < dur - ign]
    C["black"] = {"status": "fail" if bl else "pass", "segments": bl}
    C["freeze"] = {"status": "warn" if lab["freeze"] else "pass", "segments": lab["freeze"],
                   "note": "warn only: check each is an intended hold"}

    if words:
        low = [w for w in words["words"] if w["p"] < chk["transcript"]["low_confidence_below"]]
        tr = {"heard": words["text"], "low_confidence": [f"{w['w']} @{w['s']:.2f}s p={w['p']}" for w in low]}
        if man.get("expected_text"):
            e, diffs = wer(norm(man["expected_text"]), norm(words["text"]))
            tr.update(wer=round(e, 3), max_wer=chk["transcript"]["max_wer"], differences=diffs,
                      status="pass" if e <= chk["transcript"]["max_wer"] else "fail")
        else:
            tr["status"] = "warn" if low else "pass"
            tr["note"] = "no expected script given: transcript only"
        C["transcript"] = tr

    sm = out / "syncnet_master.json"
    tracks = json.loads(sm.read_text())["tracks"] if sm.exists() else []
    if man["kind"] in chk["lipsync"]["applies_to"]:
        lc = chk["lipsync"]
        rows = []
        for t in tracks:
            ok = t["lse_c"] is not None and t["lse_c"] >= lc["min_lse_c"] and abs(t["offset"] or 0) <= lc["max_abs_offset_frames"]
            rows.append({**t, "status": "pass" if ok else "fail"})
        C["lipsync"] = {"status": ("fail" if any(r["status"] == "fail" for r in rows) else "pass") if rows else "warn",
                        "min_lse_c": lc["min_lse_c"], "tracks": rows,
                        "note": lc["note"] if not rows else "one row per face shot >= 4 s"}

    if man["kind"] in chk["cut_while_talking"]["applies_to"] and words:
        gap = chk["cut_while_talking"]["word_gap_s"]
        ws = words["words"]
        bad = []
        for c in lab["cuts"]:
            t = c["t"]
            inside = any(w["s"] < t < w["e"] for w in ws) or any(
                a["e"] <= t <= b["s"] and b["s"] - a["e"] < gap for a, b in zip(ws, ws[1:]))
            # the rule is about cutting AWAY from the face: the shot before the cut must be a face shot
            # (track ends at the cut, or the cut lands inside a track). Cutting INTO the face mid-word is a J-cut.
            away = any(abs(tr["end"] - t) <= 0.5 or tr["start"] + 0.5 < t < tr["end"] - 0.5 for tr in tracks)
            if inside and away:
                bad.append(round(t, 2))
        C["cut_while_talking"] = {"status": "fail" if bad else "pass", "cuts_away_mid_phrase": bad,
                                  "cuts_total": len(lab["cuts"]),
                                  "note": "" if tracks else "no face tracks scored; face proximity unknown"}

    tj = out / "touchup.json"
    if man["touchup"]["face_detail"]["enabled"] and tj.exists():
        tu = json.loads(tj.read_text())
        g = man["touchup"]["face_detail"]["gate"]
        st = out / "syncnet_touched.json"
        tt = json.loads(st.read_text())["tracks"] if st.exists() else []
        drops = []
        for a in tracks:
            b = max(tt, key=lambda x: min(a["end"], x["end"]) - max(a["start"], x["start"]), default=None)
            if a["lse_c"] and b and b["lse_c"] is not None:
                drops.append({"start": a["start"], "end": a["end"], "master": a["lse_c"], "touched": b["lse_c"],
                              "drop_pct": round(100 * (a["lse_c"] - b["lse_c"]) / a["lse_c"], 2)})
        ssim_ok = tu["face_ssim_p05"] is not None and tu["face_ssim_p05"] >= g["face_ssim_min"]
        sync_ok = all(d["drop_pct"] <= g["syncnet_lse_c_drop_max_pct"] for d in drops)
        C["touchup_face_detail"] = {
            "status": "candidate" if (ssim_ok and sync_ok and tu["frames_touched"]) else "rejected",
            "frames_touched": tu["frames_touched"], "frames": tu["frames"], "blend": tu["blend"],
            "face_ssim_mean": tu["face_ssim_mean"], "face_ssim_p05": tu["face_ssim_p05"],
            "face_ssim_min_required": g["face_ssim_min"], "syncnet": drops,
            "syncnet_drop_max_pct": g["syncnet_lse_c_drop_max_pct"], "gpu_s": tu["seconds"],
            "note": "candidate = passed the numbers; the owner's eye decides (side-by-side in previews/)"}

    hard = [k for k, v in C.items() if v.get("status") == "fail"]
    res["verdict"] = "FAIL: " + ", ".join(hard) if hard else "PASS (owner's eye still final)"
    return res


GPT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["frames", "overall"],
    "properties": {
        "frames": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                   "required": ["file", "verdict", "tells"],
                   "properties": {"file": {"type": "string"}, "verdict": {"enum": ["looks_real", "unsure", "likely_ai"]},
                                  "tells": {"type": "array", "items": {"type": "string"}}}}},
        "overall": {"type": "string"}}}


def gpt_review(cfg: dict, sheet: Path, kind: str) -> dict:
    """realism_gate 'AI-tell review': ChatGPT vision (owner's plan via lane/chatgpt.py) looks at the contact sheet."""
    sys.path.insert(0, str(ROOT))
    from lane import chatgpt
    st = chatgpt.status()
    if not st.get("logged_in"):
        return {"status": "skipped", "note": f"ChatGPT lane not ready: {st}"}
    imgs = sorted(sheet.glob("*.jpg"))
    rules = cfg["realism_gate"]["checks"][2]
    prompt = (f"You are the final-cut reviewer for a {kind} video that must look completely real. {rules}. "
              f"For each attached frame (file names in order: {', '.join(i.name for i in imgs)}) say looks_real, unsure "
              "or likely_ai and list concrete tells (warped hands/text, waxy skin, melting background, odd mouth, "
              "identity change, over-sharpening, halos). Text overlays and captions are intended graphics, not tells.")
    schema = ROOT / "kaggle" / "build" / "final-cut-gpt-schema.json"
    schema.write_text(json.dumps(GPT_SCHEMA))
    try:
        r = chatgpt.ask(prompt, images=[str(i) for i in imgs], schema=str(schema))
    except Exception as e:  # never block the report on the review lane
        return {"status": "skipped", "note": f"{e.__class__.__name__}: {e}"[:300]}
    d = r["data"]
    bad = [f for f in d["frames"] if f["verdict"] == "likely_ai"]
    return {"status": "fail" if bad else ("warn" if any(f["verdict"] == "unsure" for f in d["frames"]) else "pass"),
            "model": r.get("model"), "overall": d["overall"], "flagged": bad + [f for f in d["frames"] if f["verdict"] == "unsure"]}


def write_md(res: dict, path: Path) -> None:
    C = res["checks"]
    L = [f"# Final-cut lab: {res['id']} ({res['kind']})", "", f"**Verdict: {res['verdict']}**", "",
         f"{res['info']['width']}x{res['info']['height']} @ {res['info']['fps']} fps, {res['info']['duration']:.2f} s", "",
         "| Check | Status | Detail |", "|---|---|---|"]
    if "loudness" in C:
        c = C["loudness"]
        L.append(f"| Loudness | {c['status']} | {c['integrated_lufs']} LUFS (target {c['target_lufs']}), true peak "
                 f"{c['true_peak_db']} dB (max {c['true_peak_max_db']}) |")
    if "transcript" in C:
        c = C["transcript"]
        d = f"WER {c['wer']:.1%} (max {c['max_wer']:.0%})" if "wer" in c else c.get("note", "")
        if c.get("differences"):
            d += "; " + "; ".join(c["differences"][:8])
        L.append(f"| Script vs what is heard | {c['status']} | {d} |")
    if "lipsync" in C:
        c = C["lipsync"]
        rows = ", ".join(f"{t['start']:.1f}-{t['end']:.1f}s LSE-C {t['lse_c']} off {t['offset']}" for t in c["tracks"]) or c["note"]
        L.append(f"| Lip-sync (SyncNet, min {c['min_lse_c']}) | {c['status']} | {rows} |")
    if "cut_while_talking" in C:
        c = C["cut_while_talking"]
        L.append(f"| No cut while talking | {c['status']} | {len(c['cuts_away_mid_phrase'])} bad of {c['cuts_total']} cuts "
                 f"{c['cuts_away_mid_phrase'] or ''} {c['note']} |")
    L.append(f"| Black frames | {C['black']['status']} | {C['black']['segments'] or 'none'} |")
    L.append(f"| Freezes | {C['freeze']['status']} | {C['freeze']['segments'] or 'none'} |")
    if "ai_tell_review" in C:
        c = C["ai_tell_review"]
        det = c.get("overall") or c.get("note", "")
        if c.get("flagged"):
            det += "; " + "; ".join(f"{f['file']}: {', '.join(f['tells'])}" for f in c["flagged"][:6])
        L.append(f"| AI-tell review (ChatGPT vision) | {c['status']} | {det} |")
    if "touchup_face_detail" in C:
        c = C["touchup_face_detail"]
        sy = ", ".join(f"{d['start']:.1f}s {d['master']}→{d['touched']} ({d['drop_pct']:+.1f}%)" for d in c["syncnet"])
        L.append(f"| Touch-up: face detail (blend {c['blend']}) | {c['status']} | {c['frames_touched']}/{c['frames']} frames; "
                 f"face SSIM p05 {c['face_ssim_p05']} (min {c['face_ssim_min_required']}); SyncNet drop {sy or 'n/a'} |")
    if C.get("transcript", {}).get("low_confidence"):
        L += ["", "Low-confidence words (check by ear): " + ", ".join(C["transcript"]["low_confidence"][:20])]
    g = res["gpu"]
    if g.get("util"):
        L += ["", "Kaggle 2x T4: " + "; ".join(f"{k} mean util {v['mean_util_pct']}%, busy {v['busy_pct']}% of samples, "
                                              f"peak {v['peak_mem_mb']} MB" for k, v in g["util"].items())
              + f"; lanes {json.dumps(g['lanes'])}; session {g['total_s']} s"]
    path.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("master")
    ap.add_argument("--kind", required=True, choices=["promo", "trip"])
    ap.add_argument("--spec", help="promo spec (expected script from its align.json files)")
    ap.add_argument("--storyline", help="trip storyline.json (expected narration)")
    ap.add_argument("--expect", help="plain-text file with the expected script")
    ap.add_argument("--id")
    ap.add_argument("--collect", action="store_true", help="don't run on Kaggle; re-gate the last downloaded run")
    ap.add_argument("--no-gpt", action="store_true", help="skip the ChatGPT-vision AI-tell review of the contact sheet")
    a = ap.parse_args()

    cfg = json.loads((ROOT / "templates" / "production.json").read_text())
    if not cfg["final_cut"]["enabled"]:
        sys.exit("final_cut disabled in templates/production.json")
    master = Path(a.master).resolve()
    mid = a.id or master.stem
    expected = (expected_from_spec(ROOT / a.spec) if a.spec else
                expected_from_storyline(ROOT / a.storyline) if a.storyline else
                Path(a.expect).read_text() if a.expect else None)
    man = build_manifest(cfg, a.kind, mid, expected)

    if not a.collect:
        bundle = ROOT / "kaggle" / "build" / "final-cut-input" / mid
        shutil.rmtree(bundle, ignore_errors=True)
        bundle.mkdir(parents=True)
        shutil.copy2(master, bundle / "master.mp4")
        (bundle / "manifest.json").write_text(json.dumps(man, indent=1))
        subprocess.run([str(ROOT / "bin" / "kgpu"), "run", str(JOB), "--input", str(bundle),
                        "--timeout-min", str(cfg["final_cut"]["timeout_min"])], check=True)

    res = gate(man, KOUT)
    if cfg["final_cut"]["checks"]["contact_sheet"].get("gpt_review") and not a.no_gpt:
        res["checks"]["ai_tell_review"] = gpt_review(cfg, KOUT / "sheet", a.kind)
        if res["checks"]["ai_tell_review"]["status"] == "fail":
            res["verdict"] = ("FAIL: " if res["verdict"].startswith("PASS") else res["verdict"] + ", ") + "ai_tell_review"
    rep = ROOT / "reports" / "final-cut"
    rep.mkdir(parents=True, exist_ok=True)
    (rep / f"{mid}.json").write_text(json.dumps(res, indent=1))
    write_md(res, rep / f"{mid}.md")
    if (KOUT / "touched.mp4").exists():
        shutil.copy2(KOUT / "touched.mp4", ROOT / "exports" / f"{mid}_touched.mp4")
        for s in ("side_by_side", "side_by_side_face"):
            if (KOUT / f"{s}.mp4").exists():
                (ROOT / "previews").mkdir(exist_ok=True)
                shutil.copy2(KOUT / f"{s}.mp4", ROOT / "previews" / f"{mid}_{s}.mp4")
    print((rep / f"{mid}.md").read_text())


if __name__ == "__main__":
    main()
