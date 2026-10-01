---
name: project-memory
description: Default in every chat. Reads and writes the shared project-memory store ({{STORE}}) for the current workspace folder so work persists across IDEs and agents without re-exploring. Apply at conversation start before searching code, and after meaningful changes, without waiting for the user to mention memory, handoff, or notes.
---

# project-memory

Follow `{{STORE}}/PROTOCOL.md` in **every** conversation. Do not wait to be asked.

## Slug

Workspace folder basename → `{{STORE}}/projects/<slug>/`.

If that directory does not exist, run `{{STORE}}/bin/ensure-project.sh` immediately. Do not ask. Do not edit `_template`.

## Before exploring code (every task)

1. Read `INDEX.md`.
2. Read the matching `features/*.md`, if any.
3. Skip `git log`, `git status`, and broad codebase search when the note lists the files and current state.
4. If note and code conflict, trust code and update the note.

## After meaningful work (unprompted)

Update `features/<topic>.md` (short) and one `INDEX.md` row. For a new topic:

```sh
{{STORE}}/bin/note.py <topic> --status wip --summary "one line" --agent "<your IDE>"
```

No chat dumps. No secrets.
