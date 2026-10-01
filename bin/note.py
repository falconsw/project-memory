#!/usr/bin/env python3
"""Create/refresh a feature note + INDEX row, write the NOW handoff, or archive old rows.

Usage:
  note.py <topic> [--status wip|done|blocked] [--summary TEXT] [--keys "words, files"] [--agent NAME]
  note.py --now --task TEXT [--state TEXT] [--next TEXT] [--files a,b] [--open TEXT] [--agent NAME]
  note.py --archive [--days 30]
Common: [--slug SLUG]

- <topic>: creates `features/<topic>.md` if missing (never overwrites content), refreshes its
  `Updated:` stamp (date, agent, git commit), and adds/updates the INDEX row.
- --now: rewrites NOW.md (the "where I stopped" handoff read first by the next agent/IDE).
  Pass `--now --done` when nothing is in progress.
- --archive: moves `done` INDEX rows not updated for N days into ARCHIVE.md (notes stay on disk).
- Prints the file it wrote.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aimem_common as c  # noqa: E402

STATUSES = ("wip", "done", "blocked")
UPDATED_LINE = re.compile(r"^Updated:.*$", re.M)
UPDATED_DATE = re.compile(r"Updated:?\**\s*:?\s*(\d{4}-\d{2}-\d{2})")


def stamp(agent: str, cwd: str) -> str:
    commit = c.git(cwd, "rev-parse", "--short", "HEAD")
    return "Updated: %s — %s%s" % (c.today(), agent, " @ " + commit if commit else "")


def upsert_row(index_text: str, topic: str, status: str, summary: str, keys: str) -> str:
    """Existing row keeps its summary/keys unless new ones are given. Also upgrades old 3-column tables."""
    pre, rows, post = c.split_index(index_text)
    for r in rows:
        if r[0] == topic:
            r[1], r[2], r[3] = status, summary or r[2], keys or r[3]
            break
    else:
        rows.append([topic, status, summary or "`features/%s.md`" % topic, keys])
    if not pre:
        pre = ["# Project index", ""]
    return c.render_index(pre, rows, post)


def write_topic(a, dest: str, cwd: str) -> str:
    note = os.path.join(dest, "features", a.topic + ".md")
    if not os.path.exists(note):
        tpl_path = os.path.join(c.project_template_dir(c.store_root()), "features", "_TEMPLATE.md")
        tpl = c.read(tpl_path) if os.path.isfile(tpl_path) else "# {{TITLE}}\n\nUpdated: {{DATE}} — {{AGENT}}\n\n- \n"
        text = tpl.replace("{{TITLE}}", a.topic.replace("-", " ").capitalize())
        text = text.replace("{{DATE}}", c.today()).replace("{{AGENT}}", a.agent)
        c.write(note, text)
    text = c.read(note)
    line = stamp(a.agent, cwd)
    text = UPDATED_LINE.sub(lambda _: line, text, count=1) if UPDATED_LINE.search(text) else text.replace("\n", "\n\n" + line, 1)
    c.write(note, text)

    index = os.path.join(dest, "INDEX.md")
    with c.lock(index):
        text = c.read(index) if os.path.isfile(index) else "# Project index\n\nSlug: `%s`\n" % os.path.basename(dest)
        c.write(index, upsert_row(text, a.topic, a.status, a.summary, a.keys))
    return note


def write_now(a, dest: str, cwd: str) -> str:
    path = os.path.join(dest, "NOW.md")
    if a.done:
        c.write(path, "# Now\n\n(nothing in progress)\n")
        return path
    if not a.task:
        sys.stderr.write("note: --now needs --task (or --done)\n")
        raise SystemExit(2)
    fields = (("Task", a.task), ("State", a.state), ("Next", a.next), ("Files", a.files), ("Open", a.open))
    body = "\n".join("- %s: %s" % (k, v.strip()) for k, v in fields if v)
    c.write(path, "# Now\n\n%s\n\n%s\n" % (stamp(a.agent, cwd), body))
    return path


def archive(dest: str, days: int) -> int:
    index = os.path.join(dest, "INDEX.md")
    if not os.path.isfile(index):
        return 0
    cutoff = dt.date.today() - dt.timedelta(days=days)
    moved: list[list[str]] = []
    with c.lock(index):
        pre, rows, post = c.split_index(c.read(index))
        keep = []
        for r in rows:
            note = os.path.join(dest, "features", r[0].strip("` ") + ".md")
            m = UPDATED_DATE.search(c.read(note)) if os.path.isfile(note) else None
            old = bool(m) and dt.date.fromisoformat(m.group(1)) < cutoff
            (moved if r[1] == "done" and old else keep).append(r)
        if moved:
            arch = os.path.join(dest, "ARCHIVE.md")
            apre, arows, apost = c.split_index(c.read(arch)) if os.path.isfile(arch) else (["# Archived topics (not loaded at session start)"], [], [])
            c.write(arch, c.render_index(apre, arows + moved, apost))
            c.write(index, c.render_index(pre, keep, post))
    return len(moved)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("topic", nargs="?", default="")
    p.add_argument("--slug", default="")
    p.add_argument("--status", default="wip", choices=STATUSES)
    p.add_argument("--summary", default="")
    p.add_argument("--keys", default="")
    p.add_argument("--agent", default=os.environ.get("AI_MEMORY_AGENT", "agent"))
    p.add_argument("--now", action="store_true")
    p.add_argument("--done", action="store_true")
    for f in ("task", "state", "next", "files", "open"):
        p.add_argument("--" + f, default="")
    p.add_argument("--archive", action="store_true")
    p.add_argument("--days", type=int, default=30)
    a = p.parse_args()

    root = c.store_root()
    cwd = os.environ.get("AI_MEMORY_CWD") or os.getcwd()
    origin = None
    if a.slug:
        slug = a.slug
    else:
        slug, origin = c.resolve_slug(root, cwd)
    dest = c.ensure_project(root, slug, origin)
    if not dest:
        sys.stderr.write("note: cannot create project %r under %s\n" % (slug, root))
        return 1

    if a.archive:
        print("archived %d row(s)" % archive(dest, a.days))
        return 0
    if a.now:
        print(write_now(a, dest, cwd))
        return 0
    if not a.topic:
        p.error("give a topic, --now, or --archive")
    if not c.TOPIC_RE.match(a.topic):
        sys.stderr.write("note: topic must be kebab-case (a-z, 0-9, -)\n")
        return 2
    print(write_topic(a, dest, cwd))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
