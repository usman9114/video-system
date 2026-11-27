"""LatentSync 1.6 (512px, sharpest open model) squeezed onto a 16 GB T4 by shrinking the frame chunk.
GPU0: num_frames=8, GPU1: num_frames=12 (+ expandable_segments). Both 20 steps, guidance 1.5, DeepCache, fp16.
Inputs: face.mp4, voice.(mp3|wav). Outputs: ls16_f8.mp4, ls16_f12.mp4 (+logs). Env in /tmp."""
import os, subprocess, sys, time, glob, json
INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
T = "/tmp/ls"
def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)
t0 = time.time()
sh(f"{sys.executable} -m pip install -q uv")
sh(f"git clone -q --depth 1 https://github.com/bytedance/LatentSync.git {T}/repo")
sh(f"cd {T} && uv venv -q -p 3.10 venv && uv pip install -q --python {T}/venv/bin/python -r repo/requirements.txt")
PY = f"{T}/venv/bin/python"
dl = ("from huggingface_hub import hf_hub_download as d\n"
      "for f in ('latentsync_unet.pt','whisper/tiny.pt'): d('ByteDance/LatentSync-1.6', f, local_dir='/tmp/ls/ckpt16')\n")
sh(f"{PY} -c \"{dl}\"")
face = glob.glob(f"{INP}/face.*")[0]; voice = glob.glob(f"{INP}/voice.*")[0]
sh(f"ffmpeg -v error -y -i {voice} -ac 1 -ar 16000 {T}/voice.wav")
print("setup", round(time.time() - t0), "s", flush=True)
procs = {}
for gpu, nf in enumerate((8, 12)):
    rd = f"{T}/run_f{nf}"
    sh(f"cp -r {T}/repo {rd} && rm -rf {rd}/checkpoints && ln -s {T}/ckpt16 {rd}/checkpoints && "
       f"sed -i 's/^  num_frames: 16/  num_frames: {nf}/' {rd}/configs/unet/stage2_512.yaml && grep -n 'num_frames' {rd}/configs/unet/stage2_512.yaml")
    env = f"CUDA_VISIBLE_DEVICES={gpu} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True"
    cmd = (f"cd {rd} && {env} {PY} -m scripts.inference --unet_config_path configs/unet/stage2_512.yaml "
           f"--inference_ckpt_path checkpoints/latentsync_unet.pt --inference_steps 20 --guidance_scale 1.5 "
           f"--enable_deepcache --video_path {face} --audio_path {T}/voice.wav --video_out_path {OUT}/ls16_f{nf}.mp4")
    procs[nf] = subprocess.Popen(cmd, shell=True, stdout=open(f"{OUT}/ls16_f{nf}.log", "w"), stderr=subprocess.STDOUT)
t1 = time.time()
rc = {str(k): p.wait() for k, p in procs.items()}
json.dump({"rc": rc, "setup_s": round(t1 - t0), "infer_s": round(time.time() - t1)}, open(f"{OUT}/summary.json", "w"))
print(rc)
sys.exit(0 if any(v == 0 for v in rc.values()) else 1)
