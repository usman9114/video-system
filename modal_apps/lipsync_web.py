"""Modal app with an HTTPS API, so it can be driven from a cloud session whose proxy can't do gRPC.

Deploy (from GitHub Actions or a laptop with the Modal CLI, NOT from the Claude cloud session):
    modal deploy modal_apps/lipsync_web.py
→ one fixed URL: https://<workspace>--video-system-lipsync-api.modal.run  (requires a Modal proxy auth token:
  headers Modal-Key / Modal-Secret).

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


@app.function(image=api_image)
@modal.asgi_app(requires_proxy_auth=True)
def api():
    from fastapi import FastAPI

    web = FastAPI()

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

    @web.get("/result/{call_id}")
    def result(call_id: str):
        try:
            return {"status": "done", **modal.FunctionCall.from_id(call_id).get(timeout=0)}
        except TimeoutError:
            return {"status": "running"}

    return web
