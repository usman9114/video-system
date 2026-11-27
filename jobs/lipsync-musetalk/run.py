"""MuseTalk 1.5 (Tencent Music Lyra Lab; MIT code, weights OpenRAIL-M) lip-sync on Kaggle 2x T4, two variants in parallel:
GPU0 bbox_shift=0, GPU1 bbox_shift=-5 (more open mouth). fp16. Inputs: face.mp4, voice.(mp3|wav).
Env in /tmp (py3.10, torch 2.0.1 cu118, mmcv 2.0.1/mmdet 3.1.0/mmpose 1.1.0 as the README pins). Outputs: mt_b0.mp4, mt_bm5.mp4."""
import os, subprocess, sys, time, glob, json
INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
T = "/tmp/mt"
def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)
t0 = time.time()
sh(f"{sys.executable} -m pip install -q uv")
sh(f"git clone -q --depth 1 https://github.com/TMElyralab/MuseTalk.git {T}/repo")
PY = f"{T}/venv/bin/python"
UV = f"uv pip install -q --python {PY}"
sh(f"cd {T} && uv venv -q -p 3.10 venv")
sh(f"{UV} torch==2.0.1 torchvision==0.15.2 torchaudio==2.0.2 --index-url https://download.pytorch.org/whl/cu118")
sh(f"cd {T}/repo && grep -v -E '^(tensorflow|tensorboard|gradio)' requirements.txt > /tmp/mt_req.txt && {UV} -r /tmp/mt_req.txt")
sh(f"{UV} 'setuptools<70' openmim mmengine 'mmcv==2.0.1' -f https://download.openmmlab.com/mmcv/dist/cu118/torch2.0/index.html")
# chumpy (pulled in by mmpose) has a legacy setup.py that imports pip: build it without isolation first
sh(f"{UV} pip wheel cython 'numpy==1.23.5' && {UV} --no-build-isolation chumpy==0.70")
sh(f"{UV} --no-build-isolation 'mmdet==3.1.0' 'mmpose==1.1.0' gdown")
# weights (same as download_weights.sh, without the hf-mirror endpoint)
dl = ("from huggingface_hub import hf_hub_download as d\n"
      "M='/tmp/mt/repo/models'\n"
      "for f in ('musetalkV15/musetalk.json','musetalkV15/unet.pth'): d('TMElyralab/MuseTalk', f, local_dir=M)\n"
      "for f in ('config.json','diffusion_pytorch_model.bin'): d('stabilityai/sd-vae-ft-mse', f, local_dir=M+'/sd-vae')\n"
      "for f in ('config.json','pytorch_model.bin','preprocessor_config.json'): d('openai/whisper-tiny', f, local_dir=M+'/whisper')\n"
      "d('yzd-v/DWPose','dw-ll_ucoco_384.pth', local_dir=M+'/dwpose')\n")
sh(f"{PY} -c \"{dl}\"")
sh(f"mkdir -p {T}/repo/models/face-parse-bisent && {T}/venv/bin/gdown --id 154JgKpzCPW82qINcVieuPH3fZ2e0P812 -O {T}/repo/models/face-parse-bisent/79999_iter.pth")
sh(f"curl -sL https://download.pytorch.org/models/resnet18-5c106cde.pth -o {T}/repo/models/face-parse-bisent/resnet18-5c106cde.pth")
print("setup", round(time.time() - t0), "s", flush=True)
face = glob.glob(f"{INP}/face.*")[0]; voice = glob.glob(f"{INP}/voice.*")[0]
sh(f"ffmpeg -v error -y -i {face} -r 25 -an -c:v libx264 -crf 12 {T}/face25.mp4 && ffmpeg -v error -y -i {voice} -ac 1 -ar 16000 {T}/voice.wav")
procs = {}
for gpu, (tag, shift) in enumerate((("b0", 0), ("bm5", -5))):
    cfg = f"{T}/task_{tag}.yaml"
    open(cfg, "w").write(f"task_0:\n video_path: \"{T}/face25.mp4\"\n audio_path: \"{T}/voice.wav\"\n bbox_shift: {shift}\n")
    cmd = (f"cd {T}/repo && CUDA_VISIBLE_DEVICES={gpu} {PY} -m scripts.inference --inference_config {cfg} "
           f"--result_dir {T}/res_{tag} --unet_model_path models/musetalkV15/unet.pth --unet_config models/musetalkV15/musetalk.json "
           f"--version v15 --ffmpeg_path /usr/bin/ --use_float16 --output_vid_name mt_{tag}.mp4")
    procs[tag] = subprocess.Popen(cmd, shell=True, stdout=open(f"{OUT}/mt_{tag}.log", "w"), stderr=subprocess.STDOUT)
t1 = time.time()
rc = {k: p.wait() for k, p in procs.items()}
for tag in procs:
    for f in glob.glob(f"{T}/res_{tag}/**/mt_{tag}.mp4", recursive=True):
        sh(f"cp {f} {OUT}/mt_{tag}.mp4")
json.dump({"rc": rc, "setup_s": round(t1 - t0), "infer_s": round(time.time() - t1)}, open(f"{OUT}/summary.json", "w"))
print(rc)
sys.exit(0 if any(os.path.exists(f"{OUT}/mt_{t}.mp4") for t in procs) else 1)
