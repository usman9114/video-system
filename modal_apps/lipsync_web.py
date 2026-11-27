"""Modal app with an HTTPS API, so it can be driven from a cloud session whose proxy can't do gRPC.

Deploy (from GitHub Actions or a laptop with the Modal CLI, NOT from the Claude cloud session):
    modal deploy modal_apps/lipsync_web.py
→ one fixed URL: https://<workspace>--video-system-lipsync-api.<region>.modal.run
Auth: header `x-api-key` must equal API_KEY from the Modal secret "lipsync-api-key" (created by the GitHub Actions
deploy from repo secret LIPSYNC_API_KEY; the Claude session sends it via a proxy-injected network secret).

Routes:
  POST /download            {"variants": "student,teacher"}            → {"call_id"}  (CPU; fills the weights Volume)
  POST /lipsync             {"video_b64", "audio_b64", "mode"}          → {"call_id"}  (L40S GPU)
  GET  /result/{call_id}                                                 → {"status": "running"} | result dict
  GET  /health                                                           → {"ok": true}
Cost control: GPU scales to zero 2 s after a job; 20 min timeout; weights on a Volume (no GPU spent downloading).
"""
import base64
import time
from pathlib import Path

import modal

app = modal.App("video-system-lipsync")
weights = modal.Volume.from_name("lipsync-weights", create_if_missing=True)
W = "/weights"
L40S_USD_PER_S = 0.000542

tbdub_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "curl")
    .run_commands("git clone --depth 1 https://github.com/TaoLiveAIGC/TBDub.git /opt/TBDub")
    .pip_install("torch==2.9.0", "torchvision==0.24.0", index_url="https://download.pytorch.org/whl/cu128")
    .run_commands("pip install -r /opt/TBDub/requirements.txt", "pip install 'huggingface_hub[cli]'")
)
api_image = modal.Image.debian_slim(python_version="3.11").pip_install("fastapi[standard]")


@app.function(image=tbdub_image, volumes={W: weights}, timeout=3600, cpu=4)
def download_weights(variants: str = "student,teacher") -> dict:
    import subprocess
    ck = f"{W}/tbdub"
    files = ["config.json", "null_prompt_emb.pt"] + [f"tbdub_{v}.safetensors" for v in variants.split(",")]
    cmds = [
        f"hf download TaoLiveAIGC/TBDub {' '.join(files)} --local-dir {ck}",
        f"hf download KlingTeam/X-Dub Wan2.2_VAE.safetensors --local-dir {ck}",
        f"hf download facebook/hubert-large-ll60k config.json preprocessor_config.json pytorch_model.bin --local-dir {ck}/hubert-large-ll60k",
        f"curl -fsSL https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task -o {ck}/face_landmarker.task",
    ]
    log = []
    for c in cmds:
        r = subprocess.run(c, shell=True, capture_output=True, text=True)
        log.append(f"$ {c}\n{r.returncode} {r.stderr[-400:]}")
        if r.returncode:
            return {"ok": False, "log": log}
    weights.commit()
    du = subprocess.run(f"du -sh {ck}/*", shell=True, capture_output=True, text=True).stdout
    return {"ok": True, "log": log, "du": du}


@app.function(image=tbdub_image, volumes={W: weights}, gpu="L40S", timeout=1200, scaledown_window=2)
def tbdub(video: bytes, audio: bytes, mode: str = "student") -> dict:
    import glob
    import os
    import subprocess
    t0 = time.time()
    os.makedirs("/tmp/in", exist_ok=True)
    Path("/tmp/in/face.mp4").write_bytes(video)
    Path("/tmp/in/voice_src").write_bytes(audio)
    subprocess.run("ffmpeg -v error -y -i /tmp/in/voice_src -ac 1 -ar 16000 /tmp/in/voice.wav", shell=True, check=True)
    args = ["python", "/opt/TBDub/inference.py", "--video", "/tmp/in/face.mp4", "--audio", "/tmp/in/voice.wav",
            "--checkpoint-dir", f"{W}/tbdub", "--inference-mode", mode, "--seed", "42", "--output-dir", "/tmp/out"]
    if mode == "student":
        args += ["--num-student-steps", "2", "--sigma-shift", "1.0", "--motion-from-latents"]
    r = subprocess.run(args, capture_output=True, text=True)
    outs = sorted(glob.glob("/tmp/out/**/*.mp4", recursive=True), key=os.path.getmtime)
    secs = time.time() - t0
    return {"ok": r.returncode == 0 and bool(outs),
            "video_b64": base64.b64encode(Path(outs[-1]).read_bytes()).decode() if outs else "",
            "log": (r.stdout + r.stderr)[-4000:], "gpu_seconds": round(secs, 1), "usd": round(secs * L40S_USD_PER_S, 3)}


# ---------------- Wan 2.2 (Alibaba, Apache-2.0): image/text → video, task 2 exploration ----------------
WAN_REPOS = {"ti2v-5B": "Wan-AI/Wan2.2-TI2V-5B", "i2v-A14B": "Wan-AI/Wan2.2-I2V-A14B"}
H100_USD_PER_S = 0.001097

wan_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0")
    .run_commands("git clone --depth 1 https://github.com/Wan-Video/Wan2.2.git /opt/Wan2.2")
    .pip_install("torch==2.6.0", "torchvision==0.21.0", "torchaudio==2.6.0")
    # flash-attn REQUIRED: Wan's model.py calls flash_attention() directly (varlen), no SDPA fallback there.
    # Official prebuilt wheel for torch 2.6 / CUDA 12 / py3.11 (no hour-long compile). docs/LESSONS.md #54
    .pip_install("https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.4.post1/flash_attn-2.7.4.post1+cu12torch2.6cxx11abiFALSE-cp311-cp311-linux_x86_64.whl")
    .run_commands("grep -v -E '^flash_attn' /opt/Wan2.2/requirements.txt > /tmp/req.txt && pip install -r /tmp/req.txt",
                  "pip install 'huggingface_hub[cli]' einops decord librosa peft loguru omegaconf onnxruntime matplotlib",
                  # wan/__init__.py imports speech2video + animate even for i2v/ti2v; their extra deps (SAM etc.) aren't
                  # needed here, so make those two imports optional (docs/LESSONS.md #52)
                  "sed -i 's/^from .speech2video import WanS2V/try:\\n    from .speech2video import WanS2V\\nexcept Exception:\\n    WanS2V = None/; "
                  "s/^from .animate import WanAnimate/try:\\n    from .animate import WanAnimate\\nexcept Exception:\\n    WanAnimate = None/' "
                  "/opt/Wan2.2/wan/__init__.py && python -c \"import ast, einops, decord, librosa, peft; ast.parse(open('/opt/Wan2.2/wan/__init__.py').read()); print('wan deps ok')\"")
)


@app.function(image=wan_image, volumes={W: weights}, timeout=7200, cpu=4)
def download_wan(model: str = "ti2v-5B") -> dict:
    import subprocess
    dst = f"{W}/wan/{model}"
    r = subprocess.run(f"hf download {WAN_REPOS[model]} --local-dir {dst}", shell=True, capture_output=True, text=True)
    weights.commit()
    du = subprocess.run(f"du -sh {dst}", shell=True, capture_output=True, text=True).stdout
    return {"ok": r.returncode == 0, "log": r.stderr[-1500:], "du": du}


def _wan_generate(task: str, model: str, prompt: str, image: bytes, size: str, frame_num: int, steps: int,
                  seed: int, extra: list, rate: float) -> dict:
    import glob
    import os
    import subprocess
    t0 = time.time()
    args = ["python", "/opt/Wan2.2/generate.py", "--task", task, "--size", size, "--ckpt_dir", f"{W}/wan/{model}",
            "--prompt", prompt, "--base_seed", str(seed), "--save_file", "/tmp/wan_out.mp4", *extra]
    if frame_num:
        args += ["--frame_num", str(frame_num)]
    if steps:
        args += ["--sample_steps", str(steps)]
    if image:
        Path("/tmp/wan_in.png").write_bytes(image)
        args += ["--image", "/tmp/wan_in.png"]
    r = subprocess.run(args, capture_output=True, text=True, cwd="/opt/Wan2.2")
    secs = time.time() - t0
    ok = r.returncode == 0 and os.path.exists("/tmp/wan_out.mp4")
    return {"ok": ok, "video_b64": base64.b64encode(Path("/tmp/wan_out.mp4").read_bytes()).decode() if ok else "",
            "log": (r.stdout + r.stderr)[-4000:], "gpu_seconds": round(secs, 1), "usd": round(secs * rate, 3)}


@app.function(image=wan_image, volumes={W: weights}, gpu="L40S", timeout=3600, scaledown_window=2)
def wan_ti2v_5b(prompt: str, image: bytes = b"", size: str = "1280*704", frame_num: int = 121, steps: int = 50,
                seed: int = 42) -> dict:
    return _wan_generate("ti2v-5B", "ti2v-5B", prompt, image, size, frame_num, steps, seed,
                         ["--offload_model", "True", "--convert_model_dtype", "--t5_cpu"], L40S_USD_PER_S)


@app.function(image=wan_image, volumes={W: weights}, gpu="H100", timeout=3600, scaledown_window=2)
def wan_i2v_a14b(prompt: str, image: bytes = b"", size: str = "1280*720", frame_num: int = 81, steps: int = 40,
                 seed: int = 42) -> dict:
    return _wan_generate("i2v-A14B", "i2v-A14B", prompt, image, size, frame_num, steps, seed,
                         ["--offload_model", "True", "--convert_model_dtype"], H100_USD_PER_S)


# ---------------- FastWan2.2-TI2V-5B (FastVideo, Apache-2.0): 3-step distilled TI2V-5B, BATCHED (cost-optimised) --------
FASTWAN_REPO = "FastVideo/FastWan2.2-TI2V-5B-FullAttn-Diffusers"
fastwan_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.6.0", "torchvision==0.21.0")
    .pip_install("diffusers==0.35.1", "transformers==4.51.3", "accelerate", "ftfy", "imageio[ffmpeg]", "pillow",
                 "huggingface_hub[cli]", "sentencepiece")
)


@app.function(image=fastwan_image, volumes={W: weights}, timeout=3600, cpu=4)
def download_fastwan() -> dict:
    import subprocess
    dst = f"{W}/fastwan/ti2v-5b"
    r = subprocess.run(f"hf download {FASTWAN_REPO} --local-dir {dst}", shell=True, capture_output=True, text=True)
    weights.commit()
    du = subprocess.run(f"du -sh {dst}", shell=True, capture_output=True, text=True).stdout
    return {"ok": r.returncode == 0, "log": r.stderr[-1200:], "du": du}


@app.function(image=fastwan_image, volumes={W: weights}, gpu="L40S", timeout=3600, scaledown_window=2)
def fastwan_batch(items: list, steps: int = 3, fps: int = 24, gpu: str = "L40S") -> dict:
    """items: [{"image_b64", "prompt", "seconds"(3.5), "seed"}]. Loads the model ONCE, animates every photo.
    Returns per-item mp4 (b64) + timing. Distilled → guidance 1.0 (no CFG pass)."""
    import io
    import torch
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
    from diffusers.utils import export_to_video
    from PIL import Image
    t0 = time.time()
    path = f"{W}/fastwan/ti2v-5b"
    vae = AutoencoderKLWan.from_pretrained(path, subfolder="vae", torch_dtype=torch.float32)
    pipe = WanImageToVideoPipeline.from_pretrained(path, vae=vae, torch_dtype=torch.bfloat16).to("cuda")
    load_s = time.time() - t0
    out = []
    for it in items:
        t1 = time.time()
        from PIL import ImageOps
        # phone photos are often stored sideways + an EXIF rotation tag → apply it first
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(base64.b64decode(it["image_b64"])))).convert("RGB")
        w, h = img.size
        # TI2V-5B native 1280x704 / 704x1280 (multiples of 32); keep orientation
        orient = it.get("orient") or ("landscape" if w >= h else "portrait")
        W_, H_ = (1280, 704) if orient == "landscape" else (704, 1280)
        # cover-crop to the model's aspect (never squash a 4:3 phone photo into 16:9); optional focus x/y 0..1
        from PIL import ImageOps
        img = ImageOps.fit(img, (W_, H_), method=Image.LANCZOS,
                           centering=(float(it.get("focus_x", 0.5)), float(it.get("focus_y", 0.5))))
        n = int(it["frames"]) if it.get("frames") else int(round(it.get("seconds", 3.5) * fps / 4)) * 4 + 1
        g = torch.Generator("cuda").manual_seed(int(it.get("seed", 42)))
        frames = pipe(image=img, prompt=it["prompt"], height=H_, width=W_, num_frames=n, num_inference_steps=steps,
                      guidance_scale=1.0, generator=g).frames[0]
        export_to_video(frames, "/tmp/clip.mp4", fps=fps)
        out.append({"video_b64": base64.b64encode(Path("/tmp/clip.mp4").read_bytes()).decode(), "frames": n,
                    "seconds": round(time.time() - t1, 1)})
    secs = time.time() - t0
    return {"ok": True, "items": out, "load_seconds": round(load_s, 1), "gpu_seconds": round(secs, 1),
            "gpu": gpu, "usd": round(secs * (H100_USD_PER_S if gpu == "H100" else L40S_USD_PER_S), 3)}


# ---------------- Lip-sync A/B candidates (owner 2026-11-27): LatentSync 1.6 full settings, X-Dub ----------------
latentsync_image = (
    modal.Image.debian_slim(python_version="3.11")          # Modal's 2026.10 builder dropped 3.10 (LESSONS #72)
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "build-essential")   # insightface builds from source on 3.11
    .run_commands("git clone --depth 1 https://github.com/bytedance/LatentSync.git /opt/LatentSync",
                  "pip install -r /opt/LatentSync/requirements.txt", "pip install 'huggingface_hub[cli]<1'")
)
xdub_image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "build-essential", "ninja-build")
    .run_commands("git clone --depth 1 https://github.com/KlingAIResearch/X-Dub.git /opt/X-Dub",
                  # upstream pins opencv 4.13 (needs numpy>=2) next to numpy 1.26.4 (chumpy/mmcv need <2): use the last
                  # numpy-1.x opencv instead (LESSONS #73)
                  "sed -i 's/^opencv-python==.*/opencv-python==4.10.0.84/' /opt/X-Dub/requirements.txt",
                  "pip install -r /opt/X-Dub/requirements.txt", "pip install setuptools wheel cython 'numpy==1.26.4'")
    # OpenMMLab stack per the X-Dub README; mmcv compiled with CUDA ops for Ada (L40S) + Hopper (H100)
    .env({"FORCE_CUDA": "1", "MMCV_WITH_OPS": "1", "TORCH_CUDA_ARCH_LIST": "8.9;9.0", "MAX_JOBS": "8"})
    .run_commands("pip install chumpy==0.70 --no-build-isolation", "pip install mmengine==0.10.7",
                  "pip install mmcv==2.1.0 --no-build-isolation", "pip install mmdet==3.2.0 mmpose==1.3.2",
                  "cd /opt/X-Dub && pip install -e . --no-deps", gpu="L40S")
)


@app.function(image=latentsync_image, volumes={W: weights}, timeout=3600, cpu=4)
def download_latentsync() -> dict:
    import subprocess
    ck = f"{W}/latentsync16"
    r = subprocess.run(f"huggingface-cli download ByteDance/LatentSync-1.6 whisper/tiny.pt latentsync_unet.pt --local-dir {ck}",
                       shell=True, capture_output=True, text=True)
    weights.commit()
    return {"ok": r.returncode == 0, "log": r.stderr[-1500:]}


@app.function(image=xdub_image, volumes={W: weights}, timeout=7200, cpu=4)
def download_xdub() -> dict:
    import subprocess
    r = subprocess.run(f"hf download KlingTeam/X-Dub --local-dir {W}/xdub --repo-type model", shell=True,
                       capture_output=True, text=True)
    weights.commit()
    du = subprocess.run(f"du -sh {W}/xdub", shell=True, capture_output=True, text=True).stdout
    return {"ok": r.returncode == 0, "log": r.stderr[-1500:], "du": du}


def _prep_inputs(video: bytes, audio: bytes, fps: int | None = None):
    import os
    import subprocess
    os.makedirs("/tmp/in", exist_ok=True)
    Path("/tmp/in/face_src.mp4").write_bytes(video)
    Path("/tmp/in/voice_src").write_bytes(audio)
    vf = ["-r", str(fps)] if fps else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", "/tmp/in/face_src.mp4", *vf, "-c:v", "libx264", "-crf", "12",
                    "-an", "/tmp/in/face.mp4"], check=True)
    subprocess.run("ffmpeg -v error -y -i /tmp/in/voice_src -ac 1 -ar 16000 /tmp/in/voice.wav", shell=True, check=True)


def _result(r, outs, t0, rate=L40S_USD_PER_S):
    secs = time.time() - t0
    return {"ok": r.returncode == 0 and bool(outs),
            "video_b64": base64.b64encode(Path(outs[-1]).read_bytes()).decode() if outs else "",
            "log": (r.stdout + r.stderr)[-4000:], "gpu_seconds": round(secs, 1), "usd": round(secs * rate, 3)}


@app.function(image=latentsync_image, volumes={W: weights}, gpu="L40S", timeout=3600, scaledown_window=2)
def latentsync16(video: bytes, audio: bytes, steps: int = 50, guidance: float = 1.5, deepcache: bool = False) -> dict:
    """LatentSync 1.6 at full settings (512 px, stage2_512, num_frames 16; the T4 test was crippled to 6 frames)."""
    import glob
    import os
    import subprocess
    t0 = time.time()
    _prep_inputs(video, audio, fps=25)                       # LatentSync is trained on 25 fps
    os.makedirs("/opt/LatentSync/checkpoints", exist_ok=True)
    for f in ("latentsync_unet.pt", "whisper"):
        dst = f"/opt/LatentSync/checkpoints/{f}"
        if not os.path.exists(dst):
            os.symlink(f"{W}/latentsync16/{f}", dst)
    args = ["python", "-m", "scripts.inference", "--unet_config_path", "configs/unet/stage2_512.yaml",
            "--inference_ckpt_path", "checkpoints/latentsync_unet.pt", "--inference_steps", str(steps),
            "--guidance_scale", str(guidance), "--video_path", "/tmp/in/face.mp4", "--audio_path", "/tmp/in/voice.wav",
            "--video_out_path", "/tmp/out.mp4", "--seed", "1247"] + (["--enable_deepcache"] if deepcache else [])
    r = subprocess.run(args, cwd="/opt/LatentSync", capture_output=True, text=True)
    return _result(r, glob.glob("/tmp/out.mp4"), t0)


@app.function(image=xdub_image, volumes={W: weights}, gpu="L40S", timeout=3600, scaledown_window=2)
def xdub(video: bytes, audio: bytes, steps: int = 30, ref_cfg: float = 2.5, audio_cfg: float = 10.0) -> dict:
    """X-Dub (Kling, Apache-2.0) with the README's recommended settings; auto face crop, pasted back on the full frame."""
    import glob
    import os
    import subprocess
    t0 = time.time()
    _prep_inputs(video, audio)
    ck, dw = "/opt/X-Dub/checkpoints", "/opt/X-Dub/dwpose_tools/models"
    if not os.path.exists(ck):
        os.symlink(f"{W}/xdub", ck)
    os.makedirs(dw, exist_ok=True)
    for f in glob.glob(f"{W}/xdub/dwpose_tools/models/*"):
        dst = f"{dw}/{os.path.basename(f)}"
        if not os.path.exists(dst):
            os.symlink(f, dst)
    args = ["python", "infer_lip_sync_pipeline.py", "--video_path", "/tmp/in/face.mp4", "--audio_path", "/tmp/in/voice.wav",
            "--ref_cfg_scale", str(ref_cfg), "--audio_cfg_scale", str(audio_cfg), "--num_inference_steps", str(steps),
            "--output_dir", "/tmp/out"]
    r = subprocess.run(args, cwd="/opt/X-Dub", capture_output=True, text=True)
    return _result(r, sorted(glob.glob("/tmp/out/**/*.mp4", recursive=True), key=os.path.getmtime), t0)


@app.function(image=api_image, secrets=[modal.Secret.from_name("lipsync-api-key")])
@modal.asgi_app()
def api():
    import hmac
    import os

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    web = FastAPI()
    key = os.environ["API_KEY"]

    @web.middleware("http")
    async def require_key(request: Request, call_next):
        if not hmac.compare_digest(request.headers.get("x-api-key", ""), key):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    @web.get("/health")
    def health():
        return {"ok": True}

    @web.post("/download")
    def download(body: dict):
        return {"call_id": download_weights.spawn(body.get("variants", "student,teacher")).object_id}

    @web.post("/lipsync")
    def lipsync(body: dict):
        call = tbdub.spawn(base64.b64decode(body["video_b64"]), base64.b64decode(body["audio_b64"]),
                           body.get("mode", "student"))
        return {"call_id": call.object_id}

    @web.post("/wan/download")
    def wan_download(body: dict):
        return {"call_id": download_wan.spawn(body.get("model", "ti2v-5B")).object_id}

    @web.post("/wan/generate")
    def wan_generate(body: dict):
        fn = wan_i2v_a14b if body.get("model") == "i2v-A14B" else wan_ti2v_5b
        kw = {k: body[k] for k in ("size", "frame_num", "steps", "seed") if k in body}
        img = base64.b64decode(body["image_b64"]) if body.get("image_b64") else b""
        return {"call_id": fn.spawn(body["prompt"], img, **kw).object_id}

    @web.post("/fastwan/download")
    def fastwan_download(body: dict):
        return {"call_id": download_fastwan.spawn().object_id}

    @web.post("/fastwan/batch")
    def fastwan_run(body: dict):
        gpu = body.get("gpu", "L40S")
        if gpu not in ("L40S", "H100"):
            return {"error": "gpu must be L40S or H100"}
        fn = fastwan_batch.with_options(gpu=gpu) if gpu != "L40S" else fastwan_batch
        return {"call_id": fn.spawn(body["items"], int(body.get("steps", 3)), int(body.get("fps", 24)), gpu).object_id}

    @web.post("/ab/download")
    def ab_download(body: dict):
        fn = download_xdub if body.get("model") == "xdub" else download_latentsync
        return {"call_id": fn.spawn().object_id}

    @web.post("/ab/lipsync")
    def ab_lipsync(body: dict):
        """{"model": "latentsync16"|"xdub", "video_b64", "audio_b64", optional settings} → {"call_id"}"""
        fn = xdub if body.get("model") == "xdub" else latentsync16
        keys = ("steps", "ref_cfg", "audio_cfg") if fn is xdub else ("steps", "guidance", "deepcache")
        kw = {k: body[k] for k in keys if k in body}
        return {"call_id": fn.spawn(base64.b64decode(body["video_b64"]), base64.b64decode(body["audio_b64"]), **kw).object_id}

    @web.get("/result/{call_id}")
    def result(call_id: str):
        try:
            return {"status": "done", **modal.FunctionCall.from_id(call_id).get(timeout=0)}
        except TimeoutError:
            return {"status": "running"}

    return web
