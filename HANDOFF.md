# HANDOFF: Read This First

Living status file. Every session updates it before ending, so any Claude account can continue.
Also read: `docs/LESSONS.md` (what went wrong and how it's fixed in code), `README.md` (how to run).

_Last updated: 2026-11-26 ~23:10 UTC_

## Project
Turn one generic talking-head video of the owner into 10 targeted Upwork promo videos.
Full brief: `docs/BRIEF.md`. Hard rules: $0 default, max about €10 total with owner approval, no fabricated
credentials, client results or testimonials, no synthetic-looking face, ask before installs or spending.

## Where things live
| What | Where |
|---|---|
| Code, configs, docs, reports | GitHub `usman9114/video-system` (private), branch `main` |
| Video files | Google Drive folder `upwork-video-system/` (source, broll, assets, previews, exports). Connector uploads max about 3 MB per call, so send drafts with the app's file send |
| Kaggle GPU lane | `bin/kgpu` + `docs/kaggle-gpu-setup.md`. Kaggle user `usmanqureshi94`, quota 6 GPU h/week (resets weekly; next 2026-11-28) |
| Cloud environment | `upwork-video-system` (personal; allows api.kaggle.com, www.kaggle.com, storage.googleapis.com, www.kaggleusercontent.com; Kaggle token saved as a network secret). It's per Claude account, so recreate it on a new account |

## Decisions made
1. **Stack:** FFmpeg + Python for cutting, compositing, captions and encoding. Kaggle 2×T4 for AI steps (Whisper large-v3, LaMa).
   Remotion v4 is planned for animated promo templates (**npm install not yet approved by the owner**).
2. **Cloud only.** Work moves between accounts through git + Drive.
3. Meta Muse: not usable. Lip-sync: not the default (MuseTalk test only, later).
4. **Owner confirmed** they may reuse the WFP footage. They asked to remove the end card and logo and replace the subtitles in place (done).
5. Thumbnails: real frame + generated background + text added locally. ChatGPT lane (Codex CLI, from repo
   `usman9114/drop-shipping-` branch `claude/eager-hawking-jmvcqj`) **install not approved yet**.

## Status
- [x] Phase 1: research (`reports/01-tool-research.md`)
- [x] Phase 2: env, Kaggle lane, git, Drive
- [x] Phase 3 (on compressed copy): `reports/02-source-footage.md`. Transcript `assets/transcripts/original_small.words.json`
- [x] **Clean master v1** from the compressed copy: `scripts/make_clean_master.sh` → `exports/clean_master_from_small.mp4`
      (QA: -14.0 LUFS, -1.5 dBTP, no black or frozen frames). Sent to the owner as `previews/DRAFT1_clean_master_review.mp4`.
- [ ] **60 MB original** (`sample-video.mp4`) is in Drive but the connector caps downloads at 10 MB. Asked the owner to upload it
      as a private Kaggle dataset `source-video`; then `bin/kgpu`'s Kaggle API can fetch it. Then re-run
      `scripts/make_clean_master.sh` + `promo.py --source source/<orig>.mp4` (all resolution-independent).
- [x] **Video #1 = n8n automation** rendered: `exports/01_n8n_automation.mp4` (4:5 1080×1350, 34.8 s, -14.4 LUFS).
      Build: `python3 scripts/promo.py scripts/videos/01_n8n.json --final`. Spec = `scripts/videos/01_n8n.json`,
      design = `templates/promo_4x5.json`. Sent to the owner for review. **Do not batch the other 9 until the owner approves #1.**
      Unconfirmed claims on screen: title "AI Solutions Consultant", feature cards (self-hosted/cloud, AI agents + API, docs & handover).
- [~] **Video #1 v2**: new first-person script from the owner's gig text (`scripts/videos/01_n8n_v2_script.md`). Needs new audio: owner recording (recommended) or AI test (Chatterbox MIT voice + MuseTalk lip-sync on Kaggle). Owner chose 'Test AI first'. Qwen3-TTS clone verdict (owner 2026-11-27): **"very robotic, not like mine" → rejected**. Chatterbox (fast rerun) verdict: **"even worse" → rejected**. Next: **ElevenLabs instant clone** (owner to sign up for Starter $1, give API key via secure form; host api.elevenlabs.io; code ready in `lane/elevenlabs.py`, sample `assets/voice/owner_voice_sample_full.wav` 48 s). Guaranteed path = owner records voice memo/video.
- [ ] Phases 4-10 for the remaining 9 gigs. **Still need the owner's Upwork gig titles and descriptions.**

## Waiting on owner
1. **Feedback on video #1** (`exports/01_n8n_automation.mp4`): look, pacing, claims on screen
2. 60 MB original → upload on kaggle.com as a **private dataset named `source-video`** (Drive connector can't fetch >10 MB)
3. Upwork gig titles and descriptions for gigs 2-10 (n8n gig text received, saved in scripts/videos/01_n8n_v2_script.md)
4. Yes or no on the ChatGPT lane (Remotion turned out not to be needed: promo.py uses Pillow + ffmpeg)
5. Confirm the transcript line "We test **what works**" (the old subtitle said "with words")

## Next step for Claude
Apply the owner's feedback on video #1 (edit the spec/template JSON, re-render). Then get the gig list and write specs 02-10
(`scripts/videos/NN_*.json`), making each meaningfully different (hook, segment order, list items, colour accent, maybe 9:16).
Add a 9:16 template (`templates/promo_9x16.json`) when needed.
