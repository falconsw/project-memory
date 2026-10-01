#!/usr/bin/env python3
"""Create a feature note and its INDEX row in one step.

Usage:
  note.py <topic> [--slug SLUG] [--status wip|done|blocked] [--summary TEXT] [--agent NAME]

- Creates `features/<topic>.md` from the template if it does not exist (never overwrites).
- Adds the INDEX row, or updates status/summary of the existing row for that topic.
- Prints the note path so the agent can edit it next.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aimem_common as c  # noqa: E402

STATUSES = ("wip", "done", "blocked")


def upsert_row(index_text: str, topic: str, status: str, summary: str) -> str:
    """Existing row keeps its summary unless a new one is given."""
    lines = index_text.splitlines()
    for i, line in enumerate(lines):
        cells = [x.strip() for x in line.strip().strip("|").split("|")] if line.strip().startswith("|") else []
        if cells and cells[0] == topic:
            kept = summary or (cells[2] if len(cells) > 2 else "")
            lines[i] = "| %s | %s | %s |" % (topic, status, kept.replace("|", "/"))
            return "\n".join(lines) + "\n"
    row = "| %s | %s | %s |" % (topic, status, (summary or "`features/%s.md`" % topic).replace("|", "/"))
    # Insert after the last table line so the row stays inside the table.
    last_table = max((i for i, l in enumerate(lines) if l.strip().startswith("|")), default=-1)
    if last_table < 0:
        lines += ["", "| Topic | Status | Note |", "| --- | --- | --- |", row]
    else:
        lines.insert(last_table + 1, row)
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("topic")
    p.add_argument("--slug", default="")
    p.add_argument("--status", default="wip", choices=STATUSES)
    p.add_argument("--summary", default="")
    p.add_argument("--agent", default=os.environ.get("AI_MEMORY_AGENT", "agent"))
    a = p.parse_args()

    if not c.TOPIC_RE.match(a.topic):
        sys.stderr.write("note: topic must be kebab-case (a-z, 0-9, -)\n")
        return 2
    root = c.store_root()
    slug = a.slug or c.slug_from_path(os.environ.get("AI_MEMORY_CWD") or os.getcwd())
    dest = c.ensure_project(root, slug)
    if not dest:
        sys.stderr.write("note: cannot create project %r under %s\n" % (slug, root))
        return 1

    note = os.path.join(dest, "features", a.topic + ".md")
    if not os.path.exists(note):
        tpl_path = os.path.join(c.project_template_dir(root), "features", "_TEMPLATE.md")
        tpl = c.read(tpl_path) if os.path.isfile(tpl_path) else "# {{TITLE}}\n\nUpdated: {{DATE}} — {{AGENT}}\n\n- \n"
        title = a.topic.replace("-", " ").capitalize()
        text = tpl.replace("{{TITLE}}", title).replace("{{DATE}}", c.today()).replace("{{AGENT}}", a.agent)
        c.write(note, text)

    index = os.path.join(dest, "INDEX.md")
    index_text = c.read(index) if os.path.isfile(index) else "# Project index\n\nSlug: `%s`\n" % slug
    c.write(index, upsert_row(index_text, a.topic, a.status, a.summary))
    print(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
