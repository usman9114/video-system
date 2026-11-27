# Project board

_Generated from `tracker/board.json` by `scripts/tracker.py`. Updated 2026-11-27 19:28 UTC._

Project board. Source of truth for what is done / in progress / open. Every agent: read at session start, update with scripts/tracker.py as you work, commit it with your work. HANDOFF.md keeps the how-to detail; this keeps the state.

## Blocked (4)

- **T01** Fix Modal lip-sync API key mismatch  _(infra · needs owner)_
  - 2026-11-27: /health 401. Server key 51 chars fp c2c204; session LIPSYNC_API_KEY 43 chars fp e6ea20. Owner: set GitHub secret LIPSYNC_API_KEY to the session value + re-run 'Deploy Modal lip-sync API', or give the session the 51-char value.
- **T02** Lip-sync A/B on line 03_who: LatentSync 1.6 / X-Dub / TBDub full-res  _(n8n · after T01)_
  - python3 -m lane.modal_lipsync ab-download --model latentsync16|xdub, then ab --model ... --video kaggle/work/lipsync/01_n8n_automation_v6/03_who_src.mp4 --audio assets/voice/01_n8n/03_who.mp3
  - TBDub full-res needs owner's sample-video.mp4 (60 MB original).
- **T06** Greece film v2: render with finishing tools (upbeat music, beat cuts, VO breathing, FFmpeg finish)  _(greece · needs owner)_
  - Tools in scripts/trip/{music_upbeat,vo_breathe,finish}.py + render.py, never run on real photos.
  - 2026-11-27: blocked, no Drive connector or linked computer in session; owner must upload the 13 photos to trips/greece/photos/ (names = Drive names).
- **T12** Re-render Greece v1 (master lost) once photos are uploaded  _(greece · needs owner)_
  - 2026-11-27: Needs the owner to upload the 13 Greece photos (Drive upwork-video-system/trips/) into this chat or a linked folder.

## To do (7)

- **T03** SyncNet-gate the A/B clips, side-by-side, owner picks winner  _(n8n · after T02)_
  - bin/kgpu run jobs/syncnet-eval --input <dir> --timeout-min 25. Gate: >= 0.9 x sync-3 (7.65).
- **T04** Render n8n video v7 with the winning lip-sync  _(n8n · after T03)_
  - Set config lipsync -> make_faces.py scripts/videos/01_n8n_v6.json -> promo.py --final
- **T05** Get gig texts for Upwork videos 2-10  _(upwork · needs owner)_
- **T08** Back up every export to the Kaggle media-backup dataset right after rendering  _(infra)_
  - trip_greece.mp4 was lost this way (LESSONS #64).
- **T09** Ask owner: TI2V-5B gate test on 4 Greece hero scenes (~$7.60 Modal credits)?  _(greece · needs owner)_
  - Default is real photo + camera move (FastWan rejected, LESSONS #65).
- **T10** Gate-test SageAttention2 / MagCache / FP8 / torch.compile; batch TBDub calls  _(infra)_
  - docs/optimization.md
- **T11** Merge greece-v2 branch into main  _(infra · needs owner)_
  - Holds X-Dub image fixes, Wan2.2 I2V batch endpoint, Greece v2 tools, 401 key fingerprint.

## In progress (0)


## Waiting on owner review (1)

- **T07** Owner feedback on Greece film v1  _(greece · needs owner)_
  - v1 sent in chat 2026-11-27 17:15 UTC (39 MB share copy). Master was NOT backed up to Kaggle; it died with that container.

## Done (7)

- **D01** n8n v6 rendered (46 s, -14 LUFS); owner rejected lip-sync  _(n8n)_
  - exports/01_n8n_automation_v6.mp4 in Kaggle backup
- **D02** SyncNet baselines: real 8.23, sync-3 7.65, TBDub v6 4.2-6.1 (fails)  _(n8n)_
- **D03** Greece analysis + storyline (12 scenes, 54.5 s), approved by owner  _(greece)_
  - trips/greece/storyline.md
- **D04** Greece film v1 rendered and sent  _(greece)_
- **D05** FastWan hero clips tested, rejected by realism gate  _(greece)_
  - LESSONS #65
- **D06** Modal deploy fixed (Python 3.11 images, X-Dub opencv/numpy/mmcv)  _(infra)_
  - PRs #3, #4 + greece-v2 commits; deploy runs 19-21 green
- **D07** Personal cloud env 'video-system' created with all project hosts  _(infra)_
  - 2026-11-27. Start new sessions in this env.
