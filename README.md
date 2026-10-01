# project-memory

Shared, local, plain-Markdown memory for AI coding agents. Claude Code, Cursor, Antigravity/Gemini, and Codex all read and write the same notes, so a feature you built in one tool is known in the next, without re-exploring the codebase or digging through `git log`.

```
~/ai-memory/                      ← the store (yours, never committed)
├── PROTOCOL.md                   ← how agents read and write
├── USER.md                       ← cross-project preferences
├── bin/                          ← ensure-project, note, doctor, install
└── projects/
    ├── _template/
    └── <workspace-folder-name>/
        ├── INDEX.md              ← one row per topic
        └── features/<topic>.md   ← 3–8 bullet notes
```

## How it works

1. At session start a hook (or the agent itself) creates `projects/<slug>/` for the workspace folder, if it is missing.
2. Before touching code, the agent reads `INDEX.md` and only the matching `features/<topic>.md`.
3. After meaningful work it updates that note and its single `INDEX.md` row.

The full rules are in [PROTOCOL.md](PROTOCOL.md).

## Install

Requires Python 3.9+ (the macOS system `python3` is fine). No dependencies.

```sh
git clone <this repo> ~/code/project-memory
cd ~/code/project-memory

python3 bin/install.py --all --dry-run   # see what would change
python3 bin/install.py --all             # store + every IDE
python3 bin/install.py --cursor --claude # or pick IDEs
```

| Flag | What it wires |
| --- | --- |
| *(none)* | Store only: `PROTOCOL.md`, `bin/`, `projects/_template/`, `USER.md` if missing |
| `--cursor` | `~/.cursor/rules/project-memory.mdc`, `sessionStart` + `beforeSubmitPrompt` hooks |
| `--claude` | `~/.claude/skills/project-memory/`, `SessionStart` hook, block in `~/.claude/CLAUDE.md` |
| `--gemini` | Block in `~/.gemini/GEMINI.md` (Gemini CLI, Antigravity) |
| `--codex` | Block in `~/.codex/AGENTS.md` |

Re-running is safe. Notes under `projects/<slug>/` are never touched. Every IDE file is backed up as `<file>.bak-project-memory` before its first change. If a file already has a hand-written memory rule, the installer leaves it alone and says so.

Custom store location: `python3 bin/install.py --store ~/notes/memory`, then `export PROJECT_MEMORY_HOME=~/notes/memory`. `AI_MEMORY_HOME` is still honoured for older installs.

## Commands

```sh
~/ai-memory/bin/ensure-project.sh [slug]         # create the project folder (slug = folder name by default)
~/ai-memory/bin/note.py <topic> --status wip --summary "one line" --agent "Claude Code"
~/ai-memory/bin/doctor.py [--slug SLUG]          # broken INDEX rows, orphan notes, secret-like strings, stale notes
```

## Sharing notes with a team

The store is personal by default. To share one project's notes, make `projects/<slug>/` a git repo of its own (or a folder inside the project repo and symlink it into the store). Run `doctor.py` before pushing: it flags tokens, keys, and `password=` style lines.

## Optional: OpenMemory MCP

`integrations/openmemory/` contains a launcher and an MCP config example for search across notes. Markdown stays the source of truth.

## Known limitations

- The slug is the folder basename, so two different repos with the same folder name share a project folder.
- Hooks only create the folder and point the agent at it; following the protocol still depends on the agent reading its rule.

---

## Türkçe özet

Yapay zeka kod asistanları (Claude Code, Cursor, Antigravity/Gemini, Codex) için ortak, yerel, Markdown tabanlı proje hafızası. Bir araçta yaptığınız iş, diğerinde kodu baştan taramadan bilinir. Kurulum: `python3 bin/install.py --all --dry-run`, sonra `--all`. Notlarınız `~/ai-memory/projects/` altında kalır ve bu repoya girmez.
