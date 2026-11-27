# HANDOFF: Read This First

Living status file. Every session updates it before ending, so any Claude account can continue.
Also read: `docs/LESSONS.md` (58+ lessons, each fixed in code/config), `templates/production.json` (single source of truth for
all settings + the owner's hard rules), `docs/optimization.md` (GPU cost playbook), `docs/ideas/trip-memories.md`.

_Last updated: 2026-11-27 ~16:45 UTC. Status below corrected to match the last 3 commits (SyncNet done, FastWan rejected)._

> **Session check first.** A session WITHOUT env `upwork-video-system` (and without the repo linked through the Claude GitHub
> App) can't do anything that matters here: kaggle/modal/elevenlabs/chatgpt hosts → 000, `git push` → 403 "not in this
> session's authorized repository set". Check with: `curl -s -o /dev/null -w '%{http_code}' https://www.kaggle.com/` and
> `git push --dry-run`. If either fails, stop and ask the owner to start a new session in that environment / link GitHub.

## Two projects in this repo
1. **Upwork promo videos** (original brief `docs/BRIEF.md`): turn the owner's one talking-head video into 10 targeted
   Upwork promos. Video #1 = n8n automation gig. Videos 2-10 need the owner's other gig texts.
2. **Trip Memories** (new idea, `docs/ideas/trip-memories.md`): ~10 trip photos → 45-75 s documentary-style film, ≥30 fps,
   cost ≈ $0.30-0.80/trip. First real test = the owner's Greece trip (13 photos).

## Owner's HARD rules (also in templates/production.json → rules / realism_gate)
- $0 by default (Modal free $30/month credits accepted; ElevenLabs Starter plan already paid). Never buy/subscribe.
- **Realism first**: "only do what is possible and realistic… it has to be real like". Nothing may look AI. Faces are never
  generated/re-animated beyond lip-sync; photos of people get camera moves only.
- **No cuts away from the face while the owner is talking.** B-roll only between lines (≤ 2.2 s). Zoom on talking face ≤ 1.05. No reversed footage.
- Lip-sync must be good: TBDub **teacher** on Modal (owner's pick, "option C"). Gate: SyncNet.
- **Always use config** (`templates/production.json`); change settings there, never ad hoc.
- Visuals: find REAL references online → give to ChatGPT to redraw/upscale; never use web images as-is; no pure-AI UIs.
- Resource-optimised always (distilled/quantized/cached/batched) but never at the cost of quality (gate in docs/optimization.md).
- Use pip (not uv) on Kaggle — torch downloads were the slowness. Claude is the director.
- No fabricated credentials/clients/results. Ask before installs or anything that costs money.

## Where things live
| What | Where |
|---|---|
| Code/configs/docs | GitHub `usman9114/video-system`, branch `main` (push to main auto-deploys Modal, see below) |
| **Media backup (gitignored files)** | Private Kaggle dataset **`usmanqureshi94/video-system-media-backup`** → `media-backup-2026-11-27.tar.gz` (109 MB): `exports/01_n8n_automation_v6.mp4`, `kaggle/work/lipsync/01_n8n_automation_v6/*` (the 6 paid TBDub clips), `kaggle/work/original_small/plate.mp4`, `broll/{generated,references,wan}`, `assets/voice/*`. Restore: download via the Kaggle API (`.venv/bin/python`, `lane.kgpu._api()` returns a tuple; pick the element with `dataset_download_files`) and `tar xzf` in the repo root |
| Drive | `upwork-video-system/` (source video, previews). Trip photos: `upwork-video-system/trips/` (13 Greece photos, flat) |
| Trip photos locally | `trips/greece/photos/` (gitignored, re-download from Drive; names = Drive names, e.g. IMG_9282.jpeg; the 3 hash-named files are 89499c09.jpeg, 69a32a81.jpeg, a0a41173.jpeg) |
| Kaggle GPU (2×T4) | `bin/kgpu run jobs/<job> --input <file-or-dir>` (ALWAYS via `bin/kgpu`, never `python -m lane.kgpu`: the repo's `kaggle/` dir shadows the package). User `usmanqureshi94`, 6 GPU-h/week |
| Modal (L40S/H100) | HTTPS API `https://nubuqqrr--video-system-lipsync-api.us-east.modal.run` (header `x-api-key`, injected by the proxy as a network secret). Client: `python3 -m lane.modal_lipsync health|lipsync|wan|fastwan-download|fastwan`. Deployed by `.github/workflows/modal-deploy.yml` on push to main (repo secrets MODAL_TOKEN_ID/SECRET, LIPSYNC_API_KEY). Proxy can't do Modal's gRPC, so never `modal run` from here. Usage log: `reports/modal-usage.jsonl` |
| ElevenLabs | `lane/elevenlabs.py` + `.claude/skills/elevenlabs/SKILL.md`. Voice id `jwItKKDHu8LXzA2tIhdT`, ~11.4k credits left, 2k reserve guard |
| ChatGPT lane | Codex CLI in `tools/codex`, logged in to owner's ChatGPT: `python3 -m lane.chatgpt image|ask|research` (re-login may be needed on a new container) |
| Cloud env | `upwork-video-system` (hosts: api.kaggle.com, www.kaggle.com, storage.googleapis.com, www.kaggleusercontent.com, auth.openai.com, chatgpt.com + secret hosts: Kaggle, ElevenLabs, Modal API). Per Claude account → recreate on a new account |

## Secrets / keys (NEVER in git; nothing to copy from the repo)
| Key | Where it lives | On a new Claude account |
|---|---|---|
| Kaggle API token | cloud env network secret, host `api.kaggle.com`, header Authorization | re-enter (secure form / env Settings) |
| ElevenLabs API key | network secret, host `api.elevenlabs.io`, header `xi-api-key` | re-enter |
| Lip-sync API key (`LIPSYNC_API_KEY`) | network secret, host `nubuqqrr--video-system-lipsync-api.us-east.modal.run`, header `x-api-key`; ALSO GitHub repo secret | re-enter the same value. GitHub secrets can't be read back: if lost, make a new random value, set it in GitHub repo secret `LIPSYNC_API_KEY` + re-run the deploy workflow (it syncs into Modal), then use it here |
| sync.so key | network secret, host `api.sync.so` | optional (free tier = watermark, not used) |
| Modal token id/secret | GitHub repo secrets (used by the deploy workflow) | nothing to do, stays with the repo. Local `.env.modal` is not needed |
| ChatGPT (Codex) login | `tools/codex/auth.json` (gitignored, per container) | re-login in the new container (device-code flow; hosts auth.openai.com + chatgpt.com) |
Environment allowed hosts to recreate: api.kaggle.com, www.kaggle.com, storage.googleapis.com, www.kaggleusercontent.com, auth.openai.com, chatgpt.com (package managers on).

## Status
### Upwork video #1 (n8n)
- [x] Script from the owner's gig text, ElevenLabs voice (`assets/voice/01_n8n/`), 6 TBDub-teacher lip-sync clips (≈$1.14).
- [x] **v6 rendered**: `exports/01_n8n_automation_v6.mp4` (46 s, -14 LUFS, rule-compliant). Build:
      `python3 scripts/make_faces.py scripts/videos/01_n8n_v6.json` (lip-sync, already done) → `python3 scripts/promo.py scripts/videos/01_n8n_v6.json --final`.
- [ ] **Owner 2026-11-27: v6 lip-sync "isn't good" (TBDub teacher via our Modal API).** Checked: timing is NOT the cause
      (clip audio vs voice mp3 cross-correlation = 0 ms on all 6 lines; renderer resamples 25→30 fps by time). Likely cause =
      model quality on a LOW-RES source (plate = compressed `original_small`, 864 px crop; the 60 MB original was never used).
      Next: SyncNet scores (job re-launched), then A/B on ONE line: (a) TBDub teacher on the full-res original (owner must upload
      `sample-video.mp4` as a private Kaggle dataset `source-video`), (b) LatentSync 1.6 on Modal L40S at full settings (the T4 test
      was crippled to num_frames 6), (c) X-Dub. Owner picks by eye; config `lipsync` updated to the winner.
- [ ] **v6 NOT yet approved by owner.** Sent to the owner in chat at handoff time with the caveat below.
- [x] **SyncNet gate DONE** (commit aae1ff8; scores in `templates/production.json` → lipsync.quality_gate): real 8.23,
      sync-3 7.65, TBDub teacher v6 4.2-6.1 → **fails** the 0.9×sync-3 gate (only lines 02-05 have scores; short clips need padding to ≥100 frames).
      Re-run only for new lip-sync candidates: same dir layout → `bin/kgpu run jobs/syncnet-eval --input <dir> --timeout-min 25`.
### Trip Memories: Greece (current work)
- [x] Stage 1 ChatGPT analysis (5 in parallel): `trips/greece/analysis.json`.
- [x] Stage 2 storyteller agent: `trips/greece/storyline.json` + **`trips/greece/storyline.md`** (12 scenes, 54.5 s,
      4 hero scenes = IMG_9270 Anafiotika, IMG_9282 Meteora, IMG_9444 Fiat, IMG_9268 graffiti lane; all others camera-move only;
      dropped 69a32a81 as near-duplicate).
- [ ] **Owner must approve the storyline** (and answer: are the Acropolis photos from this trip? blur the Fiat's plate?).
- [x] **FastWan hero clips: ran + REJECTED** by the realism gate (commit 7b6be72, LESSONS #65: repaints the scene, invents a
      readable number plate; $0.19 for 8 clips). Config default for trips is now **real photo + camera move**. So the
      storyline's 4 "hero (full AI animation)" scenes render as camera moves unless the owner OKs a full TI2V-5B gate test
      (≈ $0.95/clip × 4 photos × 2 seeds ≈ $7.60 of Modal free credits; owner earlier called ~$10 "a lot") → ASK first.
- [ ] RIFE: **not needed** for the camera-move-only cut (renders natively at 30 fps). Build only if a generative clip passes.
- [x] Trip renderer exists: `scripts/trip/render.py trips/greece [--preview]` (EXIF transpose, plate blur from
      `trips/greece/redact.json`, 9:16 1080×1920 30 fps, title, captions, dissolves, ducked music, grade+grain, narration).
      Smoke-tested 2026-11-27 in `--preview` mode on stand-in photos with EXIF orientation 6 → upright, captions/title OK.
      Full render (audio + mp4) not yet run on the real photos. Narration audio: ElevenLabs cache entries exist
      (`kaggle/cache/elevenlabs/*.json`); the mp3s are gitignored → check they are in the media backup.
### Modal / optimisation
- [x] Wan TI2V-5B and I2V-A14B work on Modal (owner prefers TI2V-5B). FastWan batch function deployed, with fixes:
      cover-crop (no 4:3→16:9 squash) and EXIF transpose (the transpose fix is in the last commit → auto-deploy).
- [ ] Gate-test SageAttention2 / MagCache / FP8 / torch.compile+snapshots (docs/optimization.md). Batch TBDub calls.

## Next step for Claude (in order)
0. Session check (top of file). Restore the media backup; copy the 13 Greece photos from Drive → `trips/greece/photos/`.
1. Check the last Modal deploy succeeded (`gh run list --repo usman9114/video-system --limit 1`) and `python3 -m lane.modal_lipsync health`.
   Note: the owner has a NEW `LIPSYNC_API_KEY` value that is not active yet (GitHub secret + deploy workflow + env network
   secret must all get the same value; the owner does the GitHub/env parts himself).
2. Get the owner's storyline approval (+ Acropolis-photos question, plate blur yes/no, hero scenes = camera moves OK?).
3. Trip render (`scripts/trip/render.py trips/greece`, preview first) → owner's eye → send the mp4.
4. n8n v6: the owner already rejected the lip-sync; run the lip-sync A/B on ONE line (full-res TBDub / LatentSync 1.6 L40S /
   X-Dub) → SyncNet gate → owner picks → config `lipsync` → re-render v7.
5. Commit + push after each step; update this file + docs/LESSONS.md before the session ends.
