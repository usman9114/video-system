# Kaggle Free GPU Lane: Setup and Reuse

Free GPU (about 30 h/week, 16 GB T4) for jobs this CPU-only cloud server can't run well:
AI lip-sync tests (MuseTalk), heavy Whisper models, face restoration checks.
Everything else (cutting, captions, Remotion renders) stays on the cloud server.

Cost: $0. Never add a payment method to Kaggle. Nothing in this lane needs one.

---

## Part A: One-time setup by you (about 5 minutes)

1. **Create an account** at https://www.kaggle.com (Google sign-in is fine).
2. **Verify your phone**: Kaggle → profile icon → **Settings** → **Phone verification**.
   This is required for GPU and internet access inside notebooks. VoIP numbers often fail.
3. **Create an API token**: Settings → **API** → **Create New Token** (the "API Tokens" section, not the legacy `kaggle.json`).
   Copy the token. **Do not paste it into chat.**
4. Tell Claude: *"Kaggle account ready."* Claude opens a secure form, and you paste the token there.
   It's stored as a network secret on the cloud environment and added to requests to
   `api.kaggle.com` by the proxy. Claude never sees the value.

## Part B: What's set up (done 2026-11-26, tested end to end)

| Item | Value |
|---|---|
| Cloud environment | `upwork-video-system` (personal) |
| Allowed hosts | `api.kaggle.com`, `www.kaggle.com`, `storage.googleapis.com` (uploads), `www.kaggleusercontent.com` (output downloads) |
| Network secret | "Kaggle API token" → `Authorization: Bearer` header on `api.kaggle.com` |
| CLI | `kaggle==2.2.5` in `.venv` (auto-installed by `bin/kgpu`), placeholder `KAGGLE_API_TOKEN=proxy-injected` |
| Wrapper | `bin/kgpu` → `lane/kgpu.py` |

Why there's a wrapper: the stock Kaggle CLI checks the token by sending it in the request **body**
(`IntrospectToken`). The proxy only injects headers, so that check fails. `kgpu` skips the check and detects your
username from an authenticated "my notebooks" call. Every other call uses the header, which works.

## Part C: kgpu = `docker run` on a Kaggle GPU

A **job** is a folder with `run.py` (plus an optional `requirements.txt` and helper files).
It runs inside Kaggle's GPU Docker image (Tesla T4 16 GB, CUDA, PyTorch 2.11 and FFmpeg preinstalled).

```bash
bin/kgpu whoami                                   # check auth
bin/kgpu run jobs/hello-gpu --input some/file.mp4 # upload, run on GPU, wait, download
bin/kgpu run jobs/x --no-wait                     # fire and forget
bin/kgpu status x  |  bin/kgpu wait x  |  bin/kgpu output x
bin/kgpu clean x                                  # delete the notebook + input dataset on Kaggle
```

Inside `run.py`: read inputs from `$KGPU_INPUT` and write results to `$KGPU_OUTPUT`.
Results land in `kaggle/outputs/kgpu-<job>/out/` (gitignored), with `_kgpu_result.json` (exit code, seconds)
and the full log `kgpu-<job>.log`.

What happens under the hood:
1. The job code and inputs are zipped into one **private** dataset `<user>/kgpu-<job>-data` (versioned on re-runs).
2. A private script notebook `<user>/kgpu-<job>` is pushed with GPU and internet on and that dataset attached.
3. A generated entry script pip-installs `requirements.txt`, runs `run.py` and records the exit code.
4. Status is polled every 30 s, then outputs are downloaded.
5. Each run is logged to `reports/gpu-usage.jsonl`.

Rules: private only, one job at a time, stop on quota errors, no secrets in jobs, and run `kgpu clean`
after jobs that uploaded face footage if you don't want it stored on Kaggle.
Quota is about 30 GPU h/week. The smoke test (`jobs/hello-gpu`) used about 15 s.

---

## Part D: Reusable prompt for future sessions

Paste this into a new Claude Code cloud session that uses the `upwork-video-system` environment:

```
Reconnect the Kaggle free GPU lane for my video project.
1. Read docs/kaggle-gpu-setup.md.
2. Check this session's environment allows api.kaggle.com, www.kaggle.com,
   storage.googleapis.com and www.kaggleusercontent.com, and that a network secret exists for api.kaggle.com.
   If anything is missing, propose the change (don't work around it).
3. Run `bin/kgpu whoami` (auto-installs the CLI into .venv; the proxy injects the real token).
4. Smoke test: `bin/kgpu run jobs/hello-gpu` and check it reports Tesla T4 + cuda true. If it returns 401/403,
   ask me for a new token via the secure credential form, never in chat.
5. Report: connected yes/no, my GPU quota if visible, and any blocker.
Rules: private datasets/notebooks only, no payment methods, $0 spend, stop on quota errors.
```

If the token ever leaks or you want to revoke access: Kaggle → Settings → API → expire the token.
The lane stops working immediately and no other account access is affected.
