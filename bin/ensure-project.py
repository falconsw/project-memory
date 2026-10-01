#!/usr/bin/env python3
"""Create `<store>/projects/<slug>/` from the template if missing. Never overwrites.

Usage:
  ensure-project.py [slug]          # slug defaults to the current repo's (see resolve_slug); prints the project dir
  ensure-project.py --hook-cursor   # Cursor hook: reads JSON on stdin, prints Cursor hook JSON
  ensure-project.py --hook-claude   # Claude Code SessionStart hook: prints additionalContext JSON

Hooks inject NOW.md + INDEX.md as context so the agent starts with zero tool calls.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aimem_common as c  # noqa: E402

HOOK_MODES = ("--hook-cursor", "--hook-claude")
STAMP = ".session-start"


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in HOOK_MODES else ""
    raw = ""
    if mode and not sys.stdin.isatty():
        raw = sys.stdin.read()
    hook = c.parse_hook_json(raw)
    arg_slug = sys.argv[1] if len(sys.argv) > 1 and not mode else ""
    cwd = c.parse_hook_cwd(raw) or os.environ.get("AI_MEMORY_CWD") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    root = c.store_root()
    try:
        if arg_slug:
            dest = c.ensure_project(root, arg_slug)
        else:
            slug, origin = c.resolve_slug(root, cwd)
            dest = c.ensure_project(root, slug, origin)
    except OSError:
        dest = ""

    context = ""
    if mode and dest:
        try:
            # The Stop hook only nags about edits made after the session began.
            event = str(hook.get("hook_event_name", ""))
            if mode == "--hook-claude" or event.lower() == "sessionstart":
                c.write(os.path.join(dest, STAMP), c.today() + "\n")
            context = c.session_context(root, dest)
        except OSError:
            context = ""

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
    sys.stderr.write("ensure-project: invalid slug or missing template\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
