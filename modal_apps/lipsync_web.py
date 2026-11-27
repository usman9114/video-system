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
    # flash_attn skipped on purpose: wan/modules/attention.py falls back to torch SDPA
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

    @web.get("/result/{call_id}")
    def result(call_id: str):
        try:
            return {"status": "done", **modal.FunctionCall.from_id(call_id).get(timeout=0)}
        except TimeoutError:
            return {"status": "running"}

    return web
