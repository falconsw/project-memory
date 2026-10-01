#!/usr/bin/env python3
"""Create `<store>/projects/<slug>/` from the template if missing. Never overwrites.

Usage:
  ensure-project.py [slug]          # slug defaults to the current folder name
  ensure-project.py --hook-cursor   # Cursor hook: reads JSON on stdin, prints Cursor hook JSON
  ensure-project.py --hook-claude   # Claude Code SessionStart hook: prints additionalContext JSON
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aimem_common as c  # noqa: E402

HOOK_MODES = ("--hook-cursor", "--hook-claude")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in HOOK_MODES else ""
    raw = ""
    if mode and not sys.stdin.isatty():
        raw = sys.stdin.read()
    slug = sys.argv[1] if len(sys.argv) > 1 and not mode else ""
    cwd = c.parse_hook_cwd(raw) or os.environ.get("AI_MEMORY_CWD") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if not slug:
        slug = c.slug_from_path(cwd)

    root = c.store_root()
    try:
        dest = c.ensure_project(root, slug)
    except OSError:
        dest = ""

    index = os.path.join(dest, "INDEX.md") if dest else ""
    context = (
        "Shared AI memory for this workspace: %s — read it before exploring code; "
        "protocol: %s" % (index, os.path.join(root, "PROTOCOL.md"))
        if dest else ""
    )

    # Hooks must never block the IDE, so they always exit 0.
    if mode == "--hook-cursor":
        sys.stdout.write(json.dumps({"continue": True, "additional_context": context}) + "\n")
        return 0
    if mode == "--hook-claude":
        out = {}
        if context:
            out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
        sys.stdout.write(json.dumps(out) + "\n")
        return 0
    if dest:
        print(dest)
        return 0
    sys.stderr.write("ensure-project: invalid slug or missing template (%r)\n" % slug)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
