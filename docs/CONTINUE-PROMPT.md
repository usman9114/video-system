# Prompt to continue on another Claude account

## Before switching (one time)
1. The GitHub repo `usman9114/video-system` must be reachable by the new account's GitHub connection
   (same GitHub account, or add the other GitHub user as a collaborator in repo Settings → Collaborators).
2. Google Drive: connect the **same Google account** that owns the `upwork-video-system` Drive folder,
   or share that folder with the new account's Google account.
3. In the new Claude account, start a **cloud** Claude Code session with the repo `usman9114/video-system` selected.

## Paste this as the first message

```
Continue my Upwork video repurposing project from where the last session stopped.

1. Read HANDOFF.md first, then docs/BRIEF.md, reports/, and docs/ as needed. Treat HANDOFF.md
   as the source of truth for decisions, status and what is waiting on me.
2. This is a new Claude account, so cloud environments and secrets don't carry over. If this session
   can't reach api.kaggle.com, propose a personal environment named "upwork-video-system"
   allowing api.kaggle.com, www.kaggle.com, storage.googleapis.com (see docs/kaggle-gpu-setup.md),
   and ask me for the Kaggle token via the secure credential form when the GPU is needed.
3. Video files live in my Google Drive folder "upwork-video-system" (source, broll, assets,
   previews, exports). Download what you need; never modify the original source video.
4. Follow all rules in the brief: $0 default, ask before installing anything, spending money,
   or sending my face/footage to a third-party service; no fabricated credentials.
5. Briefly tell me the current phase and the next 1-3 actions, then continue.
6. Commit and push to git after each meaningful step, and update HANDOFF.md before you finish
   or if I say I'm near my session limit.
```
