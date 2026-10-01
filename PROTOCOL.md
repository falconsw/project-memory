# project-memory protocol

The store lives at `$PROJECT_MEMORY_HOME` (default `~/ai-memory`; `$AI_MEMORY_HOME` is also honoured). It is local, plain Markdown, and not tied to any IDE or git repo. Every agent (Claude Code, Cursor, Antigravity/Gemini, Codex, …) reads and writes the same files.

**Default: ON in every conversation.** Agents apply this protocol on the first turn without waiting for the user to mention memory, handoff, or the store.

Markdown files are the source of truth. An optional MCP server may help search, but it is never a second memory.

## Project slug

The workspace folder name (last path segment): `/Users/me/code/foo` → `foo`.

- Project dir: `$PROJECT_MEMORY_HOME/projects/<slug>/`
- Index: `$PROJECT_MEMORY_HOME/projects/<slug>/INDEX.md`
- Feature notes: `$PROJECT_MEMORY_HOME/projects/<slug>/features/<topic>.md`

If the project dir is missing, create it automatically. No approval, no pause, no user action:

- IDE hooks run `bin/ensure-project.py` at session or prompt start.
- If the folder is still missing, the agent runs `$PROJECT_MEMORY_HOME/bin/ensure-project.sh` itself and continues.
- Never ask the user to copy `_template`. Never write into `_template/`.

## Read (every conversation, before exploring code)

For questions like "what did I do last", "how does this feature work", the first tool is **not** git.

1. Skim `USER.md` only when cross-project preferences matter.
2. Read `INDEX.md` for this slug.
3. If the task matches a row, read only that `features/<topic>.md`.
4. If the note is enough, do **not** run `git log`, `git status`, `git grep`, or broad code search. Open only the files the note lists.
5. Use git and search only when `INDEX.md` has no matching topic.
6. If the note and the code disagree, trust the code and fix the note.

## Write (after meaningful work, unprompted)

Update memory when you add or change a feature, make an architectural decision, hit a non-obvious pitfall, or leave work half-done.

1. Create or update `features/<topic>.md` from the template. Keep it short: 3–8 bullets.
2. Add or refresh exactly one row for that topic in `INDEX.md`.
3. Record the `Updated` date (absolute, `YYYY-MM-DD`) and which IDE/agent wrote it.

`bin/note.py <topic>` does steps 1–2 for you when the topic is new.

Do **not** dump chat transcripts. The goal is fewer tokens next session, not a diary.

## Never store

- Secrets, tokens, passwords, `.env` values, private keys, credentials.
- Personal data about third parties.
- Anything the repo already records better (full code, git history).

`bin/doctor.py` flags secret-like strings and broken index rows.

## Filenames

Kebab-case topic names, one topic per file: `auth.md`, `billing-webhooks.md`.

## Status values

`done` / `wip` / `blocked`
