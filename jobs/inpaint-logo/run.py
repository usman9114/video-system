"""LaMa inpainting of a fixed-mask region in every frame, split across all visible GPUs.
Inputs ($KGPU_INPUT): crop.mkv (lossless crop sequence), mask.png (white = remove).
Output ($KGPU_OUTPUT): inpainted.mkv (FFV1, same frame count/fps), stats.json.
Model: big-lama TorchScript (LaMa, Apache-2.0) from enesmsahin/simple-lama-inpainting v0.1.0 release."""
import os, json, time, subprocess, urllib.request
import numpy as np, torch, torch.multiprocessing as mp
from PIL import Image

INP, OUT = os.environ["KGPU_INPUT"], os.environ["KGPU_OUTPUT"]
URL = "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"
MODEL = "/kaggle/working/big-lama.pt"

def probe(path):
    o = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames", "-of", "json", path])
    s = json.loads(o)["streams"][0]
    return s["width"], s["height"], s["r_frame_rate"], int(s["nb_read_frames"])

def read_frames(path, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)

def worker(rank, ngpu, frames, mask, ret):
    dev = f"cuda:{rank}"
    model = torch.jit.load(MODEL, map_location=dev).eval()
    idx = list(range(rank, len(frames), ngpu))
    m = torch.from_numpy(mask).float().div(255).gt(0.5).float()[None, None].to(dev)
    out = {}
    with torch.inference_mode():
        for b in range(0, len(idx), 16):
            ids = idx[b:b + 16]
            x = torch.from_numpy(np.stack([frames[i] for i in ids])).to(dev).permute(0, 3, 1, 2).float() / 255
            y = model(x, m.expand(len(ids), -1, -1, -1))
            y = (y.clamp(0, 1) * 255).round().byte().permute(0, 2, 3, 1).cpu().numpy()
            for i, f in zip(ids, y):
                out[i] = f
    ret.update(out)

def main():
    t0 = time.time()
    if not os.path.exists(MODEL):
        urllib.request.urlretrieve(URL, MODEL)
    crop = os.path.join(INP, "crop.mkv")
    w, h, fps, n = probe(crop)
    frames = read_frames(crop, w, h)
    mask = np.asarray(Image.open(os.path.join(INP, "mask.png")).convert("L"))
    assert mask.shape == (h, w) and w % 8 == 0 and h % 8 == 0, (mask.shape, w, h)
    ngpu = torch.cuda.device_count()
    print("gpus:", ngpu, [torch.cuda.get_device_name(i) for i in range(ngpu)], "frames:", len(frames), flush=True)
    mgr = mp.Manager(); ret = mgr.dict()
    t1 = time.time()
    mp.spawn(worker, args=(ngpu, frames, mask, ret), nprocs=ngpu, join=True)
    res = np.stack([ret[i] for i in range(len(frames))])
    t2 = time.time()
    # light temporal smoothing inside each shot (kills LaMa shimmer); shot cuts = big jumps in the crop
    diff = np.abs(frames[1:].astype(np.int16) - frames[:-1]).mean(axis=(1, 2, 3))
    cuts = set((np.where(diff > 12)[0] + 1).tolist())
    sm = res.astype(np.float32).copy()
    for i in range(len(res)):
        lo, hi = i, i
        for _ in range(2):
            if lo - 1 >= 0 and lo not in cuts: lo -= 1
            if hi + 1 < len(res) and (hi + 1) not in cuts: hi += 1
        sm[i] = res[lo:hi + 1].astype(np.float32).mean(0)
    sm = sm.round().clip(0, 255).astype(np.uint8)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", fps, "-i", "-", "-c:v", "ffv1", "-pix_fmt", "rgb24", os.path.join(OUT, "inpainted.mkv")],
                         stdin=subprocess.PIPE)
    p.stdin.write(sm.tobytes()); p.stdin.close(); p.wait()
    st = {"gpus": ngpu, "frames": len(frames), "size": [w, h], "cuts": sorted(cuts),
          "inpaint_s": round(t2 - t1, 1), "total_s": round(time.time() - t0, 1)}
    json.dump(st, open(os.path.join(OUT, "stats.json"), "w"), indent=1)
    print(st)

if __name__ == "__main__":
    main()
