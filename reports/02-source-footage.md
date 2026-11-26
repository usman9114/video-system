# Phase 3: Source Footage Report (preliminary)

File analysed: `source/original_small.mp4` (owner's compressed copy, read-only,
sha256 `3fbe1506…2791c`). **To be re-run on the 60 MB original** for final resolution, bitrate and audio numbers.
Contact sheet: `reports/source-analysis/contact-sheet.jpg`.

## Technical
| Property | Value | Note |
|---|---|---|
| Duration | 52.2 s (speech ends at about 48.6 s; then a 3.6 s end card) | |
| Resolution | 864×1080 (4:5 portrait) | Instagram-style export. Max 1080 tall, so 9:16 needs a layout, not a crop |
| Frame rate | 30 fps, progressive | |
| Video bitrate | 435 kbps (compressed copy) | Soft. Use the original for exports |
| Audio | AAC 48 kHz stereo, -23.5 LUFS, peak -10 dBFS, LRA 1.8 LU | Clean, no clipping, very low noise floor. Needs a gain lift to about -14 LUFS |
| Black frames | none | |
| Frozen frames | 49.6 s → end (static end card) | Cut |
| Shots | 2 camera angles (wide desk + close-up), cut at 21.1, 23.1, 37.4, 39.8, 45.3, 46.6 s | Good: two angles make edits feel natural |

## Look
- Lighting: soft, even, natural daylight. Flattering, no harsh shadows. ✅
- Background: whiteboard grid with sticky notes. Reads as "workshop / strategy". Fits consulting and AI gigs. ✅
- Framing: centred, eye-level, good headroom. A lav mic (DJI) is visible. Professional look. ✅
- Delivery: calm, confident, natural smiles. Good gestures at about 47-50 s (open hands: "We would love to show you…").

## ⚠️ Blocking limitations
1. **Burned-in third-party branding.** The UN WFP logo is in the top-right corner for the whole video, a "UN WFP Innovation Accelerator"
   end card follows, and a lower-third reads "Usman Qureshi, Consultant, Artificial Intelligence Solutions".
   Using UN or WFP marks in a commercial Upwork promo can imply endorsement, and the UN emblem is restricted.
   → Logos must be **cropped out** of every frame, and the end card dropped.
2. **Burned-in subtitles** in the lower third of every frame. They can't be removed cleanly.
   → Crop above them (about y < 760 px). The usable clean area is about 600×650 px around the face, so 9:16 and 16:9
   outputs need a designed layout (framed talking head + text panels, or a blurred background fill). Plain upscaling would look soft.
3. **The speech is WFP-specific** ("real value for WFP", "Augmented Building Damage Assessment"…). Most lines can't
   be reused as-is for Upwork gigs without misleading viewers.
4. **Ownership:** this looks like a WFP-produced video. The owner must confirm they have permission to reuse it commercially.

## Reusable lines (generic and true, pending owner confirmation)
| Time (approx.) | Line | Usable for |
|---|---|---|
| 0.0-5.0 | "Emerging technologies are transforming every industry…" | AI consulting hook |
| 5.4-10.9 | "It's our job to identify which technologies can create real value…" (cut before "for WFP") | AI strategy / consulting |
| 31.4-37.4 | "We focus on practical application, not technology for its own sake." | Strong trust line for any AI gig |
| 37.4-43.7 | "We test with users [caption reads \"words\"; verify by transcript], understand the risk…" | AI product / MVP gigs |
| 40-46 | "Done right, emerging technologies can help us operate more efficiently, make better decisions, and reach more people." | Closing line |
| 46.8-48.6 | "We would love to show you what we are building." + open-hand gesture | CTA moment (good expression) |
| 11.3-30.8 | Satellite / building-damage project description | Only as a factual portfolio case study, if the owner may name it |

Awkward pauses: few. Silences ≥ 0.35 s at 5.0, 10.9, 22.8, 30.8, 43.7 and 46.4 s are all natural breaths of 0.37-0.53 s. Trim to about 0.15 s.

## Implication for the 10 videos
The footage alone can't carry 10 different scripts. Options (decision for the owner):
- **A. Record a new talking-head session (recommended, $0):** same setup, 10-15 minutes reading 10 short scripts.
  Best realism and conversion. The current footage becomes the B-roll and cutaways.
- **B. New voiceover + this footage as visuals:** works only with heavy B-roll, because the lips won't match.
- **C. AI lip-sync (MuseTalk on the free Kaggle GPU):** possible, but the burned subtitles must be cropped first and
  realism isn't guaranteed. Test only.
