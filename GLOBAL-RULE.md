# Shared local AI memory (default)

This protocol is **on by default in every conversation**. Do not wait for the user to mention memory.

Store: `{{STORE}}/PROTOCOL.md`. Project folder: `{{STORE}}/projects/<workspace-folder-name>/`.

**Start of every task — first tools are memory files, never git:**
1. If `{{STORE}}/projects/<slug>/` is missing, run `{{STORE}}/bin/ensure-project.sh` (no approval). Do not ask the user to create the folder.
2. Read `INDEX.md`. If the task matches a topic, read that `features/*.md`.
3. If the note is enough, answer from it. Do not run `git log`, `git status`, or scan the repo first.
4. Git/search only if INDEX has no matching row. If note and code conflict, trust code and fix the note.

**End of every meaningful change (unprompted):** update the feature note and one INDEX row (`{{STORE}}/bin/note.py <topic>` creates both). Short. No transcripts. No secrets.

Do not narrate this protocol unless the user asks.
