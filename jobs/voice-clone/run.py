"""Voice-clone bake-off on 2x T4: Chatterbox (MIT) on GPU0 and Qwen3-TTS 1.7B Base (Apache-2.0) on GPU1, in parallel.
Inputs ($KGPU_INPUT): ref.wav (owner's real voice, ~9 s), job.json {"ref_text": ..., "lines": {name: text}}.
Each model gets its own uv venv (they pin different torch versions; Kaggle's image is CUDA 13 / torch 2.11).
Outputs: <model>/<line>.wav, timings.json."""
import json, os, subprocess, sys, time, textwrap
INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
job = json.load(open(f"{INP}/job.json"))
ref = f"{INP}/ref.wav"
W = "/kaggle/working"

def sh(cmd, **kw):
    print("+", cmd, flush=True)
    return subprocess.run(cmd, shell=True, check=True, **kw)

sh(f"{sys.executable} -m pip install -q uv")
sh(f"cd {W} && uv venv -q -p 3.11 venv_cb && uv venv -q -p 3.11 venv_qw")
installs = [
    subprocess.Popen(f"cd {W} && uv pip install --python {W}/venv_cb/bin/python chatterbox-tts==0.1.7", shell=True),
    subprocess.Popen(f"cd {W} && uv pip install --python {W}/venv_qw/bin/python qwen-tts==0.1.1 torch==2.6.0 torchaudio==2.6.0 soundfile", shell=True),
]
for p in installs:
    assert p.wait() == 0, "install failed"

CB = textwrap.dedent('''
    import json, os, sys, time, torch, torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
    job = json.load(open(sys.argv[1])); ref, out = sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)
    m = ChatterboxTTS.from_pretrained(device="cuda")
    m.prepare_conditionals(ref, exaggeration=0.45)
    t = {}
    for name, text in job["lines"].items():
        for k in range(job.get("takes", 2)):
            t0 = time.time(); torch.manual_seed(100 + k)
            wav = m.generate(text, exaggeration=0.45, cfg_weight=0.45, temperature=0.7)
            ta.save(f"{out}/{name}_t{k}.wav", wav, m.sr); t[f"{name}_t{k}"] = round(time.time() - t0, 2)
    json.dump(t, open(f"{out}/timings.json", "w"), indent=1); print("chatterbox done", t)
''')
QW = textwrap.dedent('''
    import json, os, sys, time, torch, soundfile as sf
    from qwen_tts import Qwen3TTSModel
    job = json.load(open(sys.argv[1])); ref, out = sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)
    m = Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-Base", device_map="cuda:0",
                                      dtype=torch.float16, attn_implementation="sdpa")   # T4: no bf16 / flash-attn
    prompt = m.create_voice_clone_prompt(ref_audio=ref, ref_text=job["ref_text"], x_vector_only_mode=False)
    t = {}
    for name, text in job["lines"].items():
        for k in range(job.get("takes", 2)):
            t0 = time.time(); torch.manual_seed(100 + k)
            wavs, sr = m.generate_voice_clone(text=text, language="English", voice_clone_prompt=prompt,
                                              do_sample=True, temperature=0.7, top_p=0.9)
            sf.write(f"{out}/{name}_t{k}.wav", wavs[0], sr); t[f"{name}_t{k}"] = round(time.time() - t0, 2)
    json.dump(t, open(f"{out}/timings.json", "w"), indent=1); print("qwen done", t)
''')
open(f"{W}/cb.py", "w").write(CB); open(f"{W}/qw.py", "w").write(QW)
t0 = time.time()
procs = {
    "chatterbox": subprocess.Popen(f"CUDA_VISIBLE_DEVICES=0 {W}/venv_cb/bin/python {W}/cb.py {INP}/job.json {ref} {OUT}/chatterbox", shell=True),
    "qwen3tts": subprocess.Popen(f"CUDA_VISIBLE_DEVICES=1 {W}/venv_qw/bin/python {W}/qw.py {INP}/job.json {ref} {OUT}/qwen3tts", shell=True),
}
rc = {k: p.wait() for k, p in procs.items()}
json.dump({"exit": rc, "wall_s": round(time.time() - t0, 1)}, open(f"{OUT}/summary.json", "w"), indent=1)
print(rc)
sys.exit(0 if all(v == 0 for v in rc.values()) else 1)
