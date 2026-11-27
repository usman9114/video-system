# GPU cost & speed playbook (2026-11-27)

Owner rule: **always use the most resource-efficient setup (distilled, quantized, cached, batched), but never at the
cost of output quality.** Every optimization must pass the **quality gate** below before it becomes a default in
`templates/production.json` → `inference_optimization`.

## Quality gate (mandatory for every new optimization)
Run the SAME inputs + seed twice: baseline vs optimized. Accept only if all of these hold:
- **Frames:** SSIM ≥ 0.95 and LPIPS ≤ 0.05 vs baseline (or, for distilled models, the owner's eye in a side-by-side).
- **Faces:** identity similarity to the source photo/footage is no lower than baseline (ArcFace/ECAPA-style check).
- **Lip-sync** (TBDub/X-Dub): SyncNet LSE-C no lower than baseline −2%.
- Measured GPU-seconds and $ are logged (`reports/modal-usage.jsonl`).
Reject → keep the baseline, and record why in `docs/LESSONS.md`.

## Levers, ranked by payoff for OUR workloads
| # | Lever | Typical gain | Quality risk | Where it applies | Status |
|---|---|---|---|---|---|
| 1 | **Distilled models** (few-step): FastWan2.2-TI2V-5B (3 steps, Apache-2.0); TBDub Student (2 steps) | 10-30× | low-medium → gate | photo→video; lip-sync drafts | FastWan built (branch `fastwan`); TBDub Teacher kept for finals (owner's quality pick) |
| 2 | **One GPU session per job** (load model once, process all clips) | removes ~1-3 min per clip | none | all batches | FastWan batch ✅; lip-sync still one call per clip → TODO batch |
| 3 | **Right-size the GPU** (cheapest card that fits without offload) | 1.5-4× $ | none | all | L40S for 5B/TBDub ✅; H100 only when > 48 GB needed |
| 4 | **No CPU offload when VRAM fits** | 2-3× | none | Wan 5B on 48 GB | ✅ (FastWan path) |
| 5 | **Fast attention kernels**: FlashAttention-3 (H100), **SageAttention2** INT8/FP8 QK (L40S/Ada/Hopper) | attention is ~70% of Wan runtime → 1.5-2× | very low (gate) | Wan, TBDub/X-Dub (Wan-based) | TODO: A/B on FastWan + TBDub |
| 6 | **Step caching** (MagCache / TeaCache): skip near-identical denoising steps | 1.5-2× (Wan2.2 TI2V-5B 720p: 10m39s → 5m24s per MagCache) | low at conservative thresholds; artifacts if aggressive | ONLY many-step models (TBDub Teacher, full Wan); useless at 3 steps | TODO for TBDub Teacher (30 steps) |
| 7 | **FP8 weights/activations** (torchao float8 / TensorRT-LLM FP8) on L40S/H100 | 1.3-1.6× GEMM, less VRAM | low-medium → gate | big DiTs | TODO after #5 |
| 8 | **torch.compile + TF32** | 1.2-1.4× | none | long batches | TODO; pair with #9 so compile isn't paid per cold start |
| 9 | **Modal GPU memory snapshots** (restore compiled model instead of reloading) | cold start 8-36× faster | none | frequent small jobs | TODO (experimental on Modal) |
| 10 | **TensorRT-LLM VisualGen** (Wan 2.1/2.2, FP8/NVFP4 + TeaCache + Sage kernels) | biggest combined gain | low (NVIDIA-validated) | high volume only | later: heavy engine build, docs focus on B200 |
| 11 | Short clips & smart scope (3.5 s per photo; animate hero shots, 2.5D parallax for the rest) | ~2-3× | none | Trip Memories | planned |
| 12 | Cost guards: `scaledown_window=2`, timeouts, $ caps, per-run logging | avoids waste | none | all | ✅ |

## Not possible / not worth it
- **Overclocking: not possible on cloud GPUs.** Modal (like every cloud) gives no driver/BIOS/clock control. Data-centre
  cards already run at their validated boost clocks, and billing is per second, so the only way to "overclock" is to do
  less work per output (levers above).
- Int8 weight-only quantization on Wan was *slower* than TF32 + FA3 in Morphic's H100 tests. Don't assume quantization = faster;
  always measure.
- Very aggressive caching thresholds visibly degrade video (Morphic MagCache E024 showed artifacts).

## Sources
MagCache (arXiv 2506.09045; MagCache4Wan2.2 README), Morphic Wan2.2 H100 optimization blog, Voltage Park Wan2.2
acceleration blog, SenCache (arXiv 2602.24208), NVIDIA TensorRT-LLM VisualGen docs + blog 28 (FP8/NVFP4/Sage attention for
video DiTs), NVIDIA TensorRT DiT video blog, Modal GPU memory snapshot docs/blog, FastVideo FastWan2.2 model card.
