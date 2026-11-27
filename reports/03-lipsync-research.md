# Lip-sync research: open-source models vs sync.so sync-3 (2026-11-27)

Goal: owner's REAL footage + new ElevenLabs voice line, at sync-3 quality, open source, commercial use OK.
Video-to-video ("visual dubbing") models only. Photo-to-avatar generators are out of scope.

## Tested so far (same 11.5 s clip, same voice) → `previews/lipsync_compare_4way.mp4`
| Model | Licence | Where | Result |
|---|---|---|---|
| sync.so **sync-3** | proprietary | API (free trial = watermark) | Reference quality. Owner: "really good" |
| LatentSync 1.5 | Apache-2.0 (code) / weights OpenRAIL | Kaggle T4, free | Works; about 10 min GPU per 11.5 s; owner: not at sync-3 level |
| MuseTalk 1.5 | MIT code / OpenRAIL-M weights | Kaggle T4, free | Works; about 35 s GPU per clip; softer lower face |
| LatentSync 1.6 (512 px) | Apache-2.0 | Kaggle T4 | OOM at default; low-memory variants (8/12-frame chunks) running |

## Best untested candidates (ranked for our use case)
| # | Model | Who / when | Licence | Why it might match sync-3 | GPU need |
|---|---|---|---|---|---|
| 1 | **TBDub** (Student = 2-step distilled, Teacher = 30-step) | Taobao Live, Sept 2026 (arXiv 2609.06144) | **Apache-2.0 code + weights** | "Production-oriented" mask-free editing; post-trained on top of X-Dub for robustness; 7.13 FPS on H20 at 512² | BF16. Peak **15.0 GiB (Student) / 19.5 GiB (Teacher) with `--cpu-offload`**, 28 GiB default; host RAM about 22 GiB → **24 GB card OK**. Not a T4 (no BF16, 14.6 GiB usable) |
| 2 | **X-Dub** | Kuaishou Kling team, ICML 2026 (arXiv 2512.25066) | **Apache-2.0** | Mask-free "inpainting → editing" dubbing on Wan2.2-TI2V-5B; claims better sync, visual quality and identity than prior open methods | about 21 GB → 24 GB card |
| 3 | InfiniteTalk | MeiGen, 2025 | Apache-2.0 | Re-animates head and body; but its own paper shows worse FID/identity than LatentSync on HDTF (CSIM 0.775 vs 0.916) | 14B; 48-80 GB comfortable |
| 4 | LTX-2.3 Dub-It / LipDub IC-LoRA | Lightricks, 2026 | **LTX community licence** (not OSI; gated) | Regenerates lips and speech together, mask-free | 22B base: large GPU |
| 5 | KeySync | 2025 | weights released | Leakage-free lip sync | moderate |
| – | OmniSync, SyncAnyone, LiveSync | 2025-26 papers | release unconfirmed | — | — |
| ✗ | Wav2Lip | — | non-commercial | outdated (96 px mouth) | — |

## Verdict
No open model is *proven* equal to sync-3 (no public head-to-head). The strongest open contenders for real-footage
dubbing are **TBDub** and **X-Dub** (both Apache-2.0, both 2026, both from teams that ship commercial lip-sync). They need
a 24 GB BF16 GPU, so they're **not runnable on free Kaggle T4s**.

## Proposed RunPod test (owner approval needed; hard cap $3)
- 1× RTX 4090 24 GB (or L40S 48 GB) on-demand, verified datacenter; auto-terminate when the job ends.
- Run on the same clip: TBDub Student, TBDub Teacher (`--cpu-offload`), X-Dub.
- Score against sync-3: **SyncNet confidence (LSE-C ↑ / LSE-D ↓)**, **face identity similarity** to the original frames,
  sharpness of the mouth region, plus the owner's side-by-side review.
- Pass = matches sync-3 on sync confidence and identity, and the owner can't tell it's worse → produce all 10 there
  (est. $5-12 total for about 350 s of face, to be firmed up from the test's real timing).

Sources: TBDub GitHub README (Born-Digital-AI/TBDub mirror of TaoLiveAIGC), arXiv 2609.06144; X-Dub GitHub
(KlingAIResearch/X-Dub), arXiv 2512.25066, ICML 2026 poster; InfiniteTalk arXiv 2508.14033; LTX Dub-It docs; KeySync
project page; LatentSync/MuseTalk repos.
