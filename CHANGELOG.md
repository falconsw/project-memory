# Changelog

## 0.1.0 - unreleased

First release on PyPI as `ai-project-memory`.

- Install with `uvx ai-project-memory install` (or `pipx install ai-project-memory`); cloning the repo still works. Hooks keep running from the store copies, so the package can be upgraded or removed without breaking an IDE.
- Claude Code `UserPromptSubmit` hook (`prompt-topics.py`): when a prompt mentions a topic's keys, one of its key files or its name, that feature note is injected before the first turn, at most two notes, once per session. `PROJECT_MEMORY_PROMPT_TOPICS=0` turns it off.
- `project-memory --version`.
- The installer no longer replaces a `~/.local/bin/project-memory` link made by pipx or `uv tool`.
