#!/usr/bin/env python3
"""Check the memory store for problems. Read-only.

Usage:
  doctor.py [--slug SLUG] [--stale-days N] [--tokens] [--check-ides]

Reports, per project:
  error  INDEX.md missing
  error  INDEX row points at a feature note that does not exist
  warn   feature note with no INDEX row
  warn   secret-like string in a note (token, private key, password=…)
  info   note not updated for N days (default 90)
  warn   note/INDEX/NOW over its size budget (what costs tokens every session)
  warn   note's key files were deleted, or commits touched them since the note's `@ <commit>`
--tokens     also print approx. tokens injected at session start per project, and the biggest notes
--check-ides report which IDE configs carry the hook/rule (presence only, not proof the IDE obeys it)
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
COMMIT_RE = re.compile(r"Updated:.*@\s*([0-9a-f]{7,40})")
KEY_FILES_RE = re.compile(r"(?im)^.*key files?\b.*$")
INDEX_MAX_ROWS, NOTE_MAX_BULLETS, NOTE_MAX_CHARS = 40, 8, 1800


def key_files(text: str) -> list[str]:
    m = KEY_FILES_RE.search(text)
    found = re.findall(r"`([^`\s]+)`", m.group(0)) if m else []
    return [f for f in found if "/" in f or "." in f]


def check_drift(path: str, note: str, text: str) -> list[tuple[str, str]]:
    root = c.read_origin(path).get("root", "")
    files = key_files(text)
    if not root or not os.path.isdir(root) or not files:
        return []
    out = []
    gone = [f for f in files if "*" not in f and not os.path.exists(os.path.join(root, f))]
    if gone:
        out.append(("warn", "features/%s.md: key files no longer exist: %s" % (note, ", ".join(gone))))
    m = COMMIT_RE.search(text)
    live = [f for f in files if f not in gone]
    if m and live:
        log = c.git(root, "log", "--oneline", "%s..HEAD" % m.group(1), "--", *live)
        if log:
            out.append(("warn", "features/%s.md: %d commit(s) touched its key files since %s; verify the note"
                        % (note, len(log.splitlines()), m.group(1))))
    return out


def check_project(path: str, stale_days: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    index = os.path.join(path, "INDEX.md")
    features = os.path.join(path, "features")
    notes = set()
    if os.path.isdir(features):
        notes = {f[:-3] for f in os.listdir(features) if f.endswith(".md") and not f.startswith("_")}
    indexed = set()
    archive = os.path.join(path, "ARCHIVE.md")
    for cells in (c.index_rows(c.read(archive)) if os.path.isfile(archive) else []):
        indexed.add((NOTE_REF_RE.findall(" ".join(cells)) or [cells[0].strip("` ")])[0])
    if not os.path.isfile(index):
        out.append(("error", "INDEX.md missing"))
    else:
        index_text = c.read(index)
        n_rows = len(c.index_rows(index_text))
        if n_rows > INDEX_MAX_ROWS or len(index_text) > c.INDEX_BUDGET_CHARS:
            out.append(("warn", "INDEX.md is over budget (%d rows, %d chars); run note.py --archive" % (n_rows, len(index_text))))
        for cells in c.index_rows(index_text):
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
        bullets = sum(1 for l in text.splitlines() if l.lstrip().startswith(("- ", "* ")))
        if bullets > NOTE_MAX_BULLETS or len(text) > NOTE_MAX_CHARS:
            out.append(("warn", "features/%s.md is over budget (%d bullets, %d chars); trim it" % (note, bullets, len(text))))
        out += check_drift(path, note, text)
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
    now = os.path.join(path, "NOW.md")
    if os.path.isfile(now) and len(c.read(now)) > c.NOW_BUDGET_CHARS:
        out.append(("warn", "NOW.md is over budget; keep it to a few lines"))
    return out


def token_report(root: str, slug: str, path: str) -> None:
    print("tokens %s: ~%d injected at session start" % (slug, c.approx_tokens(c.session_context(root, path))))
    feats = os.path.join(path, "features")
    names = [f for f in os.listdir(feats) if f.endswith(".md") and not f.startswith("_")] if os.path.isdir(feats) else []
    for n, f in sorted(((c.approx_tokens(c.read(os.path.join(feats, f))), f) for f in names), reverse=True)[:3]:
        print("         ~%d  features/%s" % (n, f))


def check_ides() -> None:
    home = os.path.expanduser("~")

    def has(path: str, needle: str) -> bool:
        try:
            return needle in c.read(os.path.join(home, path))
        except OSError:
            return False

    checks = [
        ("claude  rule", has(".claude/CLAUDE.md", c.BEGIN)),
        ("claude  SessionStart hook", has(".claude/settings.json", "ensure-project.py")),
        ("claude  Stop hook", has(".claude/settings.json", "stop-check.py")),
        ("cursor  rule", has(".cursor/rules/project-memory.mdc", "PROTOCOL.md") or has(".cursor/rules/shared-ai-memory.mdc", "PROTOCOL.md")),
        ("cursor  hooks", has(".cursor/hooks.json", "ensure-project.py")),
        ("cursor  stop hook", has(".cursor/hooks.json", "stop-check.py")),
        ("gemini  rule", has(".gemini/GEMINI.md", c.BEGIN)),
        ("codex   rule", has(".codex/AGENTS.md", c.BEGIN)),
    ]
    for label, ok in checks:
        print("%-4s %s" % ("ok" if ok else "miss", label))
    print("note Gemini/Antigravity/Codex have no hooks: confirm once per tool that a new chat quotes the protocol.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--slug", default="")
    p.add_argument("--stale-days", type=int, default=90)
    p.add_argument("--tokens", action="store_true")
    p.add_argument("--check-ides", action="store_true")
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
    if a.check_ides:
        check_ides()
    for slug in slugs:
        if a.tokens:
            token_report(root, slug, os.path.join(projects, slug))
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
