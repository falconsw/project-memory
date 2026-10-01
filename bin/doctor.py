#!/usr/bin/env python3
"""Check the memory store for problems. Read-only.

Usage:
  doctor.py [--slug SLUG] [--stale-days N]

Reports, per project:
  error  INDEX.md missing
  error  INDEX row points at a feature note that does not exist
  warn   feature note with no INDEX row
  warn   secret-like string in a note (token, private key, password=…)
  info   note not updated for N days (default 90)
Exit code 1 when any error is found.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aimem_common as c  # noqa: E402

SECRET_PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("OpenAI/Anthropic-style key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("assignment", re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"]?[^\s'\"`]{8,}")),
]
UPDATED_RE = re.compile(r"Updated:?\**\s*:?\s*(\d{4}-\d{2}-\d{2})")
NOTE_REF_RE = re.compile(r"features/([a-z0-9][a-z0-9-]*)\.md")


def check_project(path: str, stale_days: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    index = os.path.join(path, "INDEX.md")
    features = os.path.join(path, "features")
    notes = set()
    if os.path.isdir(features):
        notes = {f[:-3] for f in os.listdir(features) if f.endswith(".md") and not f.startswith("_")}
    if not os.path.isfile(index):
        out.append(("error", "INDEX.md missing"))
        indexed = set()
    else:
        indexed = set()
        for cells in c.index_rows(c.read(index)):
            topic = cells[0].strip("` ")
            refs = NOTE_REF_RE.findall(" ".join(cells))
            target = refs[0] if refs else topic
            indexed.add(target)
            if target not in notes:
                out.append(("error", "INDEX row %r has no features/%s.md" % (topic, target)))
    for note in sorted(notes - indexed):
        out.append(("warn", "features/%s.md has no INDEX row" % note))

    today = dt.date.today()
    for note in sorted(notes):
        text = c.read(os.path.join(features, note + ".md"))
        for label, rx in SECRET_PATTERNS:
            if rx.search(text):
                out.append(("warn", "features/%s.md: possible %s" % (note, label)))
        m = UPDATED_RE.search(text)
        if m:
            try:
                age = (today - dt.date.fromisoformat(m.group(1))).days
            except ValueError:
                age = -1
            if age > stale_days:
                out.append(("info", "features/%s.md last updated %d days ago" % (note, age)))
        else:
            out.append(("info", "features/%s.md has no 'Updated: YYYY-MM-DD' line" % note))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--slug", default="")
    p.add_argument("--stale-days", type=int, default=90)
    a = p.parse_args()

    root = c.store_root()
    projects = os.path.join(root, "projects")
    if not os.path.isdir(projects):
        print("error: no store at %s (run install.py)" % root)
        return 1
    for name in ("PROTOCOL.md", os.path.join("bin", "ensure-project.py"), os.path.join("projects", "_template", "INDEX.md")):
        if not os.path.exists(os.path.join(root, name)):
            print("warn: store is missing %s (re-run install.py)" % name)

    slugs = [a.slug] if a.slug else sorted(
        d for d in os.listdir(projects) if os.path.isdir(os.path.join(projects, d)) and d not in c.RESERVED_SLUGS
    )
    errors = 0
    for slug in slugs:
        findings = check_project(os.path.join(projects, slug), a.stale_days)
        if not findings:
            print("ok     %s" % slug)
            continue
        for level, msg in findings:
            errors += level == "error"
            print("%-6s %s: %s" % (level, slug, msg))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
