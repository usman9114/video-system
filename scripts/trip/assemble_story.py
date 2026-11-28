#!/usr/bin/env python3
"""Assemble a narrated trip short from a storyboard (crop Ken Burns / Wan gen clips / Seedance clip).

  python3 scripts/trip/assemble_story.py <storyboard.json> <out.mp4> [--work DIR] [--force] [--allow-missing]

Coherence rules (owner 2026-11-28): same-photo consecutive crops never reverse direction (flipped + logged);
only a scene's first shot eases in, every other move stays in motion at its end; hard cuts within a scene, 0.4 s
dissolves at scene changes; first line of each new scene J-cuts 0.5 s before the visual cut; one continuous music bed;
gen/seedance luma matched to neighbouring shots; identical grade/grain/sharpen on everything.
Writes <out>.timeline.json (shot starts/ends, line starts, flips, overruns).
"""
import argparse, hashlib, json, subprocess, sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "trip"))
from music_doc import make_doc  # noqa: E402

W, H, FPS = 1080, 1920, 30
XF, FADE_IN, FADE_OUT, END = 0.4, 0.6, 1.0, 2.5
SCOT = ROOT / "trips" / "scotland"
FONT = ROOT / "assets" / "fonts" / "CormorantGaramond-SemiBold.ttf"
OPP = {"in": "out", "out": "in", "left": "right", "right": "left", "up": "down", "down": "up"}
CAPTIONS = {}


def run(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))


def box_for(crop, push, size):
    Wp, Hp = size
    x0, y0, x1, y1 = crop[0] * Wp, crop[1] * Hp, crop[2] * Wp, crop[3] * Hp
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    if w / h < 9 / 16: w = h * 9 / 16
    else: h = w * 16 / 9
    k = min(1.0, Wp / w, Hp / h)
    w, h = w * k, h * k
    cx = min(max(cx, w / 2), Wp - w / 2); cy = min(max(cy, h / 2), Hp - h / 2)
    return cx, cy, w, h


def render_crop(job):
    photo, crop, push, N, ease_in, out = job
    img = ImageOps.exif_transpose(Image.open(photo)).convert("RGB")
    cx, cy, w, h = box_for(crop, push, img.size)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for i in range(N):
        u = i / max(1, N - 1)
        p = 2 * u * u - u ** 3 if ease_in else u        # ease-in only at scene start; otherwise constant speed, still moving at the cut
        z, dx, dy = 1.0, 0.0, 0.0
        if push == "in": z = 1 + 0.08 * p
        elif push == "out": z = 1.08 - 0.08 * p
        else:
            z = 1.06; s = 0.03 * (1 - 2 * p)
            dx = {"left": s, "right": -s}.get(push, 0) * w
            dy = {"up": s, "down": -s}.get(push, 0) * h
        bw, bh = w / z, h / z
        bx = min(max(cx + dx, bw / 2), img.size[0] - bw / 2); by = min(max(cy + dy, bh / 2), img.size[1] - bh / 2)
        fr = img.resize((W, H), Image.LANCZOS, box=(bx - bw / 2, by - bh / 2, bx + bw / 2, by + bh / 2))
        ff.stdin.write(fr.tobytes())
    ff.stdin.close(); ff.wait()


def render_gen(clip, N, out):
    run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf",
         f"scale={W}:{H}:flags=lanczos,minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:vsbmc=1,tpad=stop_mode=clone:stop_duration=3,setsar=1",
         "-frames:v", str(N), "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", "-an", str(out)])


def render_seed(clip, N, out, xc=0.47):
    cw = 720 * 9 / 16
    x = min(max(xc * 1280 - cw / 2, 0), 1280 - cw)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf",
         f"crop={cw:.2f}:720:{x:.2f}:0,scale={W}:{H}:flags=lanczos,fps={FPS},tpad=stop_mode=clone:stop_duration=3,setsar=1",
         "-frames:v", str(N), "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", "-an", str(out)])


def frame_stats(video, last=False):
    args = ["ffmpeg", "-v", "error"]
    if last: args += ["-sseof", "-0.1"]
    args += ["-i", str(video), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"]
    y = np.asarray(Image.open(__import__("io").BytesIO(subprocess.check_output(args))).convert("L"), np.float32)
    return float(y.mean()), float(y.std())


def font(sz):
    return ImageFont.truetype(str(FONT), sz) if FONT.exists() else ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf", sz)


def spaced(d, xy, text, f, fill, sp, anchor_center=False):
    widths = [d.textlength(c, font=f) + sp for c in text]
    x, y = xy
    if anchor_center: x -= (sum(widths) - sp) / 2
    for c, wd in zip(text, widths):
        d.text((x, y), c, font=f, fill=fill); x += wd


def caption_png(text, path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    a = np.zeros((H, W), np.uint8)
    top = int(H * 0.72)
    ramp = (np.linspace(0, 1, H - top) ** 2 * 130).astype(np.uint8)
    a[top:] = ramp[:, None]
    im.putalpha(Image.fromarray(a))
    d = ImageDraw.Draw(im)
    f = font(50)
    spaced(d, (86, H - 250), text, f, (0, 0, 0, 120), 9)
    spaced(d, (84, H - 252), text, f, (242, 235, 221, 255), 9)
    im.save(path)


def endcard_png(path):
    im = Image.new("RGB", (W, H), (8, 8, 9)); d = ImageDraw.Draw(im)
    spaced(d, (W / 2, H / 2 - 70), "LOOKING UP", font(104), (236, 229, 214), 26, True)
    spaced(d, (W / 2, H / 2 + 80), "Edinburgh · London", font(46), (200, 193, 180), 6, True)
    im.save(path)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("story"); ap.add_argument("out")
    ap.add_argument("--work"); ap.add_argument("--patch"); ap.add_argument("--crf", type=int, default=16); ap.add_argument("--share-crf", type=int); ap.add_argument("--force", action="store_true"); ap.add_argument("--allow-missing", action="store_true")
    a = ap.parse_args()
    sb = json.loads(Path(a.story).read_text()); outp = Path(a.out)
    work = Path(a.work) if a.work else outp.parent / f".{outp.stem}_work"; work.mkdir(parents=True, exist_ok=True)
    if a.patch:    # {"<n>": {field: value, ...}} overrides applied to the storyboard shots
        pt = json.loads(Path(a.patch).read_text())
        for s in sb["shots"]:
            s.update({k: v for k, v in pt.get(str(s["n"]), {}).items() if not k.startswith("_")})
    shots = sb["shots"]; lines = {l["id"]: l for l in sb["lines"]}
    photos_dir = Path(a.story).parent / "photos"; gen_dir = Path(a.story).parent / "work" / "gen"
    seed_clip = Path(a.story).parent / "work" / "seedance_stgiles_ref.mp4"
    vo_dir = Path(a.story).parent / "work" / "vo"

    # ---- motion-continuity pass + scene structure
    log = []
    for i, s in enumerate(shots):
        s["N"] = round(s["seconds"] * FPS)
        s["key"] = s["photo"]
        # dissolve/ease-in only when the photo changes AND the scene (narration line) changes; same photo = hard cut
        pv = shots[i - 1] if i else None
        s["scene_start"] = i == 0 or (pv["photo"] != s["photo"] and not (s.get("line_id") is not None and s.get("line_id") == pv.get("line_id")))
        if s["type"] == "crop" and i and shots[i - 1]["photo"] == s["photo"]:
            prev = shots[i - 1]
            pp = prev.get("push_used") if prev["type"] == "crop" else None
            if pp and OPP[pp] == s["push"]:
                log.append(f"shot {s['n']}: push {s['push']} -> {pp} (was opposite of shot {prev['n']})"); s["push_used"] = pp
        s.setdefault("push_used", s.get("push"))
    # ---- segments
    jobs, segs = [], {}
    missing = []
    for s in shots:
        ph = s["type"] == "gen" and not (gen_dir / f"shot{s['n']:02d}.mp4").exists()
        if ph:
            if not a.allow_missing: sys.exit(f"missing gen shot {s['n']}")
            missing.append(s["n"])
        h = hashlib.md5(json.dumps([ph, s["type"], s["photo"], s.get("crop"), s["push_used"], s["N"], s["scene_start"]]).encode()).hexdigest()[:8]
        seg = work / f"raw{s['n']:02d}_{h}.mp4"; segs[s["n"]] = seg
        if seg.exists() and not a.force: continue
        if s["type"] == "crop":
            jobs.append((str(photos_dir / s["photo"]), s["crop"], s["push_used"], s["N"], s["scene_start"], str(seg)))
        elif s["type"] == "gen":
            clip = gen_dir / f"shot{s['n']:02d}.mp4"
            if ph:
                jobs.append((str(photos_dir / s["photo"]), [0, 0, 1, 1], "in", s["N"], True, str(seg))); continue
            render_gen(clip, s["N"], seg)
        else:
            render_seed(seed_clip, s["N"], seg)
    with Pool(4) as p: p.map(render_crop, jobs)
    # ---- luma match for gen / seedance to neighbouring real crops
    final = {}
    for i, s in enumerate(shots):
        final[s["n"]] = segs[s["n"]]
        if s["type"] == "crop" or s["n"] in missing: continue
        tg = []
        if i and shots[i - 1]["type"] == "crop": tg.append(frame_stats(segs[shots[i - 1]["n"]], True))
        if i + 1 < len(shots) and shots[i + 1]["type"] == "crop": tg.append(frame_stats(segs[shots[i + 1]["n"]], False))
        if not tg: continue
        tm, ts = np.mean([t[0] for t in tg]), np.mean([t[1] for t in tg])
        sm = np.mean([frame_stats(segs[s["n"]], False)[0], frame_stats(segs[s["n"]], True)[0]])
        ss = np.mean([frame_stats(segs[s["n"]], False)[1], frame_stats(segs[s["n"]], True)[1]])
        k = float(np.clip(ts / max(ss, 1), 0.85, 1.15))
        adj = work / (segs[s["n"]].stem + "_adj.mp4")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(segs[s["n"]]), "-vf", f"lutyuv=y='clip((val-{sm:.2f})*{k:.4f}+{tm:.2f},16,235)'",
             "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", str(adj)])
        final[s["n"]] = adj
        log.append(f"shot {s['n']} ({s['type']}) luma {sm:.1f}->{tm:.1f} ({100*(tm-sm)/max(sm,1):+.1f}%), contrast x{k:.3f}")

    # ---- timeline
    t = 0.0
    for i, s in enumerate(shots):
        d = s["N"] / FPS
        s["diss"] = i > 0 and s["scene_start"]
        s["start"] = t - (XF if s["diss"] else 0)
        s["end"] = s["start"] + d; t = s["end"]
    vid_total = t
    total = vid_total + END
    # ---- video graph
    inputs, fc, cur, acc = [], [], "v0", 0.0
    for i, s in enumerate(shots):
        inputs += ["-i", str(final[s["n"]])]
        fc.append(f"[{i}:v]fps={FPS},settb=1/{FPS},setsar=1,format=yuv420p[p{i}]")
    cur, acc = "p0", shots[0]["N"] / FPS
    for i, s in enumerate(shots[1:], 1):
        d = s["N"] / FPS
        if s["diss"]:
            fc.append(f"[{cur}][p{i}]xfade=transition=fade:duration={XF}:offset={acc - XF:.4f},settb=1/{FPS},fps={FPS}[c{i}]"); acc += d - XF
        else:
            fc.append(f"[{cur}][p{i}]concat=n=2:v=1:a=0,settb=1/{FPS},fps={FPS}[c{i}]"); acc += d
        cur = f"c{i}"
    fc.append(f"[{cur}]eq=saturation=0.95:contrast=1.03,colorbalance=rs=0.02:gs=0.005:bs=-0.02:rm=0.02:bm=-0.02,"
              f"unsharp=5:5:0.35:5:5:0,noise=alls=3:allf=t,format=yuv420p[g0]")
    cur = "g0"; n_in = len(shots)
    # captions
    seen, caps = set(), []
    for s in shots:
        for key, txt in (("flat_chair.jpg", "EDINBURGH"), ("old_town_chambers.jpg", "THE ROYAL MILE"),
                         ("stgiles", "ST GILES’ CATHEDRAL"), ("london", "LONDON")):
            if key in seen: continue
            if (s["photo"] == key) or (key in ("stgiles", "london") and s["photo"].startswith(key)):
                seen.add(key); caps.append((s, txt))
    for j, (s, txt) in enumerate(caps):
        png = work / f"cap{j}.png"; caption_png(txt, png)
        t0 = max(s["start"], FADE_IN) + 0.3 if s["n"] == 1 else s["start"] + 0.3
        inputs += ["-loop", "1", "-t", "3", "-framerate", str(FPS), "-i", str(png)]
        fc.append(f"[{n_in}:v]format=rgba,fade=t=in:st=0:d=0.5:alpha=1,fade=t=out:st=2.5:d=0.5:alpha=1,setpts=PTS+{t0:.3f}/TB[cp{j}]")
        fc.append(f"[{cur}][cp{j}]overlay=eof_action=pass:format=auto[o{j}]"); cur = f"o{j}"; n_in += 1
        s["caption"] = {"text": txt, "t0": round(t0, 2)}
    fc.append(f"[{cur}]fade=t=in:st=0:d={FADE_IN},fade=t=out:st={vid_total - FADE_OUT:.3f}:d={FADE_OUT}[mainv]")
    endpng = work / "end.png"; endcard_png(endpng)
    inputs += ["-loop", "1", "-t", f"{END}", "-framerate", str(FPS), "-i", str(endpng)]
    fc.append(f"[{n_in}:v]fps={FPS},settb=1/{FPS},setsar=1,format=yuv420p[endv]")
    fc.append(f"[mainv][endv]concat=n=2:v=1:a=0,settb=1/{FPS}[vout]")
    (work / "v.txt").write_text(";\n".join(fc))
    vid = work / "video.mp4"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex_script", str(work / "v.txt"), "-map", "[vout]",
         "-c:v", "libx264", "-crf", str(a.crf), "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS), "-t", f"{total:.3f}", str(vid)])

    # ---- narration schedule
    vo_t, prev_end, overrun = {}, 0.0, []
    for lid in sorted(lines):
        l = lines[lid]; f, last = shots[[x["n"] for x in shots].index(l["shots"][0])], shots[[x["n"] for x in shots].index(l["shots"][-1])]
        st = f["start"] - 0.5 if (f["scene_start"] and f["n"] != 1) else f["start"] + 0.3
        st = max(st, prev_end + 0.15, 0.0)
        mp3 = vo_dir / f"L{lid:02d}_t0.mp3"; d = dur(mp3)
        vo_t[lid] = (st, d, mp3); prev_end = st + d
        if st + d > last["end"] + 0.01: overrun.append({"line": lid, "past_last_shot_s": round(st + d - last["end"], 2)})
    # ---- music
    byn = {s["n"]: s for s in shots}
    pk = sb.get("peak_shot")          # music silence+swell shot: storyboard "peak_shot" (n) or the seedance shot
    sd = [s for s in shots if s["n"] == pk] if pk else [s for s in shots if s["type"] == "seedance"]
    S0, S1 = (sd[0]["start"], sd[0]["end"]) if sd else (None, None)
    first = lambda ph: min(s["start"] for s in shots if s["photo"].startswith(ph))
    secs = [(0, first("old_town"), "low"), (first("old_town"), byn[17]["start"], "mid")]
    if sd: secs += [(byn[17]["start"], S0, "low"), (S0, S1 + 1.0, "high"), (S1 + 1.0, total + 1, "low")]
    else: secs += [(byn[17]["start"], total + 1, "low")]
    bed = work / "bed.wav"; make_doc(total + 0.5, secs, bed)
    G = 10 ** (4 / 20)
    if sd:
        vexpr = (f"if(lt(t,{S0 - 1.12:.3f}),1,if(lt(t,{S0 - 1.0:.3f}),({S0 - 1.0:.3f}-t)/0.12,if(lt(t,{S0:.3f}),0,"
                 f"if(lt(t,{S0 + 1:.3f}),{G:.4f}*(t-{S0:.3f}),if(lt(t,{S1:.3f}),{G:.4f},if(lt(t,{S1 + 1.5:.3f}),{G:.4f}-{G - 1:.4f}*(t-{S1:.3f})/1.5,1))))))")
    else: vexpr = "1"
    ain, af, mix = ["-i", str(bed)], [], []
    for k, lid in enumerate(sorted(vo_t)):
        st, d, mp3 = vo_t[lid]; ms = int(st * 1000)
        ain += ["-i", str(mp3)]
        af.append(f"[{k + 1}:a]aresample=48000,adelay={ms}|{ms}[v{k}]"); mix.append(f"[v{k}]")
    af.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=longest,apad=whole_dur={total:.3f},asplit=2[vo][key]")
    af.append(f"[0:a]volume='{vexpr}':eval=frame,volume=0.35,afade=t=out:st={vid_total - 0.5:.2f}:d={END + 0.5:.2f}[mus]")
    af.append("[mus][key]sidechaincompress=threshold=0.05:ratio=4:attack=80:release=400[duck]")
    af.append("[duck][vo]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.5:attack=5:release=80[mx]")
    (work / "a.txt").write_text(";\n".join(af))
    pre = work / "pre.wav"
    run(["ffmpeg", "-v", "error", "-y", *ain, "-filter_complex_script", str(work / "a.txt"), "-map", "[mx]", "-t", f"{total:.3f}", "-ar", "48000", str(pre)])
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(pre), "-af", "loudnorm=I=-14:TP=-2.4:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = json.loads(r[r.rindex("{"):])
    ln = (f"loudnorm=I=-14:TP=-2.4:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(vid), "-i", str(pre), "-af", ln + ",aresample=48000", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(outp)])
    if (work / "video.mp4").exists() and a.share_crf is None: pass
    if a.share_crf:
        run(["ffmpeg", "-v", "error", "-y", "-i", str(outp), "-c:v", "libx264", "-crf", str(a.share_crf), "-preset", "medium",
             "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(outp.with_name(outp.stem + "_share.mp4"))])
    tl = {"total": round(total, 3), "missing_gen_placeholders": missing, "flips": log,
          "shots": [{"n": s["n"], "type": s["type"], "start": round(s["start"], 3), "end": round(s["end"], 3), "push_used": s["push_used"],
                     "ease_in": s["scene_start"], "dissolve_in": s["diss"], **({"caption": s["caption"]} if "caption" in s else {})} for s in shots],
          "lines": [{"id": k, "start": round(v[0], 3), "end": round(v[0] + v[1], 3)} for k, v in vo_t.items()],
          "vo_offsets": [round(vo_t[k][0], 3) for k in sorted(vo_t)], "overruns": overrun}
    outp.with_suffix(".timeline.json").write_text(json.dumps(tl, indent=1))
    print(f"wrote {outp} ({total:.2f}s) overruns={overrun} missing={missing}"); print("\n".join(log))


if __name__ == "__main__":
    main()
