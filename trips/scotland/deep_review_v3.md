## 1) Verdict

**Current cut: 5.5/10. Achievable with this material: 8/10.**

There’s a good film in the idea: a personal trip from Edinburgh’s interiors to London’s night sky, tied together by the feeling of looking up. The stained glass and final skyline can make that feel like a real emotional progression.

Right now, the repeated cathedral views risk turning contemplation into repetition; the narration carries a lot of guidebook facts; and the generated shots need to feel more securely attached to the real photographs. The first two seconds also need a stronger reason to keep watching.

**One edit note to resolve first:** the supplied timeline ends at **1:56.9**, but the contact sheet runs to **3:56** and includes the London night sequence and title card. I can’t reliably judge the actual ending or its precise timing until those refer to the same cut. For the v4 plan below, I assume the intended finished runtime is **2:00**.

## 2) Owner notes: 1–3 solutions

### 1. Make every shot of you begin on the real photo

For any shot where your face or body is visible, use that actual photo as the image-to-video input and select the option that uses the reference image as the first frame. Wan’s implementation exposes this as `init_first_frame` / `--start_from_ref`; confirm your interface’s equivalent is enabled. [Wan 2.2 reference-frame option](https://github.com/Wan-Video/Wan2.2/blob/main/wan/speech2video.py)

Then:

- Hold the original photo for **8–12 frames** at 24 or 30 fps.
- Cut or briefly dissolve into the generated continuation.
- Use only the **first 2–3 seconds** of a generation. If the face starts to drift, cut back to the photo or move to a detail shot.
- Keep the move small: one head turn, a glance upward, a subtle shoulder shift, or a small step.

**Prompt starting point:**  
> Start exactly from the supplied photograph. Preserve the man’s identity, face, clothing, body proportions, companion, architecture, and composition. Locked camera. He takes a quiet breath, then gently turns his eyes toward the cathedral window. Natural restrained movement, documentary realism. No new objects, no camera move, no face change, no hand movement.

For the window shot, swap in “he slowly raises his gaze toward the window.” For a companion moment, try “they exchange a small smile”; avoid asking Wan to invent complicated contact or detailed hand gestures.

### 2. Give the narration more space and contrast

Keep the personal voice, but stop asking every sentence to do two jobs. Put the useful historical fact in narration or on screen, then give the image a beat to breathe.

For ElevenLabs Multilingual v2, generate short lines separately so you can choose a different take or pace for each. A reasonable starting experiment is **speed 0.93–0.97, stability around 40–50%, style 0**; treat those as trial values, not universal settings. ElevenLabs says lower stability can add expression, while excessive lowering can make delivery erratic; it recommends leaving style at zero in general. For v2, use `<break time="0.6s" />` for pauses. Audio tags such as `[softly]` and `[excited]` are for Eleven v3/v4; those models do not support SSML break tags. [ElevenLabs voice settings and pause guidance](https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech) · [ElevenLabs prompting guidance](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices)

### 3. Use gestures as brief punctuation, not choreography

Plan **one clear gesture per useful shot**: touch the railing, turn toward your companion, glance back to camera, or point once toward the window. The pointing shot is the riskiest because it requires a convincing hand and finger shape. Try two seeds, pick the better take, and cut away before the hand becomes prominent. For the more expressive companion moment, use the high-quality Seedance clip if it begins from the real photo; otherwise, preserve the real photo and animate only a small head or shoulder movement.

## 3) Top 10 other fixes, ranked by impact

Costs below are relative to tools you already have; generation costs depend on your current subscriptions and credit allowances.

| Rank | What and why | How to implement | Effort / cost | Wan risk and mitigation |
|---|---|---|---|---|
| **1** | **Reconcile the runtime and rebuild the cut map.** The timeline and contact sheet appear to describe different-length edits. | Confirm the intended 2:00 master, then map every shot, narration line, title, and silent beat against that export. Trim or remove material to land at 120 seconds. Use FFmpeg for final conform if needed: `ffmpeg -i v4_master.mov -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,format=yuv420p" -c:v libx264 -crf 18 -preset slow -r 30 -c:a aac -b:a 192k -movflags +faststart v4_vertical.mp4` | **M / $0** beyond edit time | **Low:** this is a timeline issue. |
| **2** | **Replace the slow opening with a human hook.** The opening ceiling and seated figure are atmospheric but don’t immediately establish the journey or its personal point of view. | Open on your strongest real image of you looking up, with “I kept looking up—from Edinburgh to London.” Show **EDINBURGH** as a small location label, not a long title card. Let the ceiling follow as the first visual answer. | **S / $0** | **Medium** if you animate the face. Start on the photo; use a tiny eye or head movement, or keep the hook on the still. |
| **3** | **Give the middle a progression, not a catalogue.** The repeated nave/window views risk feeling like variants of one shot. | Build three clear movements: **arrive and settle** (chair/street), **look up** (St Giles’ and window), **carry the feeling into London** (night skyline). Keep the strongest window view and one meaningful detail; shorten similar views. | **M / $0** | **Low:** edit choice, not generation. |
| **4** | **Shorten factual narration and leave gaps for the images.** Several lines are dense, especially the window attribution and date. | Use the revised script below. Put secondary details in brief on-screen text if they are legible over the relevant image. Generate each sentence as a separate ElevenLabs take; use modest pauses instead of slowing the entire voice track. | **M / existing subscription** | **Low** |
| **5** | **Add a restrained location sound bed.** The film currently has no audible sense of chair, footsteps, cathedral, or river, so the generated score has to carry too much. | Lay in a quiet room tone at the opening, soft footsteps for the street transition, a long gentle reverb tail inside St Giles’, then distant city and river sound at night. Keep effects subtle and use short fades. Generate or source ambience separately; don’t ask Wan to supply it. | **M / $0–low** | **None** |
| **6** | **Shape the score around one deliberate release.** A continuous piano/pad/strings bed can flatten the piece even when the images change. | Start with sparse piano; add a low pulse or strings on the move into St Giles’; thin the music beneath the east window; let the London skyline widen the sound. At the emotional peak, cut narration and music for **one full second**, then allow the ending to resolve. | **M / existing music tool or credits** | **None** |
| **7** | **Match the real stills and generated shots.** The source types can feel like separate worlds if their contrast, warmth, and texture differ. | Choose a reference still for each location. Match exposure and white balance first, then reduce any excessive AI saturation or sharpness. Add a very light consistent grain only if it helps the stills and motion sit together. | **M / $0** | **Medium** where faces drift in tone or shape. Cut back to the real frame before the mismatch becomes conspicuous. |
| **8** | **Use captions for mobile viewing, and keep them clear of interface overlays.** The location labels are useful, but the historical information needs careful screen placement and reading time. | Burn in concise, readable captions for dialogue and use separate, smaller location labels. Keep text inside a central safe area; TikTok’s guidance recommends vertical 9:16 and keeping text away from controls. An SRT can be burned in during an FFmpeg export with the `subtitles` filter. [TikTok vertical-format and safe-zone guidance](https://ads.tiktok.com/business/en/guides/video-advertising-guide) | **S–M / $0** | **None** |
| **9** | **Make the ending feel earned, then get out.** The night images and “LOOKING UP” title can work, but the contact sheet suggests a long stretch of similar skyline framing before the title. | Hold on the strongest image of you looking up, end the narration on “I leave still looking up,” give the silent peak, then show a short title card. If the sheet’s final night section is in the master, trim repeated near-identical frames. | **S / $0** | **Medium** if the final face shot is generated. Prefer the real photo or cut to skyline before the face drifts. |
| **10** | **Make separate platform exports only if the crop or caption placement requires them.** A two-minute vertical master is a viable starting point for short-form platforms, but layout and rights still matter. | Keep a clean **9:16, 1080×1920** master and check captions against each app’s interface before posting. A two-minute vertical video is within YouTube Shorts’ current three-minute limit; for a Short longer than one minute, YouTube says an active Content ID claim can block it, so check the rights status of the generated score. [YouTube Shorts length and music guidance](https://support.google.com/youtube/answer/15424877) | **S / $0** | **None** |

## 4) Concrete v4 plan

1. **Confirm the real master duration.** Reconcile the 1:56.9 timeline with the 3:56 contact sheet. Build the v4 timeline to the intended 2:00 runtime.
2. **Reorder around the journey.** Start with you looking up; settle into the chair; move outside with your companion; enter St Giles’; reveal the east window and Bellany paintings; finish at the Thames at night.
3. **Choose one best image per beat.** Reduce the repeated window and painting angles. Use longer holds only where the image changes emotionally or visually.
4. **Regenerate only the human shots that need motion.** Feed each original photograph into Wan, enable its reference-first-frame option, keep the movement small, generate two seeds, and use the cleanest first 2–3 seconds. Favor the Seedance clip for any shot that needs a convincing face or companion interaction.
5. **Record the revised narration in short pieces.** Try v2 with separate generations and SSML pauses; compare with v3 audio-tagged takes for the most important lines. Don’t speed up the whole track to make it fit—trim words or shots instead.
6. **Build the sound arc.** Add quiet location beds and specific footsteps, room tone, cathedral reverb, and river/city sound. Keep them below the voice. Thin the score before the one-second silent peak.
7. **Match the grade and captions.** Normalize the real and generated shots, add concise burned-in captions, and keep all text inside a mobile-safe area.
8. **Finish and check the export.** End on the strongest final image, keep the title brief, export vertical 1080×1920, and verify that the audio and captions remain legible on a phone-sized screen.

## 5) Revised narration

This version keeps the supplied facts while reducing the guidebook cadence. The tags below are for an **Eleven v3 trial**; v3 supports audio tags but not SSML breaks. If staying with Multilingual v2, remove the bracketed tags and use the indicated pauses as `<break time="0.6s" />` in separate generations. [ElevenLabs model-specific pause guidance](https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech)

> [softly] I began in Edinburgh, already looking up.  
> Even the ceiling felt like a beginning.  
> I sat, let my shoulders drop, and listened to the room.
>
> The Royal Mile runs from the Castle to Holyroodhouse—about a Scots mile.  
> Outside Old Town Chambers, at 329 High Street, my companion and I found our pace.
>
> Then St Giles’. David the First founded it in 1124.  
> John Knox preached here from 1559. This is Edinburgh’s High Kirk.  
> [pause] I looked up.
>
> The east window shows the Crucifixion and the Ascension.  
> A guide credits it to Ballantine of Edinburgh. Its 1874–77 inscription dates mark Lord Provost Falshaw’s term.
>
> I stayed longer than I meant to.  
> Below it: John Bellany’s harbour paintings, with Port Seton’s fishing boats.
>
> [softly] At night, the Thames held the lights.  
> The City’s towers blurred behind me.  
> [pause] I leave still looking up.
