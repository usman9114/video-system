"""Modal app: open-source lip-sync (TBDub, Apache-2.0) on a 48 GB L40S, paid from Modal's free monthly credits.

    modal run modal_apps/lipsync.py::download_weights                 # once; CPU only, fills the Volume (~15 GB per variant)
    modal run modal_apps/lipsync.py --video face.mp4 --audio voice.wav --mode student --out out.mp4
    modal run modal_apps/lipsync.py --video face.mp4 --audio voice.wav --mode teacher --out out.mp4

Cost control: GPU containers scale to zero right after the call (scaledown_window=2), timeout 20 min, weights are
read from a Volume (no GPU time spent downloading). Each call reports GPU seconds and approximate $ (L40S about $1.95/h).
TBDub: github.com/TaoLiveAIGC/TBDub (Taobao Live, 2026), weights TaoLiveAIGC/TBDub + KlingTeam/X-Dub VAE.
"""
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


@app.function(image=tbdub_image, volumes={W: weights}, timeout=3600, cpu=4)
def download_weights(variants: str = "student,teacher"):
    """CPU-only: download TBDub checkpoints into the Volume (no GPU billed)."""
    import subprocess
    ck = f"{W}/tbdub"
    files = ["config.json", "null_prompt_emb.pt"] + [f"tbdub_{v}.safetensors" for v in variants.split(",")]
    cmds = [
        f"hf download TaoLiveAIGC/TBDub {' '.join(files)} --local-dir {ck}",
        f"hf download KlingTeam/X-Dub Wan2.2_VAE.safetensors --local-dir {ck}",
        f"hf download facebook/hubert-large-ll60k config.json preprocessor_config.json pytorch_model.bin --local-dir {ck}/hubert-large-ll60k",
        f"curl -fsSL https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task -o {ck}/face_landmarker.task",
    ]
    for c in cmds:
        print("+", c, flush=True)
        subprocess.run(c, shell=True, check=True)
    weights.commit()
    subprocess.run(f"du -sh {ck}/*", shell=True)


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
    return {"ok": r.returncode == 0 and bool(outs), "video": Path(outs[-1]).read_bytes() if outs else b"",
            "log": (r.stdout + r.stderr)[-4000:], "gpu_seconds": round(secs, 1), "usd": round(secs * L40S_USD_PER_S, 3)}


@app.local_entrypoint()
def main(video: str, audio: str, out: str, mode: str = "student"):
    import json
    res = tbdub.remote(Path(video).read_bytes(), Path(audio).read_bytes(), mode)
    if not res["ok"]:
        print(res["log"])
        raise SystemExit("tbdub failed")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(res["video"])
    rec = {"op": "tbdub", "mode": mode, "gpu_seconds": res["gpu_seconds"], "usd": res["usd"], "out": out,
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open("reports/modal-usage.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))
