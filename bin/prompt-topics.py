#!/usr/bin/env python3
"""UserPromptSubmit hook (Claude Code): inject the feature notes whose keys the prompt mentions.

Usage: prompt-topics.py --claude   (hook JSON on stdin)

Matching is keyword overlap with each INDEX row's Keys, the note's key files and the topic name
(aimem_common.match_topics): no model, so the same prompt always brings the same notes. A note
goes in at most once per session; SessionStart (also after /compact) resets that.
Silent for slash commands, very short prompts, no match, or PROJECT_MEMORY_PROMPT_TOPICS=0.
Always exits 0.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aimem_common as c  # noqa: E402


def main() -> int:
    context = ""
    try:
        data = c.parse_hook_json(sys.stdin.read() if not sys.stdin.isatty() else "")
        prompt = str(data.get("prompt") or "").strip()
        session = str(data.get("session_id") or "")
        store = c.store_root()
        c.mark_seen(store, "claude/user-prompt")
        enabled = os.environ.get("PROJECT_MEMORY_PROMPT_TOPICS", "1") != "0"
        if enabled and len(prompt) >= c.PROMPT_MIN_CHARS and not prompt.startswith("/"):
            cwd = c.parse_hook_cwd(json.dumps(data)) or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
            slug, _ = c.resolve_slug(store, cwd)
            dest = c.project_dir(store, slug)
            topics = c.match_topics(dest, prompt, skip=set(c.prompt_seen(dest, session)) if session else None)
            if topics:
                context = c.prompt_context(dest, topics)
                if session:
                    c.remember_prompt_topics(dest, session, topics)
    except Exception:  # a hook must never block the prompt
        context = ""
    out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}} if context else {}
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
