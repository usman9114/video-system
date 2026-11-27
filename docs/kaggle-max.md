# Getting the most out of Kaggle's free GPUs

Kaggle gives this account **6 GPU-hours a week** (21,600 s, resets Saturday 00:00 UTC; `bin/kgpu quota`) on a
**2× T4** machine. Kaggle bills **session time, not per GPU**, so a session that keeps only one T4 busy wastes half
of what we pay for in quota (LESSONS #43). Every job here therefore splits its work across both GPUs.

## What runs on Kaggle now

| Stage | Job | GPU0 | GPU1 | Typical session |
|---|---|---|---|---|
| Final-cut lab (every master, before delivery) | `jobs/final-cut` via `scripts/final_cut.py` | Whisper large-v3 → SyncNet on the master | face-detail touch-up → encode → SyncNet on the touched cut | ≈ 18 min for a 46 s promo with the touch-up (GFPGAN ≈ 1.3 fps per T4 at 1080×1350), ≈ 6 min without |
| Fill lab (pre-render gaps) | `jobs/fill-lab` via `scripts/fill_lab.py` | half the clips | other half (longest-first, so both finish together) | 113 s for six lip-sync clips (measured) |
| Captions | `jobs/transcribe` | Whisper | (idle: short job) | ≈ 2 min |
| Logo removal | `jobs/inpaint-logo` | LaMa, frames split | LaMa, frames split | ≈ 1 min |
| Lip-sync gate | `jobs/syncnet-eval` | SyncNet | (idle) | ≈ 4 min |

Modal (paid from the free $30/month) keeps the jobs a T4 can't do well: TBDub/LatentSync 1.6 lip-sync, Wan video.

## Weekly budget (6 h)

| Use | Share | Why |
|---|---|---|
| Final-cut lab on every master + re-checks after fixes | ≈ 1.5 h | ~5 full runs with touch-up; the cheapest place to catch a bad cut before the owner sees it |
| Fill lab (RIFE 25→30 fps on lip-sync clips, hero-clip 24→30 + upscale) | ≈ 1 h | every new lip-sync batch / gated hero clip |
| Lip-sync A/B scoring (SyncNet on candidates from Modal) | ≈ 1 h | the open lip-sync problem (HANDOFF) needs objective scores per candidate |
| Captions/transcripts for new source footage (videos 2-10) | ≈ 0.5 h | Whisper large-v3 per new talking-head video |
| Reserve | ≈ 2 h | re-runs; never plan to 100 % |

## Rules that keep it efficient
- Use Kaggle's own torch (no second PyTorch download), pip `--no-deps` for torch-pinning packages (LESSONS #28).
- One job at a time; `--no-wait` + a background wait so long runs never block the session.
- Nothing heavy under `/kaggle/working` (it becomes output; LESSONS #31). Weights and envs live in `/tmp`.
- Measure both GPUs: final-cut and fill-lab log mean utilisation per GPU into their result JSON. SyncNet's face
  tracking is CPU-heavy, so its lane shows low GPU utilisation; that is the known limit, not a bug.
- Stop on quota errors. Check `bin/kgpu quota` before a big batch.

## Next candidates (not built yet)
- A `kgpu-wheelhouse` private dataset with the RIFE / GFPGAN / Real-ESRGAN / Whisper weights so setup skips downloads.
- Batch several masters into one final-cut session (setup cost paid once).
