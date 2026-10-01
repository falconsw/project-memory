#!/usr/bin/env python3
"""Stop hook: if code changed during this session but NOW.md was not refreshed, ask the agent once to do it.

Usage: stop-check.py --claude | --cursor   (hook JSON on stdin)

Silent when: nothing changed since the session started, NOW.md is newer than every change,
the session-start stamp is missing, or this is already the follow-up turn (no loops).
Always exits 0.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aimem_common as c  # noqa: E402


def changed_mtimes(cwd: str) -> list[float]:
    top = c.git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return []
    out = []
    for line in c.git(top, "status", "--porcelain", strip=False).splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        try:
            out.append(os.path.getmtime(os.path.join(top, path)))
        except OSError:
            continue
    return out


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--claude"
    reply = ""
    try:
        data = c.parse_hook_json(sys.stdin.read() if not sys.stdin.isatty() else "")
        again = data.get("stop_hook_active") or int(data.get("loop_count") or 0) > 0
        cwd = c.parse_hook_cwd(json.dumps(data)) or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        store = c.store_root()
        slug, origin = c.resolve_slug(store, cwd)
        dest = c.project_dir(store, slug)
        stamp = os.path.join(dest, ".session-start")
        if not again and os.path.isfile(stamp):
            now = os.path.join(dest, "NOW.md")
            floor = max(os.path.getmtime(stamp), os.path.getmtime(now) if os.path.isfile(now) else 0)
            # Either files were edited after the last handoff, or a commit landed after it
            # (NOW would still say "uncommitted").
            committed = c.git(cwd, "log", "-1", "--format=%ct")
            if any(m > floor for m in changed_mtimes(cwd)) or (committed.isdigit() and float(committed) > floor):
                reply = (
                    "Memory handoff missing: run `%s --now --task \"...\" --state \"...\" --next \"...\" --files a,b` "
                    "(and `note.py <topic> --summary ...` if a feature changed), then stop. Keep it to a few lines."
                    % os.path.join(store, "bin", "note.py")
                )
    except Exception:  # a hook must never break the IDE
        reply = ""
    who = "cursor" if mode == "--cursor" else "claude"
    try:
        c.mark_seen(c.store_root(), who + "/stop-reminded" if reply else who + "/stop")
    except Exception:
        pass
    if mode == "--cursor":
        out = {"followup_message": reply} if reply else {}
    else:
        out = {"decision": "block", "reason": reply} if reply else {}
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
