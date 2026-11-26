# HANDOFF: Read This First

Living status file. Every session updates it before ending, so any Claude account can continue.

_Last updated: 2026-11-26, end of Phase 1 / start of Phase 2_

## Project
Turn one generic talking-head video of the owner into 10 targeted Upwork promo videos.
The full brief is in `docs/BRIEF.md`. Hard rules: $0 default, max about €10 total with owner approval,
no fabricated credentials, client results or testimonials, no synthetic-looking face, ask before installs or spending.

## Where things live
| What | Where |
|---|---|
| Code, templates, configs, scripts, reports | GitHub `usman9114/upwork-video-system` (private) |
| Video files (source, B-roll, previews, exports) | Google Drive folder `upwork-video-system/` (subfolders: source, broll, assets, previews, exports) |
| Kaggle GPU lane | `docs/kaggle-gpu-setup.md` (token stored as a cloud-environment network secret, never in git) |
| Cloud environment | `upwork-video-system` (personal; allows api.kaggle.com, www.kaggle.com, storage.googleapis.com). It's per Claude account, so recreate it on a new account |

## Decisions made
1. **Stack:** Remotion v4 (templates, captions, CTA) + FFmpeg (cuts, audio, QA) + faster-whisper/WhisperX (local captions). Fallback: pure FFmpeg. See `reports/01-tool-research.md`.
2. **Run in the cloud** (not on the owner's computer). Usage limits are per account, so work moves between accounts through git + Drive.
3. **Meta Muse:** not usable (Muse Video is a closed beta and it generates new footage; Muse Spark is a text model).
4. **Lip-sync:** not the default. Default = real footage + the owner's own voiceover. MuseTalk on Kaggle is to be tested in Phase 6 only.
5. **Free GPU:** Kaggle chosen. Colab/Lightning/Modal rejected for now. Budget of about €10 available if a paid option clearly helps (e.g. fal.ai LatentSync about $0.20 per clip up to 40 s; RunPod 4090 about $0.34/h). Ask first.
6. **Thumbnails:** a real frame of the owner + a generated background + text added locally. Optional ChatGPT lane (Codex CLI on the owner's ChatGPT Go plan, from repo `usman9114/drop-shipping-` branch `claude/eager-hawking-jmvcqj`, files `scout/chatgpt.py`, `scripts/install_codex.sh`, `.claude/skills/chatgpt/SKILL.md`). **Install NOT yet approved.** Never send face frames to OpenAI without asking.

## Status
- [x] Phase 1: research + recommendation
- [~] Phase 2: environment created, Kaggle reachable, Drive + git set up. Tool smoke test not yet run.
- [ ] Kaggle: owner to create account, verify phone, create API token, then Claude requests it via the secure form
- [ ] Phase 3: waiting for the source video (owner uploads to Drive `upwork-video-system/source/`)
- [ ] Phase 4: waiting for the owner's Upwork gig titles and descriptions
- [ ] Phases 5 to 10

## Waiting on owner
1. Source video uploaded to Drive `upwork-video-system/source/`
2. Upwork gig titles and descriptions
3. Yes or no on installing the ChatGPT lane (Codex CLI)
4. Kaggle token (when ready)

## Next step for Claude
Once the video is in Drive: download it to `source/` (never modify the original), install the pinned tools
(ask first), run the smoke test, write `reports/02-source-footage.md`.
