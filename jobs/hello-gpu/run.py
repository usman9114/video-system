"""Smoke test: prove GPU, torch, ffmpeg and inputs work on Kaggle."""
import os, json, subprocess, pathlib
inp, out = os.environ.get("KGPU_INPUT", ""), os.environ["KGPU_OUTPUT"]
info = {"inputs": sorted(os.listdir(inp)) if inp else []}
try:
    import torch
    info["torch"] = torch.__version__
    info["cuda"] = torch.cuda.is_available()
    info["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    if info["cuda"]:
        x = torch.randn(4096, 4096, device="cuda"); info["matmul_ok"] = float((x @ x).mean()) == float((x @ x).mean())
except Exception as e:
    info["torch_error"] = repr(e)
info["ffmpeg"] = subprocess.run("ffmpeg -version | head -1", shell=True, capture_output=True, text=True).stdout.strip()
for f in (pathlib.Path(inp).glob("*.txt") if inp else []):
    info["echo_" + f.name] = f.read_text().strip()
json.dump(info, open(f"{out}/hello.json", "w"), indent=1)
print(json.dumps(info, indent=1))
