#!/usr/bin/env python3
"""Project board CLI. Source of truth: tracker/board.json. Every change re-renders tracker/BOARD.md.

  python3 scripts/tracker.py show [--list todo]       # print the board
  python3 scripts/tracker.py add "title" --project greece [--list todo] [--owner] [--note "..."] [--blocked-by T01]
  python3 scripts/tracker.py move T02 doing            # lists: blocked todo doing review done
  python3 scripts/tracker.py note T02 "what happened"  # dated note
  python3 scripts/tracker.py render                    # rewrite BOARD.md only
Commit tracker/ with your work, then re-publish tracker/board.html to the board artifact (URL in tracker/board.json -> artifact_url).
"""
import argparse, datetime, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOARD = ROOT / "tracker" / "board.json"
MD = ROOT / "tracker" / "BOARD.md"
HTML = ROOT / "tracker" / "board.html"  # published as the board artifact; built from board_template.html
TITLES = {"blocked": "Blocked", "todo": "To do", "doing": "In progress", "review": "Waiting on owner review", "done": "Done"}


def load():
    return json.loads(BOARD.read_text())


def save(b):
    b["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    BOARD.write_text(json.dumps(b, indent=2, ensure_ascii=False) + "\n")
    render(b)


def card(b, cid):
    for c in b["cards"]:
        if c["id"] == cid.upper():
            return c
    sys.exit(f"no card {cid}")


def render(b):
    out = ["# Project board", "", f"_Generated from `tracker/board.json` by `scripts/tracker.py`. Updated {b.get('updated', '?')}._", "",
           b["about"], ""]
    for lst in b["lists"]:
        cs = [c for c in b["cards"] if c["list"] == lst]
        out += [f"## {TITLES.get(lst, lst)} ({len(cs)})", ""]
        for c in cs:
            tags = [c.get("project", "")] + (["needs owner"] if c.get("needs_owner") else []) + \
                   ([f"after {', '.join(c['blocked_by'])}"] if c.get("blocked_by") else [])
            out.append(f"- **{c['id']}** {c['title']}  _({' · '.join(t for t in tags if t)})_")
            out += [f"  - {n}" for n in c.get("notes", [])]
        out.append("")
    MD.write_text("\n".join(out))
    data = json.dumps(b, ensure_ascii=False).replace("</", "<\\/")
    HTML.write_text((ROOT / "tracker" / "board_template.html").read_text().replace("__BOARD_JSON__", data))


def main():
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    sh = s.add_parser("show"); sh.add_argument("--list")
    a = s.add_parser("add"); a.add_argument("title"); a.add_argument("--project", required=True)
    a.add_argument("--list", default="todo"); a.add_argument("--owner", action="store_true")
    a.add_argument("--note", action="append", default=[]); a.add_argument("--blocked-by", action="append", default=[])
    m = s.add_parser("move"); m.add_argument("id"); m.add_argument("list")
    n = s.add_parser("note"); n.add_argument("id"); n.add_argument("text")
    s.add_parser("render")
    args = p.parse_args()
    b = load()
    today = datetime.date.today().isoformat()
    if args.cmd == "show":
        for lst in b["lists"]:
            if args.list and lst != args.list:
                continue
            print(f"== {TITLES[lst]}")
            for c in (c for c in b["cards"] if c["list"] == lst):
                print(f"  {c['id']:4} [{c.get('project','')}]{' *owner*' if c.get('needs_owner') else ''} {c['title']}")
        return
    if args.cmd == "add":
        if args.list not in b["lists"]:
            sys.exit(f"list must be one of {b['lists']}")
        pre = "D" if args.list == "done" else "T"
        nums = [int(c["id"][1:]) for c in b["cards"] if c["id"][0] == pre]
        cid = f"{pre}{max(nums, default=0) + 1:02d}"
        b["cards"].append({"id": cid, "title": args.title, "list": args.list, "project": args.project,
                           "needs_owner": args.owner, "blocked_by": args.blocked_by,
                           "notes": [f"{today}: {x}" for x in args.note]})
        print(cid)
    elif args.cmd == "move":
        if args.list not in b["lists"]:
            sys.exit(f"list must be one of {b['lists']}")
        c = card(b, args.id); c["notes"].append(f"{today}: {c['list']} -> {args.list}"); c["list"] = args.list
    elif args.cmd == "note":
        card(b, args.id)["notes"].append(f"{today}: {args.text}")
    save(b)


if __name__ == "__main__":
    main()
