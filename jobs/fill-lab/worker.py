"""Fill-lab worker: work(gpu, man, jobs, out, results) processes its clips on ONE T4. run.py calls it from one thread
per GPU inside the notebook process. (Launching it as a child process got the Kaggle session cancelled ~40 s in,
every time; the same code in-process ran fine. LESSONS #75.) The CUDA current device is per thread, so each thread
sets its own. Nothing touches /kaggle/working except the finished clips."""
import json, math, subprocess, sys, threading, time
import numpy as np
import torch
import torch.nn.functional as F

W = "/tmp/fl"
_lock = threading.Lock()          # model package imports happen once, under a lock


def probe(p):
    s = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                            "stream=width,height,r_frame_rate", "-of", "json", p]))["streams"][0]
    n, d = map(int, s["r_frame_rate"].split("/"))
    return s["width"], s["height"], n / d


def read_all(p, w, h):
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", p, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True, stdin=subprocess.DEVNULL).stdout
    return list(np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3))


def write_all(path, src, frames, w, h, fps, enc):
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-", "-i", src, "-map", "0:v", "-map", "1:a?",
                          "-c:v", "libx264", "-preset", enc["preset"], "-crf", str(enc["crf"]), "-pix_fmt", "yuv420p",
                          "-c:a", "copy", "-shortest", path], stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close()
    p.wait()


class Gpu:
    def __init__(self, gpu, man):
        self.gpu, self.man = gpu, man
        self.dev = torch.device(f"cuda:{gpu}")
        torch.cuda.set_device(self.dev)
        self._rife = self._up = None

    def rife(self):
        if self._rife is None:
            with _lock:
                if f"{W}/rife" not in sys.path:
                    sys.path.insert(0, f"{W}/rife")
                from train_log.RIFE_HDv3 import Model     # its module-level device is "cuda" = this thread's device
            m = Model(); m.load_model(f"{W}/rife/train_log", -1); m.eval(); m.device()
            self._rife = m
        return self._rife

    def interpolate(self, frames, w, h, fps_in, fps_out):
        """Output frame k sits at source position k*fps_in/fps_out: copy when it lands on a frame, else RIFE at t."""
        m, cfg = self.rife(), self.man["interpolate"]
        ph, pw = (64 - h % 64) % 64, (64 - w % 64) % 64
        to_t = lambda a: F.pad(torch.from_numpy(a.copy()).to(self.dev).permute(2, 0, 1)[None].float() / 255,
                               (0, pw, 0, ph))
        n_out = int(math.floor((len(frames) - 1) * fps_out / fps_in + 1e-6)) + 1
        out, cache = [], {}
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16, enabled=cfg["fp16"]):
            for k in range(n_out):
                p = k * fps_in / fps_out
                i = int(math.floor(p + 1e-6)); t = p - i
                if t < 1e-3 or i + 1 >= len(frames):
                    out.append(frames[min(i, len(frames) - 1)]); continue
                for j in (i, i + 1):
                    if j not in cache:
                        cache[j] = to_t(frames[j])
                for j in [x for x in cache if x < i]:
                    del cache[j]
                y = m.inference(cache[i], cache[i + 1], timestep=t, scale=cfg["scale"])
                out.append((y[0, :, :h, :w].float().clamp(0, 1) * 255).round().byte().permute(1, 2, 0).cpu().numpy())
        return out

    def upscaler(self):
        if self._up is None:
            with _lock:
                if f"{W}/basicsr-1.4.2" not in sys.path:
                    sys.path.insert(0, f"{W}/basicsr-1.4.2")
                from basicsr.archs.rrdbnet_arch import RRDBNet
                from realesrgan import RealESRGANer
            net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
            self._up = RealESRGANer(scale=2, model_path=f"{W}/RealESRGAN_x2plus.pth", model=net,
                                    tile=self.man["upscale"]["tile"], half=True, device=self.dev)
        return self._up

    def upscale(self, frames, w, h, scale):
        from PIL import Image
        u = self.upscaler()
        ow, oh = int(round(w * scale / 2)) * 2, int(round(h * scale / 2)) * 2
        out = []
        for f in frames:
            y, _ = u.enhance(np.ascontiguousarray(f[:, :, ::-1]), outscale=2)
            out.append(np.asarray(Image.fromarray(np.ascontiguousarray(y[:, :, ::-1])).resize((ow, oh), Image.LANCZOS)))
        return out, ow, oh


def work(gpu, man, jobs, OUT, results):
    g = Gpu(gpu, man)
    print(f"[w{gpu}] start {[j['name'] for j in jobs]} {torch.cuda.get_device_name(gpu)}", flush=True)
    for j in jobs:
        t0 = time.time()
        w, h, fps = probe(j["path"])
        frames = read_all(j["path"], w, h)
        rec = {"name": j["name"], "in": [w, h, round(fps, 3), len(frames)], "ops": j["ops"], "gpu": gpu}
        if "interpolate" in j["ops"] and abs(fps - j["target_fps"]) > 0.01:
            frames = g.interpolate(frames, w, h, fps, j["target_fps"]); fps = j["target_fps"]
        if "upscale" in j["ops"]:
            frames, w, h = g.upscale(frames, w, h, j["scale"])
        write_all(f"{OUT}/{j['name']}", j["path"], frames, w, h, fps, man["encode"])
        rec.update(out=[w, h, fps, len(frames)], seconds=round(time.time() - t0, 1))
        results[j["name"]] = rec
        print(f"[w{gpu}] {rec}", flush=True)
