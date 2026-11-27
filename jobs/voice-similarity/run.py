"""Objective voice similarity: speaker identity (SpeechBrain ECAPA-TDNN, Apache-2.0) + pitch/timbre stats.
Inputs ($KGPU_INPUT): real/*.wav (owner's real voice chunks), <candidate>/*.wav (clones).
Score = cosine similarity of each clip's speaker embedding to the mean REAL embedding.
Real-vs-real is leave-one-out (each real chunk vs the mean of the other real chunks), giving the ceiling.
Fast path: plain pip, Kaggle's preinstalled torch (docs/LESSONS.md #28)."""
import glob, json, os, subprocess, sys
INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
import torch
open("/tmp/c.txt", "w").write(f"torch=={torch.__version__}\n")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-c", "/tmp/c.txt", "speechbrain==1.0.3", "librosa"], check=True)
import numpy as np, librosa, torchaudio
if not hasattr(torchaudio, "list_audio_backends"):   # torchaudio>=2.9 removed it; speechbrain 1.0.3 still calls it
    torchaudio.list_audio_backends = lambda: ["soundfile"]
import huggingface_hub as _hh   # speechbrain 1.0.3 passes use_auth_token (removed in huggingface_hub>=1.0): drop it
_orig = _hh.hf_hub_download
def _dl(*a, use_auth_token=None, **k):
    return _orig(*a, **k)
_hh.hf_hub_download = _dl
from speechbrain.inference.speaker import EncoderClassifier
from huggingface_hub import snapshot_download   # speechbrain 1.0.3 passes use_auth_token, removed in new hub: load locally
src = snapshot_download("speechbrain/spkrec-ecapa-voxceleb", local_dir="/tmp/ecapa_src")
enc = EncoderClassifier.from_hparams(source=src, savedir="/tmp/ecapa", run_opts={"device": "cuda"})

def load(p):
    y, _ = librosa.load(p, sr=16000, mono=True)
    y, _ = librosa.effects.trim(y, top_db=35)
    return y

def emb(y):
    with torch.no_grad():
        e = enc.encode_batch(torch.tensor(y)[None].cuda()).squeeze().cpu().numpy()
    return e / np.linalg.norm(e)

def stats(y):
    f0, vf, _ = librosa.pyin(y, fmin=60, fmax=300, sr=16000, frame_length=1024)
    f0 = f0[~np.isnan(f0)]
    semis = 12 * np.log2(f0 / np.median(f0)) if len(f0) else np.array([0.0])
    cent = librosa.feature.spectral_centroid(y=y, sr=16000).mean()
    return {"f0_median_hz": round(float(np.median(f0)), 1) if len(f0) else None,
            "pitch_variation_semitones": round(float(np.std(semis)), 2),
            "brightness_hz": round(float(cent)), "voiced_ratio": round(float(np.mean(vf)), 2)}

groups = {}
for d in sorted(glob.glob(f"{INP}/*/")):
    g = os.path.basename(d.rstrip("/"))
    groups[g] = {os.path.basename(f): load(f) for f in sorted(glob.glob(d + "*.wav"))}
E = {g: {n: emb(y) for n, y in clips.items()} for g, clips in groups.items()}
real = E["real"]
res = {"per_clip": {}, "summary": {}}
for g, clips in E.items():
    sims = []
    for n, e in clips.items():
        others = [v for k, v in real.items() if not (g == "real" and k == n)]
        m = np.mean(others, 0); m /= np.linalg.norm(m)
        s = float(e @ m); sims.append(s)
        res["per_clip"][f"{g}/{n}"] = {"similarity": round(s, 3), **stats(groups[g][n])}
    st = [res["per_clip"][f"{g}/{n}"] for n in clips]
    res["summary"][g] = {"clips": len(sims), "similarity_mean": round(float(np.mean(sims)), 3),
                         "similarity_min": round(float(np.min(sims)), 3),
                         "f0_median_hz": round(float(np.median([x["f0_median_hz"] for x in st if x["f0_median_hz"]])), 1),
                         "pitch_variation_semitones": round(float(np.mean([x["pitch_variation_semitones"] for x in st])), 2),
                         "brightness_hz": round(float(np.mean([x["brightness_hz"] for x in st])))}
json.dump(res, open(f"{OUT}/similarity.json", "w"), indent=1)
print(json.dumps(res["summary"], indent=1))
