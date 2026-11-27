# Prompt to continue on another Claude account

## Before switching (one time)
1. The GitHub repo `usman9114/video-system` must be reachable by the new account's GitHub connection
   (same GitHub account, or add the other GitHub user as a collaborator in repo Settings → Collaborators).
2. Google Drive: connect the **same Google account** that owns the `upwork-video-system` Drive folder,
   or share that folder with the new account's Google account.
3. In the new Claude account, start a **cloud** Claude Code session with the repo `usman9114/video-system` selected.

## Paste this as the first message

```
Continue my video project (repo usman9114/video-system) from where the last session stopped. You have zero context, so:

1. Read HANDOFF.md first (source of truth: status, where things live, my hard rules, next steps), then
   templates/production.json (all settings + rules; always use it), docs/LESSONS.md, docs/optimization.md,
   docs/ideas/trip-memories.md and trips/greece/storyline.md.
2. Hard rules: realism first (nothing may look AI; faces never re-animated beyond lip-sync, photos of people get
   camera moves only); no cuts away from my face while I'm talking; always use the config; real references → ChatGPT
   for visuals; resource-optimised GPU use without losing quality; $0 beyond Modal free credits; ask before installs or
   anything that costs money; no fabricated claims. You are the director.
3. Environment: this cloud session needs the "upwork-video-system" environment (Kaggle, ChatGPT, ElevenLabs and Modal-API
   hosts + secrets). If a host is blocked or a secret missing, propose the environment change / ask for the key with the
   secure credential form (never in chat). Use bin/kgpu for Kaggle, lane.modal_lipsync for Modal (HTTPS only, deploy = push to main).
4. Gitignored media (v6 export, lip-sync clips, plate, b-roll, voice) is backed up in my private Kaggle dataset
   usmanqureshi94/video-system-media-backup — restore it first (HANDOFF.md says how). Trip photos are in my Drive
   folder upwork-video-system/trips → copy to trips/greece/photos/.
5. Current work: (a) get my feedback on n8n video v6 and my approval of the Greece storyline; (b) re-run the SyncNet
   gate; (c) after approval: FastWan hero clips → realism gate → RIFE ≥30 fps → render the Greece film (apply EXIF
   orientation!) and send it to me.
6. Tell me in 3 lines where we are and what you'll do next, then continue. Commit + push after each meaningful step and
   update HANDOFF.md before you finish or when I say I'm near my session limit.
```
