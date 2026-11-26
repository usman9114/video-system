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

## Part B: What Claude sets up (already automated)

| Item | Value |
|---|---|
| Cloud environment | `upwork-video-system` (personal) |
| Allowed hosts | `api.kaggle.com`, `www.kaggle.com`, `storage.googleapis.com` (Kaggle upload/download links) |
| Network secret | Bearer token for `api.kaggle.com` |
| CLI | `pip install kaggle==2.2.5` in the project venv, run with a placeholder `KAGGLE_API_TOKEN` (the proxy swaps in the real one) |

## Part C: How a GPU job runs

1. Inputs (video clips, audio) are uploaded as a **private** Kaggle Dataset:
   `kaggle datasets create -p kaggle/inputs/<job> --dir-mode zip` (private by default).
2. A notebook or script plus `kernel-metadata.json` with
   `"enable_gpu": true, "enable_internet": true, "is_private": true` is pushed:
   `kaggle kernels push -p kaggle/jobs/<job>`
3. Status is checked: `kaggle kernels status <user>/<job>` (poll every few minutes, not every second).
4. Outputs are downloaded: `kaggle kernels output <user>/<job> -p kaggle/outputs/<job>`
5. The private dataset is deleted afterwards if it holds face footage you don't want stored.

Rules: always private, one job at a time, stop on quota errors, no secrets inside notebooks,
log GPU minutes used in `reports/gpu-usage.md`.

---

## Part D: Reusable prompt for future sessions

Paste this into a new Claude Code cloud session that uses the `upwork-video-system` environment:

```
Reconnect the Kaggle free GPU lane for my video project.
1. Read docs/kaggle-gpu-setup.md.
2. Check this session's environment allows api.kaggle.com, www.kaggle.com and
   storage.googleapis.com, and that a network secret exists for api.kaggle.com.
   If anything is missing, propose the change (don't work around it).
3. Install the Kaggle CLI (pip install kaggle==2.2.5) in a project venv and run it with
   KAGGLE_API_TOKEN=placeholder (the proxy injects the real token).
4. Smoke test: `kaggle kernels list --mine --page-size 1`. If it returns 401/403,
   ask me for a new token via the secure credential form, never in chat.
5. Report: connected yes/no, my GPU quota if visible, and any blocker.
Rules: private datasets/notebooks only, no payment methods, $0 spend, stop on quota errors.
```

If the token ever leaks or you want to revoke access: Kaggle → Settings → API → expire the token.
The lane stops working immediately and no other account access is affected.
