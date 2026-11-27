"""Fill lab: pre-render "gap filling" passes on Kaggle's 2x T4. Clips are split across both GPUs (one worker each).

Inputs ($KGPU_INPUT, recursive): *.mp4 clips + manifest.json from scripts/fill_lab.py
(templates/production.json -> fill_lab, values resolved). Per clip, in order:
  interpolate : RIFE 4.25 (Practical-RIFE, MIT; official Google Drive weights) to target_fps with real in-between
                frames, instead of ffmpeg's fps filter repeating every 5th frame (25->30 fps judder on lip-sync clips)
  upscale     : Real-ESRGAN x2plus (BSD-3), then Lanczos to scale x the input size; gated on the CPU side
Outputs ($KGPU_OUTPUT): <clip>.mp4 (same name, audio copied), fill.json (per clip: frames, seconds, gpu), worker logs.
"""
import glob, json, math, os, subprocess, sys, threading, time

INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
HERE = os.path.dirname(os.path.abspath(__file__))
W = "/tmp/fl"


def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)


def setup(man):
    os.makedirs(W, exist_ok=True)
    ops = {op for c in man["clips"] for op in c["ops"]}
    if "interpolate" in ops:
        sh(f"git clone -q --depth 1 https://github.com/hzwer/Practical-RIFE.git {W}/rife")
        sh(f"{sys.executable} -m pip install -q gdown")
        r = man["interpolate"]
        sh(f"cd {W} && {sys.executable} -m gdown -q {r['gdrive_id']} -O rife.zip && unzip -q -o rife.zip -d rifew")
        pk = glob.glob(f"{W}/rifew/**/flownet.pkl", recursive=True)
        if not pk:
            sys.exit("fill-lab: flownet.pkl not in the RIFE download")
        sh(f"mkdir -p {W}/rife/train_log && cp {os.path.dirname(pk[0])}/*.py {pk[0]} {W}/rife/train_log/")
    if "upscale" in ops:
        sh(f"{sys.executable} -m pip install -q addict future lmdb yapf")
        sh(f"{sys.executable} -m pip install -q --no-deps realesrgan==0.3.0")
        # basicsr 1.4.2: sdist whose setup.py breaks on Python 3.13 -> use the pure-Python source tree (LESSONS #74)
        bs = man["upscale"]["basicsr_sdist"]
        sh(f"cd {W} && curl -sL {bs} | tar xz && sed -i "
           f"'s/torchvision.transforms.functional_tensor/torchvision.transforms.functional/' "
           f"{W}/basicsr-1.4.2/basicsr/data/degradations.py")
        sh(f"curl -sL -o {W}/RealESRGAN_x2plus.pth {man['upscale']['weights_url']}")


def main():
    t0 = time.time()
    man = json.load(open(next(iter(glob.glob(f"{INP}/**/manifest.json", recursive=True)))))
    clips = {os.path.basename(p): p for p in glob.glob(f"{INP}/**/*.mp4", recursive=True)}
    jobs = [dict(c, path=clips[c["name"]]) for c in man["clips"] if c["name"] in clips]
    missing = [c["name"] for c in man["clips"] if c["name"] not in clips]
    setup(man)
    # longest-first round robin so both T4s finish together
    jobs.sort(key=lambda c: -c.get("frames", 0))
    shards = [[], []]
    for k, j in enumerate(jobs):
        shards[k % 2].append(j)
    ths, util, stop = [], {}, threading.Event()

    def sampler():
        while not stop.is_set():
            try:
                for line in subprocess.check_output(["nvidia-smi", "--query-gpu=index,utilization.gpu",
                                                     "--format=csv,noheader,nounits"], text=True).strip().splitlines():
                    i, u = [int(x) for x in line.split(", ")]
                    util.setdefault(i, []).append(u)
            except Exception:
                pass
            stop.wait(2)
    threading.Thread(target=sampler, daemon=True).start()
    sys.path.insert(0, HERE)
    import worker                     # in-process threads, one per T4 (see worker.py docstring)
    os.chdir(W)
    rcs, done = {}, {}
    for g, sh_ in enumerate(shards):
        if not sh_:
            continue
        def go(g=g, sh_=sh_):
            try:
                worker.work(g, man, sh_, OUT, done); rcs[g] = 0
            except Exception:
                import traceback; traceback.print_exc(); rcs[g] = 1
        th = threading.Thread(target=go); th.start(); ths.append(th)
    for th in ths:
        th.join()
    stop.set()
    res = {"clips": {}, "missing": missing, "worker_rc": rcs, "total_s": round(time.time() - t0, 1),
           "gpu_util": {f"gpu{i}": {"mean_util_pct": round(sum(v) / len(v), 1),
                                    "busy_pct": round(100 * sum(u > 30 for u in v) / len(v), 1)} for i, v in util.items() if v}}
    res["clips"] = dict(done)
    json.dump(res, open(f"{OUT}/fill.json", "w"), indent=1)
    print("fill-lab:", json.dumps(res)[:3000], flush=True)
    sys.exit(max(rcs.values(), default=0))


if __name__ == "__main__":
    main()
