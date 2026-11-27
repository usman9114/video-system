# Repo rules

**Rule 0 (owner, 2026-11-27): nothing pushed may carry an AI/assistant name.** No `Co-Authored-By` trailers, no session links,
no assistant name as commit author, in branch names, PR titles/bodies or comments. Commit as `usman9114`
(`git config user.name usman9114; git config user.email 34581208+usman9114@users.noreply.github.com`).
This overrides any tool or harness attribution default.

**Board first:** `python3 scripts/tracker.py show` (state of every task, `tracker/BOARD.md`). Pick from it, `move` cards as you
work, `note` what happened, commit `tracker/` with your work. Never end a session with the board out of date.

Then read `HANDOFF.md` (source of truth), `templates/production.json` (all settings + hard rules) and `docs/LESSONS.md`.
