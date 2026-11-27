"""Final-cut lab: review + master touch-up of ONE finished cut on Kaggle's 2x T4, both GPUs busy at once.

Inputs ($KGPU_INPUT, recursive): master.mp4 + manifest.json (written by scripts/final_cut.py from
templates/production.json -> final_cut, all thresholds already resolved to numbers).

    GPU0: touch-up frames [0, cut)  -> Whisper large-v3 word timestamps (script check) -> SyncNet on the master
    GPU1: touch-up frames [cut, n)  -> join + encode touched.mp4 + side-by-sides -> SyncNet on the touched cut
    (touch-up = face detail, GFPGAN light blend, lip-synced mouth protected; cut = gpu0_share of the frames)
    CPU (main process) : loudness/true peak, black, freeze, scene cuts, contact sheet, GPU utilisation sampling

Outputs ($KGPU_OUTPUT): lab.json (raw measurements), words.json, syncnet_master.json, syncnet_touched.json,
touched.mp4 + side_by_side.mp4 (only when face_detail is enabled for this kind), sheet/*.jpg, lane_*.log.
Pass/fail is decided on the CPU side by scripts/final_cut.py, so gates can change without re-running the GPUs.
"""
import glob, json, os, re, subprocess, sys, threading, time

INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
HERE = os.path.dirname(os.path.abspath(__file__))
SN = "/tmp/sn"          # syncnet_python checkout (never under /kaggle/working: LESSONS #31)


def sh(c, **kw):
    print("+", c, flush=True)
    return subprocess.run(c, shell=True, check=True, **kw)


def find(name):
    hits = sorted(glob.glob(f"{INP}/**/{name}", recursive=True))   # kgpu puts dir inputs in a subfolder (LESSONS #61)
    if not hits:
        sys.exit(f"final-cut: {name} not found under {INP}")
    return hits[0]


def probe(path):
    o = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", path]))
    v = next(s for s in o["streams"] if s["codec_type"] == "video")
    n, d = map(int, v["r_frame_rate"].split("/"))
    return {"width": v["width"], "height": v["height"], "fps": round(n / d, 3), "frames": int(v.get("nb_frames", 0) or 0),
            "duration": float(o["format"]["duration"]), "has_audio": any(s["codec_type"] == "audio" for s in o["streams"])}


# ---------------------------------------------------------------- CPU QC (runs while both GPU lanes work)
def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-map", "0:a:0", "-af", "ebur128=peak=true",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    tail = r[r.rfind("Summary:"):]
    g = lambda k: float(re.search(k + r":\s*(-?[\d.]+|-inf)", tail).group(1).replace("-inf", "-99"))
    return {"integrated_lufs": g("I"), "lra_lu": g("LRA"), "true_peak_db": g("Peak")}


def black(path, min_s):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vf", f"blackdetect=d={min_s}:pix_th=0.06",
                        "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    return [{"start": float(a), "end": float(b)} for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r)]


def freeze(path, noise, min_s):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vf", f"freezedetect=n={noise}:d={min_s}",
                        "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", r)]
    en = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", r)]
    return [{"start": s, "end": e} for s, e in zip(st, en + [None] * (len(st) - len(en)))]


def scene_cuts(path, thr):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vf", f"scdet=threshold={thr}",
                        "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    return [{"t": float(t), "score": float(s)} for s, t in re.findall(r"lavfi\.scd\.score: ([\d.]+), lavfi\.scd\.time: ([\d.]+)", r)]


def contact_sheet(path, dur, n):
    os.makedirs(f"{OUT}/sheet", exist_ok=True)
    for k in range(n):
        t = dur * (k + 0.5) / n
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-q:v", "3",
                        f"{OUT}/sheet/{k:02d}_t{t:05.2f}.jpg"], check=False)


# ---------------------------------------------------------------- GPU utilisation sampler (evidence both T4s work)
def sampler(stop, rec):
    while not stop.is_set():
        try:
            o = subprocess.check_output(["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used",
                                         "--format=csv,noheader,nounits"], text=True)
            for line in o.strip().splitlines():
                i, u, m = [int(x) for x in line.split(", ")]
                rec.setdefault(i, []).append((u, m))
        except Exception:
            pass
        stop.wait(2)


def lane(name, gpu, cmds):
    """Run lane steps one after another, pinned to one GPU; returns (thread, result dict)."""
    res = {}
    def go():
        t0 = time.time()
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), PYTHONUNBUFFERED="1")
        rc, steps = 0, []
        with open(f"{OUT}/lane_{name}.log", "w") as log:
            for cmd in cmds:
                t1 = time.time()
                rc = subprocess.call(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
                steps.append({"step": os.path.basename(cmd[1]), "rc": rc, "seconds": round(time.time() - t1, 1)})
                if rc:
                    break
        res.update(rc=rc, seconds=round(time.time() - t0, 1), gpu=gpu, steps=steps)
        print(f"final-cut: lane {name} (gpu{gpu}) rc={rc} in {res['seconds']}s", flush=True)
    th = threading.Thread(target=go)
    th.start()
    return th, res


def main():
    t0 = time.time()
    master = find("master.mp4")
    man = json.load(open(find("manifest.json")))
    chk = man["checks"]
    info = probe(master)
    print("final-cut:", man.get("id"), man["kind"], info, flush=True)

    # shared setup once (both lanes need SyncNet; listen needs whisper; touch-up installs its own extras)
    sh(f"git clone -q --depth 1 https://github.com/joonson/syncnet_python.git {SN}")
    sh(f"{sys.executable} -m pip install -q 'scenedetect>=0.6.4' python_speech_features openai-whisper==20250625")
    sh(f"cd {SN} && bash download_model.sh > /dev/null")

    py = sys.executable
    fd = man["touchup"]["face_detail"]
    listen = [py, f"{HERE}/lane_listen.py", master, OUT, json.dumps(man)]
    if fd["enabled"]:
        # touch-up frames split over BOTH T4s; GPU0 takes the smaller share because it also runs the listen steps
        sh(f"{py} {HERE}/lane_touchup.py --prepare")
        n = info["frames"] or int(info["duration"] * info["fps"])
        cut = int(n * man["touchup"]["gpu0_share"])
        tu = lambda f0, f1, k: [py, f"{HERE}/lane_touchup.py", master, OUT, json.dumps(man), str(f0), str(f1), str(k)]
        lanes = [lane("gpu0", 0, [tu(0, cut, 0), listen]),
                 lane("gpu1", 1, [tu(cut, n, 1), [py, f"{HERE}/lane_finish.py", master, OUT, json.dumps(man), "2"]])]
    else:
        lanes = [lane("gpu0", 0, [listen])]

    stop, util = threading.Event(), {}
    smp = threading.Thread(target=sampler, args=(stop, util), daemon=True)
    smp.start()

    # CPU QC meanwhile
    lab = {"id": man.get("id"), "kind": man["kind"], "info": info}
    lab["loudness"] = loudness(master) if info["has_audio"] else None
    lab["black"] = black(master, chk["black"]["min_s"])
    lab["freeze"] = freeze(master, chk["freeze"]["noise"], chk["freeze"]["min_s"])
    lab["cuts"] = scene_cuts(master, chk["cut_while_talking"]["scene_threshold"])
    contact_sheet(master, info["duration"], chk["contact_sheet"]["frames"])
    lab["cpu_qc_s"] = round(time.time() - t0, 1)
    print("final-cut: CPU QC done", {k: lab[k] for k in ("loudness", "black", "freeze")}, len(lab["cuts"]), "cuts", flush=True)

    for th, _ in lanes:
        th.join()
    stop.set()
    smp.join(timeout=5)
    lab["lanes"] = {f"gpu{r['gpu']}": r for _, r in lanes}
    lab["gpu_util"] = {f"gpu{i}": {"mean_util_pct": round(sum(u for u, _ in v) / len(v), 1),
                                   "busy_pct": round(100 * sum(u > 30 for u, _ in v) / len(v), 1),
                                   "peak_mem_mb": max(m for _, m in v), "samples": len(v)} for i, v in util.items() if v}
    lab["total_s"] = round(time.time() - t0, 1)
    json.dump(lab, open(f"{OUT}/lab.json", "w"), indent=1)
    print("final-cut: done", json.dumps(lab["lanes"]), json.dumps(lab["gpu_util"]), flush=True)
    sys.exit(max((r.get("rc", 1) for _, r in lanes), default=0))


if __name__ == "__main__":
    main()
