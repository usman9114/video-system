"""Chatterbox (MIT) voice clone, FAST path: plain pip into Kaggle's env, reusing its preinstalled torch (no 2.5 GB
download). Lessons: docs/LESSONS.md #28 (speed), #31 (nothing big under /kaggle/working).
Inputs: ref.wav, job.json {"lines": {...}, "takes": n}. Outputs: chatterbox/<line>_t<k>.wav (+ setup log)."""
import json, os, subprocess, sys, time
INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
t0 = time.time()
import torch
cons = "/tmp/constraints.txt"
open(cons, "w").write(f"torch=={torch.__version__}\n")
try:
    import torchaudio
    open(cons, "a").write(f"torchaudio=={torchaudio.__version__}\n")
except ImportError:
    pass
pip = [sys.executable, "-m", "pip", "install", "-q", "-c", cons]
subprocess.run(pip + ["--no-deps", "chatterbox-tts==0.1.7", "resemble-perth", "conformer==0.3.2", "diffusers==0.29.0",
                      "s3tokenizer", "pykakasi==2.3.0"], check=True)
subprocess.run(pip + ["librosa==0.11.0", "transformers==5.2.0", "pyloudnorm", "omegaconf", "onnx", "setuptools<81",
                      "safetensors"], check=True)
print("setup", round(time.time() - t0), "s", flush=True)
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS
job = json.load(open(f"{INP}/job.json"))
os.makedirs(f"{OUT}/chatterbox", exist_ok=True)
m = ChatterboxTTS.from_pretrained(device="cuda")
print("watermarker:", type(m.watermarker).__name__, flush=True)
m.prepare_conditionals(f"{INP}/ref.wav", exaggeration=job.get("exaggeration", 0.5))
timings = {}
for name, text in job["lines"].items():
    for k in range(job.get("takes", 2)):
        t = time.time(); torch.manual_seed(7 + k)
        wav = m.generate(text, exaggeration=job.get("exaggeration", 0.5), cfg_weight=job.get("cfg", 0.5), temperature=0.8)
        ta.save(f"{OUT}/chatterbox/{name}_t{k}.wav", wav, m.sr); timings[f"{name}_t{k}"] = round(time.time() - t, 2)
json.dump({"timings": timings, "total_s": round(time.time() - t0)}, open(f"{OUT}/chatterbox/timings.json", "w"), indent=1)
print(timings)
