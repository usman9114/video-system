#!/usr/bin/env python3
"""Assemble generated trip shots into a narrated documentary sequence (owner-approved steps, 2026-11-27):

  1. every scene opens on the REAL photo (same 9:16 crop the generator used), held `hold` s
  2. dissolve into the generated clip (Wan I2V, 16 fps) re-timed smoothly to 30 fps and slowed to fit the line
  3. narration line starts while the named subject is on screen (LESSONS 87); serif place · date caption + scrim
  4. scenes joined with short dissolves; documentary score ducked under the voice; -14 LUFS / TP -2

  python3 scripts/trip/assemble_gen.py <plan.json> <out.mp4>
plan.json: {"fps":30, "hold":0.8, "lead":0.6, "tail":0.9, "xfade":0.45,
            "scenes":[{"photo","clip","vo","caption","focus_x"?,"focus_y"?}]}
"""
import json, subprocess, sys, tempfile
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "trip"))
from music_doc import make_doc  # noqa: E402

W, H = 1080, 1920
FONT = ROOT / "assets" / "fonts" / "CormorantGaramond-SemiBold.ttf"


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)]))


def sh(cmd):
    subprocess.run(cmd, check=True)


def scene(sc, cfg, tmp, i):
    fps, hold, lead, tail = cfg["fps"], cfg["hold"], cfg["lead"], cfg["tail"]
    # real photo, same crop as the generator (exif transpose + 9:16 cover crop at the focus point)
    img = ImageOps.exif_transpose(Image.open(ROOT / sc["photo"])).convert("RGB")
    img = ImageOps.fit(img, (W, H), Image.LANCZOS, centering=(sc.get("focus_x", 0.5), sc.get("focus_y", 0.5)))
    still = tmp / f"s{i}.png"
    img.save(still)
    vo_len = dur(ROOT / sc["vo"])
    total = max(hold + dur(ROOT / sc["clip"]), lead + vo_len + tail)
    slow = max(1.0, (total - hold) / dur(ROOT / sc["clip"]))
    cap = sc.get("caption", "")
    font = FONT if FONT.exists() else "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
    text = (f",drawtext=fontfile='{font}':text='{cap}':x=84:y=h-300:fontsize=58:fontcolor=0xF2EBDD:"
            f"shadowcolor=black@0.5:shadowx=2:shadowy=2:alpha='if(lt(t,0.4),t/0.4,if(lt(t,3.2),1,max(0,(3.8-t)/0.6)))'") if cap else ""
    scrim = ("[v0]split[a][b];[b]crop=iw:ih*0.3:0:ih*0.7,colorchannelmixer=rr=0:gg=0:bb=0,format=rgba,"
             "geq=r=0:g=0:b=0:a='110*(Y/H)*(Y/H)'[s];[a][s]overlay=0:H*0.7:enable='lt(t,3.8)'[v1]") if cap else "[v0]null[v1]"
    out = tmp / f"scene{i}.mp4"
    fc = (f"[0:v]loop=loop=-1:size=1,trim=0:{hold + 0.3},setpts=PTS-STARTPTS,fps={fps},format=yuv420p[ph];"
          f"[1:v]scale={W}:{H}:flags=lanczos,minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1,"
          f"setpts={slow:.4f}*(PTS-STARTPTS),fps={fps},tpad=stop_mode=clone:stop_duration=2,format=yuv420p[cl];"
          f"[ph][cl]xfade=transition=fade:duration=0.3:offset={hold},trim=0:{total},setpts=PTS-STARTPTS,"
          f"eq=saturation=0.95:contrast=1.03,noise=alls=3:allf=t[v0];{scrim};[v1]null{text}[v]")
    sh(["ffmpeg", "-v", "error", "-y", "-i", str(still), "-i", str(ROOT / sc["clip"]), "-filter_complex", fc,
        "-map", "[v]", "-r", str(fps), "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-an", str(out)])
    return out, total, vo_len


def main():
    plan, outp = json.loads(Path(sys.argv[1]).read_text()), Path(sys.argv[2])
    cfg = {"fps": 30, "hold": 0.8, "lead": 0.6, "tail": 0.9, "xfade": 0.45, **plan}
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        parts = [scene(sc, cfg, tmp, i) for i, sc in enumerate(cfg["scenes"])]
        xf = cfg["xfade"]
        # video: chain xfades; record where each scene starts on the final timeline
        starts, acc, inputs, fc, last = [], 0.0, [], [], "0:v"
        for i, (p, d, _) in enumerate(parts):
            inputs += ["-i", str(p)]
            starts.append(acc if i == 0 else acc - xf)
            if i:
                fc.append(f"[{last}][{i}:v]xfade=transition=fade:duration={xf}:offset={acc - xf:.3f}[x{i}]")
                last = f"x{i}"
                acc += d - xf
            else:
                acc = d
        total = acc
        vid = tmp / "video.mp4"
        sh(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc) or "[0:v]null[x0]",
            "-map", f"[{last if fc else 'x0'}]", "-c:v", "libx264", "-crf", "16", "-preset", "medium", str(vid)])
        # audio: voice lines at scene start + lead, score ducked under them
        bed = tmp / "bed.wav"
        make_doc(total + 0.5, [(0, total + 0.5, "low")], bed)
        ain, af, mix = ["-i", str(bed)], [], []
        for i, (sc, s) in enumerate(zip(cfg["scenes"], starts)):
            ain += ["-i", str(ROOT / sc["vo"])]
            ms = int((s + cfg["lead"]) * 1000)
            af.append(f"[{i + 2}:a]adelay={ms}|{ms},apad=whole_dur={total:.3f}[v{i}]")
            mix.append(f"[v{i}]")
        n = len(mix)
        af.append(f"{''.join(mix)}amix=inputs={n}:normalize=0,asplit=2[vo][key]")
        af.append(f"[1:a]volume=0.35,afade=t=in:d=1,afade=t=out:st={total - 1.2:.2f}:d=1.2[mus]")
        af.append("[mus][key]sidechaincompress=threshold=0.05:ratio=4:attack=80:release=400[duck]")
        af.append("[duck][vo]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-2:LRA=11[a]")
        sh(["ffmpeg", "-v", "error", "-y", "-i", str(vid), *ain, "-filter_complex", ";".join(af),
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}",
            "-movflags", "+faststart", str(outp)])
    Path(outp).with_suffix(".timeline.json").write_text(json.dumps(
        {"total": round(total, 3), "vo_offsets": [round(s + cfg["lead"], 3) for s in starts]}, indent=1))
    print(f"wrote {outp} ({total:.2f}s); vo offsets {[round(s + cfg['lead'], 2) for s in starts]}")


if __name__ == "__main__":
    main()
