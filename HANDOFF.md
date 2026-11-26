# HANDOFF: Read This First

Living status file. Every session updates it before ending, so any Claude account can continue.
Also read: `docs/LESSONS.md` (what went wrong and how it's fixed in code), `README.md` (how to run).

_Last updated: 2026-11-26 ~22:50 UTC_

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
- [ ] Re-run on the **60 MB original** once it's in Drive `source/` (the owner said they'll upload it).
      Note: a Drive download of 60 MB through the connector is untested.
- [ ] **Video #1 = n8n automation gig** (owner request 2026-11-26: "make something for n8n, like I'm a pro and
      would help you with your problems"). Concept and script in progress: `scripts/videos/01_n8n.md` (next step).
- [ ] Phases 4-10 for the remaining 9 gigs. **Still need the owner's Upwork gig titles and descriptions.**

## Waiting on owner
1. Feedback on DRAFT1 (clean master)
2. 60 MB original → Drive `upwork-video-system/source/`
3. Upwork gig titles and descriptions (at least the n8n gig text)
4. OK to `npm install` Remotion v4 (for animated templates), and yes or no on the ChatGPT lane
5. Confirm the transcript line "We test **what works**" (the old subtitle said "with words")

## Next step for Claude
Write the n8n video concept and script (reusing only true, generic lines from the source + on-screen text and B-roll),
get the owner's OK, then build the promo template and render the preview.
