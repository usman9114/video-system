# Project board

_Generated from `tracker/board.json` by `scripts/tracker.py`. Updated 2026-11-27 20:03 UTC._

Project board. Source of truth for what is done / in progress / open. Every agent: read at session start, update with scripts/tracker.py as you work, commit it with your work. HANDOFF.md keeps the how-to detail; this keeps the state.

## Blocked (3)

- **T06** Greece film v2: render with finishing tools (upbeat music, beat cuts, VO breathing, FFmpeg finish)  _(greece · needs owner)_
  - Tools in scripts/trip/{music_upbeat,vo_breathe,finish}.py + render.py, never run on real photos.
  - 2026-11-27: blocked, no Drive connector or linked computer in session; owner must upload the 13 photos to trips/greece/photos/ (names = Drive names).
  - 2026-11-27: 2026-11-27: prepared without photos: 7 narration mp3s extracted to trips/greece/work/vo/ (gitignored, from paid ElevenLabs cache), upbeat music generator tested OK. ONLY missing input: the 13 photos in trips/greece/photos/. Then: render.py trips/greece (preview first) -> scripts/trip/finish.py -> final_cut.py --kind trip -> back up to Kaggle (T08).
  - 2026-11-27: Drive photos: this session has NO Google Drive connector (ListConnectors empty; registry shows Google Drive not installed). Owner to connect Google Drive in claude.ai connectors and start a new session in env video-system, or upload photos.
- **T12** Re-render Greece v1 (master lost) once photos are uploaded  _(greece · needs owner)_
  - 2026-11-27: Needs the owner to upload the 13 Greece photos (Drive upwork-video-system/trips/) into this chat or a linked folder.
- **T16** Owner to identify the newer/better approach tried earlier (name, or file/chat) so it can be recorded and reused  _(n8n · needs owner)_

## To do (9)

- **T03** SyncNet-gate the A/B clips, side-by-side, owner picks winner  _(n8n · after T02)_
  - bin/kgpu run jobs/syncnet-eval --input <dir> --timeout-min 25. Gate: >= 0.9 x sync-3 (7.65).
  - 2026-11-27: Done for 03_who via bin/kgpu run jobs/syncnet-eval. Gate passed.
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
  - 2026-11-27: greece-v2 now also contains final-cut-lab.
- **T13** Fix true peak 0.1 dB over limit in promo master (v7)  _(n8n · after T04)_
- **T15** Delete stale claude/project-thread-* branches (Rule 0; content already in greece-v2)  _(infra · needs owner)_

## In progress (0)


## Waiting on owner review (2)

- **T02** Lip-sync A/B on line 03_who: LatentSync 1.6 / X-Dub / TBDub full-res  _(n8n · after T01)_
  - python3 -m lane.modal_lipsync ab-download --model latentsync16|xdub, then ab --model ... --video kaggle/work/lipsync/01_n8n_automation_v6/03_who_src.mp4 --audio assets/voice/01_n8n/03_who.mp3
  - TBDub full-res needs owner's sample-video.mp4 (60 MB original).
  - 2026-11-27: Owner 2026-11-27 (late): believes a newer, better lip-sync approach was already tried before this session, and the n8n video was 'quite good already' after a GPT review; Greece v2 was underway. NOT found in repo/Kaggle/other sessions (only this session exists). LatentSync 1.6 test clip made anyway (work/ab/03_who_latentsync16.mp4, $0.27 Modal), unscored. PAUSE further lip-sync spend until owner says which approach.
  - 2026-11-27: RESULT: LatentSync 1.6 (Modal L40S) on 03_who: LSE-C 8.454, offset 0 (TBDub same line 6.125; real 8.23; gate 6.89) -> PASSES. Owner to confirm by eye; then run other 5 lines (~$1.6) and render v7. X-Dub skipped (image lacks click; not needed).
  - 2026-11-27: blocked -> review
- **T07** Owner feedback on Greece film v1  _(greece · needs owner)_
  - v1 sent in chat 2026-11-27 17:15 UTC (39 MB share copy). Master was NOT backed up to Kaggle; it died with that container.

## Done (11)

- **T01** Fix Modal lip-sync API key mismatch  _(infra · needs owner)_
  - 2026-11-27: /health 401. Server key 51 chars fp c2c204; session LIPSYNC_API_KEY 43 chars fp e6ea20. Owner: set GitHub secret LIPSYNC_API_KEY to the session value + re-run 'Deploy Modal lip-sync API', or give the session the 51-char value.
  - 2026-11-27: Re-checked: still 401, same fingerprints. Kaggle OK (usmanqureshi94), ElevenLabs OK (Starter, 28,969 of 40,000 chars used), GitHub push OK.
  - 2026-11-27: Owner may create a new key: new value -> GitHub secret LIPSYNC_API_KEY -> re-run deploy -> session gets it via secure credential form (host nubuqqrr--video-system-lipsync-api.us-east.modal.run, header x-api-key).
  - 2026-11-27: blocked -> done
  - 2026-11-27: Fixed 2026-11-27: owner set new GitHub secret, deploy re-run, /health ok, key saved in session via credential form.
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
- **D08** Final-cut lab built: Whisper script check, SyncNet per face shot, loudness, cut rules, contact sheet, touch-up gate  _(infra)_
  - 2026-11-27: Branch final-cut-lab, merged into greece-v2. Run before delivering any master: scripts/final_cut.py
- **D09** Final-cut on n8n v6: FAIL lip-sync (LSE-C 3.9-6.05 vs min 6.887) + true peak -1.4 dB (max -1.5)  _(n8n)_
  - 2026-11-27: Face touch-up (GFPGAN) and RIFE on lip-sync clips both rejected by SyncNet gate (LESSONS 74-78). Report: reports/final-cut/01_n8n_automation_v6.md
- **T14** ChatGPT (Codex) sign-in on this container  _(infra · needs owner)_
  - 2026-11-27: Codex 0.169.0 installed. Owner enters the device code at auth.openai.com/codex/device.
  - 2026-11-27: Signed in; lane.chatgpt ask test returned ok. Auth at ~/.codex/auth.json (per container).
  - 2026-11-27: blocked -> done
