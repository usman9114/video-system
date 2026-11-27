"""LatentSync (ByteDance, Apache-2.0 code) lip-sync on Kaggle 2x T4: v1.5 (256px, ~8 GB) on GPU0 and v1.6 (512px,
~18 GB officially; may OOM on a 16 GB T4) on GPU1, in parallel. Free, no watermark.
Inputs: face.mp4 (cropped face video), voice.(mp3|wav). Outputs: ls15.mp4, ls16.mp4, logs.
Env lives in /tmp (never /kaggle/working, see docs/LESSONS.md #31). Python 3.10 is required (mediapipe/decord wheels)."""
import os, subprocess, sys, time, glob, json
INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
T = "/tmp/ls"
def sh(c, **k):
    print("+", c, flush=True); return subprocess.run(c, shell=True, check=True, **k)
t0 = time.time()
sh(f"{sys.executable} -m pip install -q uv")
sh(f"git clone -q --depth 1 https://github.com/bytedance/LatentSync.git {T}/repo")
sh(f"cd {T} && uv venv -q -p 3.10 venv && uv pip install -q --python {T}/venv/bin/python -r repo/requirements.txt")
PY = f"{T}/venv/bin/python"
dl = ("from huggingface_hub import hf_hub_download as d\n"
      "for rep, tag in (('ByteDance/LatentSync-1.5','15'),('ByteDance/LatentSync-1.6','16')):\n"
      "  for f in ('latentsync_unet.pt','whisper/tiny.pt'):\n"
      "    d(rep, f, local_dir=f'/tmp/ls/ckpt{tag}')\n")
sh(f"{PY} -c \"{dl}\"")
print("setup", round(time.time() - t0), "s", flush=True)
face = glob.glob(f"{INP}/face.*")[0]
voice = glob.glob(f"{INP}/voice.*")[0]
sh(f"ffmpeg -v error -y -i {voice} -ac 1 -ar 16000 {T}/voice.wav")
def job(tag, gpu, cfg):
    # scripts.inference expects checkpoints/ relative to the repo; give each run its own copy of the repo
    rd = f"{T}/run{tag}"
    sh(f"cp -r {T}/repo {rd} && rm -rf {rd}/checkpoints && ln -s {T}/ckpt{tag} {rd}/checkpoints")
    cmd = (f"cd {rd} && CUDA_VISIBLE_DEVICES={gpu} {PY} -m scripts.inference --unet_config_path configs/unet/{cfg} "
           f"--inference_ckpt_path checkpoints/latentsync_unet.pt --inference_steps 25 --guidance_scale 1.5 "
           f"--enable_deepcache --video_path {face} --audio_path {T}/voice.wav --video_out_path {OUT}/ls{tag}.mp4")
    return subprocess.Popen(cmd, shell=True, stdout=open(f"{OUT}/ls{tag}.log", "w"), stderr=subprocess.STDOUT)
t1 = time.time()
procs = {"15": job("15", 0, "stage2.yaml"), "16": job("16", 1, "stage2_512.yaml")}
rc = {k: p.wait() for k, p in procs.items()}
json.dump({"rc": rc, "setup_s": round(t1 - t0), "infer_s": round(time.time() - t1)}, open(f"{OUT}/summary.json", "w"))
print(rc)
sys.exit(0 if any(v == 0 for v in rc.values()) else 1)
