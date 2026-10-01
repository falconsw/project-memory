# project-memory protocol

The store lives at `$PROJECT_MEMORY_HOME` (default `~/ai-memory`; `$AI_MEMORY_HOME` is also honoured). It is local, plain Markdown, and not tied to any IDE or git repo. Every agent (Claude Code, Cursor, Antigravity/Gemini, Codex, …) reads and writes the same files.

**Default: ON in every conversation.** Agents apply this protocol on the first turn without waiting for the user to mention memory, handoff, or the store.

Markdown files are the source of truth. An optional MCP server may help search, but it is never a second memory.

## Project slug

The main repo's folder name (worktrees and subfolders resolve to it): `/Users/me/code/foo` → `foo`.
If a different repo already owns that name, the slug becomes `foo-<6-hex>` (identity = git remote URL, else path; recorded in `projects/<slug>/.origin`).
Agents never compute the slug: `bin/ensure-project.sh` prints the project dir.

- Project dir: `$PROJECT_MEMORY_HOME/projects/<slug>/`
- `NOW.md`: where the last session stopped (task / state / next / files / open). Overwritten each time.
- `INDEX.md`: one row per topic (Topic, Status, Note, Keys). `ARCHIVE.md`: old `done` rows, never loaded at start.
- `features/<topic>.md`: 3–8 bullet notes.

If the project dir is missing, create it automatically. No approval, no pause, no user action:

- IDE hooks run `bin/ensure-project.py` at session start; it creates the dir and injects NOW + INDEX as context (zero tool calls).
- Without hooks (Gemini, Antigravity, Codex) the agent runs `bin/ensure-project.sh` and reads `NOW.md` + `INDEX.md`.
- Never ask the user to copy `_template`. Never write into `_template/`.

## Read (every conversation, before exploring code)

1. If NOW/INDEX are already in context, do not re-read them. Skim `USER.md` only when cross-project preferences matter.
2. Continue from NOW. If the task matches an INDEX row (topic, summary or keys), read only that `features/<topic>.md`.
3. If the note is enough, do **not** run `git log`, `git status`, `git grep`, or broad code search. Open only the files the note lists.
4. Use git and search only when INDEX has no matching topic.
5. If the note and the code disagree, trust the code and fix the note.

## Write (after meaningful work, unprompted)

1. `bin/note.py --now --task ... --state ... --next ... --files ...` (or `--now --done`). A Stop hook asks once if code changed and NOW was not refreshed.
2. If a feature changed or a decision/pitfall appeared: `bin/note.py <topic> --status ... --summary ... --keys ...`, then edit `features/<topic>.md` (3–8 bullets). `note.py` stamps `Updated: date — agent @ commit` and keeps exactly one INDEX row.
3. Housekeeping: `bin/note.py --archive` moves `done` rows older than 30 days out of INDEX; `bin/doctor.py` flags oversize files, dead key files and notes whose files changed since their commit.

Do **not** dump chat transcripts. The goal is fewer tokens next session, not a diary. Budgets: INDEX ≤ 40 rows / 3500 chars, note ≤ 8 bullets / 1800 chars, NOW ≤ 1500 chars.

## Never store

- Secrets, tokens, passwords, `.env` values, private keys, credentials.
- Personal data about third parties.
- Anything the repo already records better (full code, git history).

`bin/doctor.py` flags secret-like strings and broken index rows.

## Filenames

Kebab-case topic names, one topic per file: `auth.md`, `billing-webhooks.md`.

## Status values

`done` / `wip` / `blocked`
