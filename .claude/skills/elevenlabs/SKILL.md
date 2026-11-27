---
name: elevenlabs
description: Use the owner's ElevenLabs account (Starter plan) to voice video scripts in the owner's own cloned voice: prep the clone sample, generate lines with character timestamps (frame-accurate captions), stitch lines for continuous prosody, pick takes with the objective similarity gate, and keep credit use minimal. Use for any voiceover, narration or AI-voice task in this repo. Not for music or sound effects.
---

# ElevenLabs lane: owner's voice, maximum quality, minimum credits

Code: `lane/elevenlabs.py` (stdlib only). Usage log: `reports/elevenlabs-usage.jsonl`. Cache: `kaggle/cache/elevenlabs/`.
Owner consent to clone **their own** voice: 2026-11-27. Never clone anyone else's voice.

## Account facts (verified 2026-11-27)
- Plan **Starter**: **40,000 credits/month**, instant voice cloning (IVC), commercial licence. No PVC (needs Creator).
- Output formats on Starter: up to **`mp3_44100_128`** (`mp3_44100_192` returns 403 and needs Creator).
- API key = cloud-environment network secret, injected as `xi-api-key` on `api.elevenlabs.io` (we send a placeholder).
  Key permissions needed: **Voices → Write**, **Text to Speech → Access**, User → Read (for `whoami`).
  A 401 `missing_permissions` error means the owner must edit the key's permissions (the value stays the same).
- Owner clone: `assets/voice/elevenlabs_voice.json` (voice_id `jwItKKDHu8LXzA2tIhdT`, made from a 48 s sample).

## Workflow
```bash
python3 -m lane.elevenlabs prep <video|audio> [--start s --end s]      # → assets/voice/ivc_sample.mp3 (IVC spec)
python3 -m lane.elevenlabs clone assets/voice/ivc_sample.mp3 --name "..."  # once; stores voice_id
python3 -m lane.elevenlabs say --job scripts/videos/<id>.voice.json --out kaggle/outputs/voice-11l/<id> --takes 2 --dry-run
python3 -m lane.elevenlabs say --job ... --out ... --takes 2            # real run (cached and logged)
python3 -m lane.elevenlabs usage                                       # credits spent so far
```
Job JSON: `{"lines": {"01_hook": "...", ...}, "settings": {"stability": 0.45, "similarity_boost": 0.85, "style": 0.0}}`.
Each line gives `<line>_t<k>.mp3` + `<line>_t<k>.align.json` (word timings in the same `{w,s,e}` format as Whisper,
so `scripts/promo.py` captions use them directly, with **no Whisper run needed**).

## Quality rules (ElevenLabs docs + our measurements)
1. **Clone sample**: one speaker, no noise, MP3 ≥ 192 kbps, about -20 LUFS, true peak -3 dB, long pauses trimmed.
   1-2 min is ideal; we only have 48 s of the owner. More clean speech (e.g. any other real recording) = a better clone:
   re-`prep` with all of it and re-`clone`.
2. **Model**: `eleven_multilingual_v2` for finals (most stable with IVC). `eleven_flash_v2_5` (`--draft`, half price)
   only for timing and pacing drafts. `eleven_v3` (audio tags like `[excited]`, `[pause]`) only as an A/B test: it's
   less stable with clones.
3. **Settings (v2)**: stability 0.40-0.55 (lower = livelier but riskier), similarity_boost 0.80-1.0, **style 0**
   (style > 0 adds instability), speaker_boost on, speed 0.95-1.05.
4. **Write for the ear**: short sentences; commas and "..." for breath; spell out tricky terms ("n8n" is read
   correctly as "N eight N"; check the align.json); no ALL CAPS unless you want emphasis.
5. **Stitching**: lines of one script are generated in order with `previous_request_ids` (max 3), so tone and pace stay
   consistent. Regenerate a single line → it still stitches to the earlier ones.
6. **Takes + objective gate**: 2 takes per line, then score with `jobs/voice-similarity` (Kaggle, about 1.5 min) and keep the
   take with the highest similarity. Bars: owner real-vs-real = 0.88; **ElevenLabs v1 clone = 0.51 (pitch 111.8 Hz vs
   owner 112.6, brightness 1515 vs 1498)**; Qwen 0.10; Chatterbox 0.01. The owner's ear is the final judge.

## Credit budget (2026-11-27)
- An accidental click in the ElevenLabs **web app** used about 27k credits. Balance after that: **about 11.4k until the about 27 Dec reset**.
- `say` checks the live balance and refuses any run that would leave **< 2,000 credits** (`RESERVE`).
- Default is **1 take per line**. Use a 2nd take only for a line that fails the similarity gate or the owner's ear.
- Remind the owner: avoid one-click generation features in the web app (video/dubbing/studio projects) while credits are low.

## Credit optimisation
- Cost ≈ characters × takes × (1.0 v2/v3 | 0.5 flash). One 40 s script ≈ 650 chars → 2 takes ≈ 1,300 credits.
  10 videos × 2 takes ≈ 13k credits: fits Starter (40k) with room for retakes.
- Always `--dry-run` first on new scripts; `--max-chars` guards each run (default 4,000).
- Cache key = voice + model + settings + text + seed: re-running a job only bills **changed** lines.
- Iterate wording on `--draft` (flash) and render finals once on v2.
- Failed requests are not billed.

## Don't
- Don't clone any voice except the owner's. Don't remove or misrepresent the AI origin if a platform requires disclosure.
- Don't paste the key anywhere; don't use `mp3_44100_192` (Creator only); don't loop on 429s. Back off instead.
