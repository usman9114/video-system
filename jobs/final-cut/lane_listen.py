"""GPU0 lane: Whisper large-v3 word timestamps on the master's audio, then SyncNet on the master.
openai-whisper on purpose (faster-whisper fails on Kaggle's CUDA 13 image, LESSONS #4)."""
import json, os, subprocess, sys

master, OUT, man = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
HERE = os.path.dirname(os.path.abspath(__file__))

import whisper  # noqa: E402
m = whisper.load_model(man["checks"]["transcript"]["model"], device="cuda")
r = m.transcribe(master, language=man.get("language", "en"), word_timestamps=True,
                 condition_on_previous_text=False, temperature=0)
words = [{"w": w["word"].strip(), "s": round(w["start"], 3), "e": round(w["end"], 3), "p": round(w["probability"], 3)}
         for s in r["segments"] for w in s["words"]]
json.dump({"text": r["text"].strip(), "words": words}, open(f"{OUT}/words.json", "w"), indent=1)
print("listen:", len(words), "words |", r["text"].strip()[:300], flush=True)
del m

if man["kind"] in man["checks"]["lipsync"]["applies_to"]:
    subprocess.run([sys.executable, f"{HERE}/syncnet_tracks.py", master, "master", f"{OUT}/syncnet_master.json"], check=True)
