"""SyncNet lip-sync quality (joonson/syncnet_python, the standard LSE-C / LSE-D metric) for every *.mp4 in $KGPU_INPUT.
LSE-C = confidence (higher = better sync), LSE-D = min distance (lower = better), offset in frames (0 = in sync).
Output: syncnet.json {clip: {offset, lse_d, lse_c}}. Fast path: pip into Kaggle's env (docs/LESSONS.md #28)."""
import glob, json, os, re, subprocess, sys
INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
T = "/tmp/sn"
def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)
sh(f"git clone -q --depth 1 https://github.com/joonson/syncnet_python.git {T}")
sh(f"{sys.executable} -m pip install -q scenedetect==0.5.1 python_speech_features")
sh(f"cd {T} && bash download_model.sh")
res = {}
for f in sorted(glob.glob(f"{INP}/*.mp4")):
    name = os.path.splitext(os.path.basename(f))[0]
    # syncnet expects 25 fps
    sh(f"ffmpeg -v error -y -i {f} -r 25 -ar 16000 {T}/{name}.mp4")
    subprocess.run(f"cd {T} && {sys.executable} run_pipeline.py --videofile {name}.mp4 --reference {name} --data_dir /tmp/snd",
                   shell=True, capture_output=True, text=True)
    r = subprocess.run(f"cd {T} && {sys.executable} run_syncnet.py --videofile {name}.mp4 --reference {name} --data_dir /tmp/snd",
                       shell=True, capture_output=True, text=True)
    txt = r.stdout + r.stderr
    off = re.findall(r"AV offset:\s*(-?\d+)", txt); md = re.findall(r"Min dist:\s*([\d.]+)", txt); cf = re.findall(r"Confidence:\s*([\d.]+)", txt)
    res[name] = {"offset": int(off[0]) if off else None, "lse_d": float(md[0]) if md else None,
                 "lse_c": float(cf[0]) if cf else None, "tracks": len(cf)}
    if not cf:
        res[name]["log"] = txt[-800:]
    print(name, res[name], flush=True)
json.dump(res, open(f"{OUT}/syncnet.json", "w"), indent=1)
