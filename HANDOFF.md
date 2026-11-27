# HANDOFF: Read This First

Living status file. Every session updates it before ending, so any Claude account can continue.
Also read: `docs/LESSONS.md` (58+ lessons, each fixed in code/config), `templates/production.json` (single source of truth for
all settings + the owner's hard rules), `docs/optimization.md` (GPU cost playbook), `docs/ideas/trip-memories.md`.

_Last updated: 2026-11-27 ~16:00 UTC (session ran out of context; handoff written on owner request)_

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

## Status
### Upwork video #1 (n8n)
- [x] Script from the owner's gig text, ElevenLabs voice (`assets/voice/01_n8n/`), 6 TBDub-teacher lip-sync clips (≈$1.14).
- [x] **v6 rendered**: `exports/01_n8n_automation_v6.mp4` (46 s, -14 LUFS, rule-compliant). Build:
      `python3 scripts/make_faces.py scripts/videos/01_n8n_v6.json` (lip-sync, already done) → `python3 scripts/promo.py scripts/videos/01_n8n_v6.json --final`.
- [ ] **v6 NOT yet approved by owner.** Sent to the owner in chat at handoff time with the caveat below.
- [ ] **SyncNet gate** (`jobs/syncnet-eval`): fixed `scenedetect>=0.6.4` (repo needs `open_video`) and recursive input glob
      (inputs land in a subfolder). Re-run: put REAL_original_footage.mp4 (from the first run's build dir or cut from plate),
      `SYNC3_hookcta.mp4` (= `kaggle/work/lipsync/hookcta_sync3.mp4`) and the 6 v6 clips into one dir →
      `bin/kgpu run jobs/syncnet-eval --input <dir> --timeout-min 25`. Then compare LSE-C vs real & sync-3 (gate ≥ 0.9× sync-3).
### Trip Memories: Greece (current work)
- [x] Stage 1 ChatGPT analysis (5 in parallel): `trips/greece/analysis.json`.
- [x] Stage 2 storyteller agent: `trips/greece/storyline.json` + **`trips/greece/storyline.md`** (12 scenes, 54.5 s,
      4 hero scenes = IMG_9270 Anafiotika, IMG_9282 Meteora, IMG_9444 Fiat, IMG_9268 graffiti lane; all others camera-move only;
      dropped 69a32a81 as near-duplicate).
- [ ] **Owner must approve the storyline** (and answer: are the Acropolis photos from this trip? blur the Fiat's plate?).
- [ ] Then: `python3 -m lane.modal_lipsync fastwan --items <json>` for the 4 hero photos (items: image, prompt, out, seconds 3.5,
      seed, orient portrait for 9:16, focus_x/y). 2 seeds each. FastWan weights are DOWNLOADED on the Modal volume
      (`/weights/fastwan/ti2v-5b`, 23 GB, 25 files, confirmed 2026-11-27). Measure $ + quality vs TI2V-5B (gate).
- [ ] Realism gate on every hero clip (painted faces in IMG_9268 and plate text in IMG_9444 must not shimmer) → else camera move.
- [ ] RIFE 24→30/60 fps (not built yet; Practical-RIFE MIT on Modal). Camera-move-only scenes render natively at 30 fps (no interpolation needed).
- [ ] Trip renderer: new template in `scripts/promo.py` (or `scripts/trip/render.py`): **apply `ImageOps.exif_transpose`**
      (5 photos are stored sideways, one mirrored, one flipped); 9:16 1080×1920; captions ≤7 words; dissolves at act breaks;
      music bed; optional narration in owner's ElevenLabs voice (credits!).
### Modal / optimisation
- [x] Wan TI2V-5B and I2V-A14B work on Modal (owner prefers TI2V-5B). FastWan batch function deployed, with fixes:
      cover-crop (no 4:3→16:9 squash) and EXIF transpose (the transpose fix is in the last commit → auto-deploy).
- [ ] Gate-test SageAttention2 / MagCache / FP8 / torch.compile+snapshots (docs/optimization.md). Batch TBDub calls.

## Next step for Claude (in order)
1. Check the last Modal deploy succeeded (`gh run list --repo usman9114/video-system --limit 1`) and `python3 -m lane.modal_lipsync health`.
2. Ask the owner for v6 feedback and storyline approval (show `trips/greece/storyline.md`).
3. Re-run SyncNet (above) and report scores.
4. After approval: FastWan hero clips → realism gate → RIFE → trip render → send to owner.
5. Commit + push after each step; update this file + docs/LESSONS.md before the session ends.
