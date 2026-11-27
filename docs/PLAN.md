# Parallel plan (Opus advisor, 2026-11-27)

Main session (Opus / opusplan) directs and is the ONLY writer of the board (`tracker.py`, `pm.py`) and git. Subagents get a <=150-word
brief, hand back <=100 words (numbers + pass/fail), never commit.

| Stream | Agent | Cost | Steps | Gate |
|---|---|---|---|---|
| S1 Greece v2 | Sonnet subagent, CPU | $0 | preview -> ChatGPT still review -> full render -> `scripts/trip/finish.py` -> `final_cut.py --kind trip` -> S3 backup | M1 owner OKs preview |
| S2 n8n lip-sync | Sonnet subagent | ~0.3 Kaggle GPU-h | fix TBDub 03_who frozen frames (39,81,167,233; blend neighbours, no RIFE); check face-box jump at f89; one SyncNet job (fixed TBDub, LatentSync, real); side-by-side + 2x slow-mo mouth | M2 owner picks by eye; no Modal spend before |
| S3 Infra | Haiku subagent | $0 | limiter ceiling -2.0 dBTP, re-run loudness pass on v6, must be <= -1.5; back up every new export to Kaggle (one at a time); prepare push/branch-delete commands, don't run | M3 owner OKs push (push to main redeploys Modal: check /health after) |
| S4 Gigs 2-10 | ChatGPT lane | $0 | draft gig-text questionnaire, owner fills it | owner answers |

TBDub vs LatentSync: fix TBDub first ($0). If fixed TBDub passes LSE-C 6.89 and owner likes it, keep TBDub. Else one more LatentSync
line (01_hook, ~$0.27), then decide. Full LatentSync = 5 lines ~$1.6 of Modal free credits. If the look gap is sharpness, try a gated
upscale of LatentSync's face crop. Worst case ~$1.9 credits, 0.5 GPU-h.

Token rules: ChatGPT does review/research/writing/images; Claude decides. Never re-read HANDOFF/LESSONS/optimization in full, grep.
One `pm.py sync` per merge point. One SyncNet job for all clips. `tail -20` on logs. Haiku for mechanical work; Opus advisor only at M1-M3.
Kaggle jobs one at a time.
