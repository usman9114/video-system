"""Transcribe every audio/video file in $KGPU_INPUT with Whisper large-v3 (openai-whisper, uses Kaggle's
# NOTE: openai-whisper on purpose; faster-whisper fails on Kaggle CUDA 13 image (docs/LESSONS.md #4)
preinstalled CUDA PyTorch) + word timestamps. Writes <name>.words.json to $KGPU_OUTPUT."""
import os, json, glob
import whisper
inp, out = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
m = whisper.load_model("large-v3", device="cuda")
for f in sorted(glob.glob(inp + "/*")):
    if not f.lower().endswith((".wav", ".mp3", ".m4a", ".mp4", ".flac")):
        continue
    r = m.transcribe(f, language="en", word_timestamps=True, condition_on_previous_text=False, temperature=0)
    data = {"file": os.path.basename(f), "segments": [
        {"start": s["start"], "end": s["end"], "text": s["text"].strip(),
         "words": [{"w": w["word"], "s": w["start"], "e": w["end"], "p": round(w["probability"], 3)} for w in s["words"]]}
        for s in r["segments"]]}
    base = os.path.splitext(os.path.basename(f))[0]
    json.dump(data, open(f"{out}/{base}.words.json", "w"), indent=1)
    print(base, "->", len(data["segments"]), "segments")
    print(" ".join(s["text"] for s in data["segments"]))
