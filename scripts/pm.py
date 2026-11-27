#!/usr/bin/env python3
"""ChatGPT as project manager (owner 2026-11-27: save Claude tokens, use ChatGPT at max).

  python3 scripts/pm.py sync ["what just happened"]   # ChatGPT reads board + recent commits + HANDOFF, updates the board
  python3 scripts/pm.py brief                          # ChatGPT writes the next-actions / owner-questions brief, no changes
Add --dry to print the proposed board changes without applying them.
Claude (or any agent) only reports facts; the PM decides card moves/notes/new cards. Needs the Codex login (lane.chatgpt).
"""
import argparse, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lane import chatgpt  # noqa: E402
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("tracker", ROOT / "scripts" / "tracker.py")
tr = importlib.util.module_from_spec(spec); spec.loader.exec_module(tr)

ROLE = """You are the project manager of a video-production project (Upwork promo videos + Trip Memories films).
You never produce media; you keep the board accurate and tell the team what to do next.
Rules: the owner's hard rules are in HANDOFF (realism first, $0 by default, ask before anything that costs money, no cuts
away from the face while talking). A card is 'done' only when the work is finished AND verified. Anything only the owner can do
(upload files, set secrets, approve spend, choose between options) is needs_owner=true. Use list 'blocked' for cards that cannot
progress, 'doing' only for work actively underway. Do not invent facts: only use the board, commits and the event text below.
Return ONLY the JSON the schema asks for. ops: move/note/add card changes (id empty for add). next_actions: max 5, ordered,
concrete, each starting with the card id. owner_questions: only real decisions/uploads the owner must provide, max 4, one line each.
risks: max 3."""


def gather(event: str) -> str:
    log = subprocess.run(["git", "log", "-15", "--format=%h %ad %s", "--date=short"], cwd=ROOT, capture_output=True, text=True).stdout
    handoff = (ROOT / "HANDOFF.md").read_text()[:6000]
    board = json.dumps(tr.load(), ensure_ascii=False)
    return f"{ROLE}\n\n## Event reported\n{event or '(none, routine review)'}\n\n## Board (JSON)\n{board}\n\n## Recent commits\n{log}\n\n## HANDOFF.md (head)\n{handoff}"


def apply(ops):
    b = tr.load()
    for o in ops:
        try:
            if o["op"] == "add":
                pre = "D" if o["list"] == "done" else "T"
                nums = [int(c["id"][1:]) for c in b["cards"] if c["id"][0] == pre]
                b["cards"].append({"id": f"{pre}{max(nums, default=0) + 1:02d}", "title": o["title"], "list": o["list"] or "todo",
                                   "project": o["project"] or "infra", "needs_owner": o["needs_owner"],
                                   "blocked_by": o["blocked_by"], "notes": [o["text"]] if o["text"] else []})
            else:
                c = tr.card(b, o["id"])
                if o["op"] == "move" and o["list"] in b["lists"]:
                    c["notes"].append(f"PM: {c['list']} -> {o['list']}" + (f" ({o['text']})" if o["text"] else "")); c["list"] = o["list"]
                elif o["op"] == "note" and o["text"]:
                    c["notes"].append(f"PM: {o['text']}")
        except SystemExit:
            print(f"skipped op on unknown card {o.get('id')}", file=sys.stderr)
    tr.save(b)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["sync", "brief"]); p.add_argument("event", nargs="?", default="")
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    r = chatgpt.ask(gather(a.event), schema=str(ROOT / "prompts" / "pm_schema.json"))
    d = r["data"]
    if a.cmd == "sync" and not a.dry:
        apply(d["ops"])
    elif a.cmd == "sync":
        print(json.dumps(d["ops"], indent=1))
    print("NEXT:"); [print(" -", x) for x in d["next_actions"]]
    print("OWNER:"); [print(" -", x) for x in d["owner_questions"]]
    print("RISKS:"); [print(" -", x) for x in d["risks"]]
    print(f"({len(d['ops'])} board ops, {r['seconds']}s)")


if __name__ == "__main__":
    main()
