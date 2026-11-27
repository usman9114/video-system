# Idea: "Trip Memories", ~10 photos → a short documentary-style travel film

Owner idea (2026-11-27): like the Scotland cathedral clip, but for a whole trip. Someone uploads about 10 photos and gets
a cinematic mini-documentary of the trip. Could become its own Upwork gig or product.

## What the viewer gets (MVP)
A 45-75 s film, 9:16 (Reels/TikTok) + 16:9 (YouTube), 30 fps (60 optional):
1. **Cold open**: the most striking photo comes alive (camera move + natural motion), then title card *"Scotland · September 2026"*.
2. **Journey**: photos in chronological order, each animated for 3-5 s, cut on the music's beats, gentle cross-dissolves.
3. **Story layer**: short documentary captions per scene ("First light over Edinburgh", "Inside St Giles'…"), optional
   narration in the traveller's own voice (their ElevenLabs clone or a voice memo) or no voice at all.
4. **Route moment** (if photos have GPS): a stylised map with the route drawing itself between stops.
5. **Ending**: a slow push-in on a reflective photo + *"Until next time."*

## Pipeline (every piece already exists in this repo, except where marked NEW)
| Step | Tool | Status |
|---|---|---|
| Ingest: EXIF date/GPS, sort by time, drop duplicates/blurry, pick the cold-open photo | Python (Pillow EXIF) + Claude judgement | NEW (small) |
| Story: arc (arrival → exploration → highlight → reflection), per-photo shot direction + caption (+ narration line) | Claude | NEW (prompt template) |
| Animate each photo | **Wan 2.2 TI2V-5B** on Modal (owner's preferred model), 2 seeds | ✅ `/wan/generate` |
| Pick the best take + protect identity | face-similarity check (photo vs frames; reject drift) → fallback: Ken Burns / 2.5D parallax | NEW (ArcFace check; Ken Burns ✅) |
| Smooth to 30/60 fps | **RIFE** frame interpolation on Modal (MIT) | NEW (in progress) |
| Consistent look | one colour grade + light film grain across clips | NEW (ffmpeg LUT) |
| Music | original synthesized bed ✅, or a licence-checked track | ✅ / owner choice |
| Narration (optional) | ElevenLabs clone ✅ or traveller's voice memo | ✅ |
| Edit + titles + export 9:16 / 16:9 | `scripts/promo.py` renderer (new "trip" template) | ✅ engine, NEW template |

## Cost: optimised (owner 2026-11-27: "$10 is a lot")
The first TI2V-5B test cost $0.95/clip because of: memory offload on a 48 GB card, 50 steps, 5 s, model reload per photo.
Optimised plan:
| Lever | Effect |
|---|---|
| **FastWan2.2-TI2V-5B** (FastVideo, Apache-2.0): 3-step DMD distill of the owner's preferred model, guidance 1.0 (no CFG) | ~15-30× fewer transformer passes |
| **One GPU session per trip** (model loaded once) | saves ~2-3 min/photo |
| No offload on the 48 GB L40S | ~2-3× faster |
| 3.5 s per photo (85 frames) instead of 5 s | ~1.4× |
| Animate 4-5 hero photos; 2.5D parallax (depth-based) on the rest | ~2× |
Target: **≈ $0.30-0.80 per 10-photo trip** (to be confirmed by the first measured batch). Quality fallback: full TI2V-5B for hero shots only.

## Quality rules (inherit templates/production.json)
- Faces: reject any clip where the person drifts from their photo (identity check), use the parallax fallback instead.
- ≥ 30 fps output (RIFE), 1080p target.
- No fabricated places/facts in captions: only what the photos/EXIF/traveller say.
- Real-reference rule for any added graphics (map style from a real map reference, redrawn).

## First test = the owner's own Scotland trip
Needs: the ~10 Scotland photos as files (Drive `upwork-video-system/assets/scotland/`), plus optionally 1-2 lines per
photo (where/what) or "you direct".
