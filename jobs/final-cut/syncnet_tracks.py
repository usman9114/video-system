"""SyncNet (joonson/syncnet_python, LSE-C/LSE-D) on EVERY face track of a whole cut, with each track's time range.
Usage: syncnet_tracks.py <video> <ref-name> <out.json>   (needs the checkout at /tmp/sn; one GPU via CUDA_VISIBLE_DEVICES)
run_pipeline splits the cut at scene changes and tracks faces (>= 100 frames = 4 s at 25 fps); run_syncnet then
prints one offset/dist/conf block per track, in the same (sorted) order as tracks.pckl."""
import json, os, pickle, re, subprocess, sys

SN = "/tmp/sn"
video, ref, out = sys.argv[1:4]
data = f"/tmp/snd_{ref}"
v25 = f"/tmp/{ref}_25.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", video, "-r", "25", "-ar", "16000", v25], check=True)
pp = subprocess.run([sys.executable, "run_pipeline.py", "--videofile", v25, "--reference", ref, "--data_dir", data],
                    cwd=SN, capture_output=True, text=True)
r = subprocess.run([sys.executable, "run_syncnet.py", "--videofile", v25, "--reference", ref, "--data_dir", data],
                   cwd=SN, capture_output=True, text=True)
txt = r.stdout + r.stderr
off = [int(x) for x in re.findall(r"AV offset:\s*(-?\d+)", txt)]
md = [float(x) for x in re.findall(r"Min dist:\s*([\d.]+)", txt)]
cf = [float(x) for x in re.findall(r"Confidence:\s*([\d.]+)", txt)]
tracks = []
tp = f"{data}/pywork/{ref}/tracks.pckl"
if os.path.exists(tp):
    for k, tr in enumerate(pickle.load(open(tp, "rb"))):
        fr = tr["track"]["frame"]
        tracks.append({"track": k, "start": round(float(fr[0]) / 25, 2), "end": round(float(fr[-1] + 1) / 25, 2),
                       "frames": int(len(fr)),
                       "offset": off[k] if k < len(off) else None, "lse_d": md[k] if k < len(md) else None,
                       "lse_c": cf[k] if k < len(cf) else None})
res = {"ref": ref, "tracks": tracks}
if not cf:
    res["log"] = txt[-800:]
    res["pipeline_log"] = (pp.stdout + pp.stderr)[-1500:]
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res)[:2000])
