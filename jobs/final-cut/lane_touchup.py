"""Touch-up shard (one per T4): face detail (GFPGAN v1.4, Apache-2.0; RetinaFace/parsing from facexlib, MIT) blended
LIGHTLY into frames [F0, F1) of the master -> lossless /tmp/fc/touched_<k>.mkv. lane_finish.py joins the shards,
encodes, makes the side-by-sides and runs SyncNet on the touched cut. `--prepare` installs once before the shards.
Realism-first: only the largest face >= min_face_px is touched, only its skin/mouth parse mask (paste_back), and only
`blend` of the restoration is mixed in. The result is a candidate; the owner's eye decides (production.json final_cut)."""
import json, os, subprocess, sys, threading, time, urllib.request
import numpy as np
import cv2

W = "/tmp/fc"; os.makedirs(W, exist_ok=True); os.chdir(W)   # facexlib/gfpgan save weights relative to cwd (LESSONS #31)
PREPARE = sys.argv[1] == "--prepare"
MODEL = f"{W}/GFPGANv1.4.pth"


def sh(c):
    print("+", c, flush=True); subprocess.run(c, shell=True, check=True)


if PREPARE:
    # Fast path on Kaggle's torch (LESSONS #28): no-deps for the torch-pinning packages, build basicsr against Kaggle's torch.
    sh(f"{sys.executable} -m pip install -q addict future lmdb yapf filterpy")
    sh(f"{sys.executable} -m pip install -q --no-deps facexlib==0.3.0 gfpgan==1.3.8")      # both ship wheels
    # basicsr 1.4.2 is sdist-only and its setup.py can't run on Kaggle's Python 3.13 (`return locals()['__version__']`
    # -> KeyError, PEP 667). It is pure Python, so use the source tree on sys.path instead of installing it.
    BS = "https://files.pythonhosted.org/packages/86/41/00a6b000f222f0fa4c6d9e1d6dcc9811a374cabb8abb9d408b77de39648c/basicsr-1.4.2.tar.gz"
    sh(f"cd {W} && curl -sL {BS} | tar xz")
    sh(f"sed -i 's/torchvision.transforms.functional_tensor/torchvision.transforms.functional/' "
       f"{W}/basicsr-1.4.2/basicsr/data/degradations.py")                                    # torchvision>=0.17
    if not os.path.exists(MODEL):
        urllib.request.urlretrieve("https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth", MODEL)
    from facexlib.utils.face_restoration_helper import FaceRestoreHelper  # downloads RetinaFace + parsing weights once
    FaceRestoreHelper(1, face_size=512, det_model="retinaface_resnet50", use_parse=True, model_rootpath="gfpgan/weights")
    sys.exit(0)

sys.path.insert(0, f"{W}/basicsr-1.4.2")
master, OUT, man = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
F0, F1, K = int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])    # this shard = frames [F0, F1)
fd = man["touchup"]["face_detail"]

import torch  # noqa: E402
from gfpgan import GFPGANer  # noqa: E402
from skimage.metrics import structural_similarity as ssim  # noqa: E402

info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                           "stream=width,height,r_frame_rate", "-of", "json", master]))["streams"][0]
w, h, rate = info["width"], info["height"], info["r_frame_rate"]
rd = subprocess.Popen(["ffmpeg", "-v", "error", "-i", master, "-vf", f"select=between(n\\,{F0}\\,{F1 - 1})",
                       "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
wr = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", rate,
                       "-i", "-", "-c:v", "ffv1", f"{W}/touched_{K}.mkv"], stdin=subprocess.PIPE)   # lossless shard

g = GFPGANer(model_path=MODEL, upscale=1, arch="clean", channel_multiplier=2, bg_upsampler=None,
             device=torch.device("cuda"))
a = float(fd["blend"])
stats, boxes = [], []
t0 = time.time()
n = 0
while True:
    buf = rd.stdout.read(w * h * 3)
    if len(buf) < w * h * 3:
        break
    rgb = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    out = rgb
    with torch.inference_mode():
        _, _, rest = g.enhance(bgr, has_aligned=False, only_center_face=True, paste_back=True)
    df = np.asarray(g.face_helper.det_faces, dtype=np.float32).reshape(-1, 5)   # only_center_face -> one flat box
    det = [b for b in df if (b[2] - b[0]) >= fd["min_face_px"]]
    if rest is not None and det:
        wgt = np.float32(a)
        lm = np.asarray(g.face_helper.all_landmarks_5, dtype=np.float32).reshape(-1, 5, 2)
        if fd.get("protect_mouth") and len(lm):
            # keep the lip-synced mouth exactly as generated: GFPGAN re-draws lips and costs SyncNet confidence
            (mlx, mly), (mrx, mry) = lm[0][3], lm[0][4]
            d = float(np.hypot(mrx - mlx, mry - mly))
            m = np.zeros((h, w), np.float32)
            cv2.ellipse(m, (int((mlx + mrx) / 2), int((mly + mry) / 2 + 0.15 * d)),
                        (int(d * fd["mouth_w"]), int(d * fd["mouth_h"])), 0, 0, 360, 1.0, -1)
            m = cv2.GaussianBlur(m, (0, 0), d * 0.25)
            wgt = (a * (1 - m))[:, :, None]
        mix = (bgr.astype(np.float32) * (1 - wgt) + rest.astype(np.float32) * wgt).round().clip(0, 255).astype(np.uint8)
        out = np.ascontiguousarray(mix[:, :, ::-1])
        x0, y0, x1, y1 = [int(round(v)) for v in det[0][:4]]
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        s = ssim(rgb[y0:y1, x0:x1].mean(2), out[y0:y1, x0:x1].mean(2), data_range=255)
        stats.append({"frame": F0 + n, "face_ssim": round(float(s), 4), "box": [x0, y0, x1, y1]})
        boxes.append([x0, y0, x1, y1])
    wr.stdin.write(out.tobytes())
    n += 1
    if n % 150 == 0:
        print(f"touchup: {n} frames, {n / (time.time() - t0):.1f} fps, faces touched {len(stats)}", flush=True)
wr.stdin.close(); wr.wait(); rd.wait()
json.dump({"frames": n, "seconds": round(time.time() - t0, 1), "blend": a, "per_frame": stats},
          open(f"{W}/touchup_{K}.json", "w"))
print(f"touchup shard {K}: frames {F0}-{F1}, {n} done, {len(stats)} faces, {time.time() - t0:.0f}s", flush=True)
