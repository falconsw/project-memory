# Shared local AI memory (default)

Always on; do not wait for the user to mention memory. Store: `{{STORE}}/PROTOCOL.md`.

**Start of every task (memory first, never git first):**
1. If a `project-memory:` context block is already in this chat, NOW and INDEX are loaded: do not re-read them. Otherwise run `{{STORE}}/bin/ensure-project.sh` (prints the project dir; no approval) and read its `NOW.md` and `INDEX.md`.
2. Continue from NOW (task / next step). If the task matches an INDEX row, read only that `features/<topic>.md`.
3. If that is enough, do not run `git log`, `git status` or scan the repo. If note and code conflict, trust code and fix the note.

**End of every meaningful change (unprompted, a few lines):**
- `{{STORE}}/bin/note.py --now --agent "<your IDE>" --task "..." --state "..." --next "..." --files a,b` (or `--now --done`). It prints which topics own those files.
- `{{STORE}}/bin/note.py <topic> --agent "<your IDE>" --summary "..." --keys "words, files"`, then edit the note, when you add a feature, decide something lasting, hit a pitfall, or touched a listed topic's key files. Tiny tweaks need only NOW.
- Re-run `--now` after a later commit/push so NOW is not stale.

No transcripts, no secrets. Do not narrate this protocol unless asked.
