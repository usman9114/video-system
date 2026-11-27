"""After both touch-up shards: join them, encode touched.mp4 (audio from the master), merge the per-frame stats into
touchup.json, write side-by-sides for the owner's eye, then SyncNet on the touched cut (gate input).
argv: master OUT manifest-json nshards"""
import glob, json, os, subprocess, sys
import numpy as np

master, OUT, man, N = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), int(sys.argv[4])
HERE = os.path.dirname(os.path.abspath(__file__))
W = "/tmp/fc"
enc = man["touchup"]["encode"]


def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)


with open(f"{W}/shards.txt", "w") as f:
    for k in range(N):
        f.write(f"file '{W}/touched_{k}.mkv'\n")
sh(f"ffmpeg -v error -y -f concat -safe 0 -i {W}/shards.txt -i {master} -map 0:v -map 1:a? -c:v libx264 "
   f"-preset {enc['preset']} -crf {enc['crf']} -pix_fmt yuv420p -profile:v high -c:a copy -movflags +faststart "
   f"{OUT}/touched.mp4")

parts = [json.load(open(f"{W}/touchup_{k}.json")) for k in range(N)]
stats = [s for p in parts for s in p["per_frame"]]
fs = [s["face_ssim"] for s in stats]
res = {"frames": sum(p["frames"] for p in parts), "frames_touched": len(stats), "blend": parts[0]["blend"],
       "seconds": max(p["seconds"] for p in parts), "shard_seconds": [p["seconds"] for p in parts],
       "face_ssim_mean": round(float(np.mean(fs)), 4) if fs else None,
       "face_ssim_p05": round(float(np.percentile(fs, 5)), 4) if fs else None,
       "face_ssim_min": round(float(np.min(fs)), 4) if fs else None, "per_frame": stats}
json.dump(res, open(f"{OUT}/touchup.json", "w"))
print("touchup:", {k: v for k, v in res.items() if k != "per_frame"}, flush=True)

sh(f"ffmpeg -v error -y -i {master} -i {OUT}/touched.mp4 -filter_complex "
   f"\"[0:v]scale=iw/2:-2[a];[1:v]scale=iw/2:-2[b];[a][b]hstack\" -map 1:a? -c:v libx264 -crf 18 -preset fast "
   f"-c:a copy {OUT}/side_by_side.mp4")
boxes = [s["box"] for s in stats]
if boxes:
    x0, y0, x1, y1 = [int(v) for v in np.median(np.array(boxes), 0)]
    cw, ch = (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2
    sh(f"ffmpeg -v error -y -i {master} -i {OUT}/touched.mp4 -filter_complex "
       f"\"[0:v]crop={cw}:{ch}:{x0}:{y0},scale=iw*2:-2:flags=neighbor[a];[1:v]crop={cw}:{ch}:{x0}:{y0},"
       f"scale=iw*2:-2:flags=neighbor[b];[a][b]hstack\" -map 1:a? -c:v libx264 -crf 16 -preset fast -c:a copy "
       f"{OUT}/side_by_side_face.mp4")

subprocess.run([sys.executable, f"{HERE}/syncnet_tracks.py", f"{OUT}/touched.mp4", "touched",
                f"{OUT}/syncnet_touched.json"], check=True)
