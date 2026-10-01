# project-memory

Shared, local, plain-Markdown memory for AI coding agents. Claude Code, Cursor, Antigravity/Gemini, and Codex all read and write the same notes, so a feature you built in one tool is known in the next, without re-exploring the codebase or digging through `git log`.

```
~/ai-memory/                      ← the store (yours, never committed)
├── PROTOCOL.md                   ← how agents read and write
├── USER.md                       ← cross-project preferences
├── bin/                          ← ensure-project, note, doctor, install
└── projects/
    ├── _template/
    └── <repo-folder-name>/
        ├── NOW.md                ← where the last session stopped (read first)
        ├── INDEX.md              ← one row per topic (+ keywords)
        ├── ARCHIVE.md            ← old `done` rows, never loaded at start
        └── features/<topic>.md   ← 3–8 bullet notes
```

## How it works

1. At session start a hook creates `projects/<slug>/` if missing and **injects `NOW.md` + `INDEX.md` into the context**: the agent starts with zero tool calls and ~300–800 tokens.
2. The agent continues from NOW and opens only the one `features/<topic>.md` that matches. No `git log`, no repo scan.
3. After meaningful work it runs `note.py --now ...` (handoff) and `note.py <topic> ...` (feature note + INDEX row). A Stop hook asks once if code changed but NOW was not refreshed.

Switching IDE mid-task works because NOW says what was being done, what is next, and which files matter.

The full rules are in [PROTOCOL.md](PROTOCOL.md).

## Install

Requires Python 3.9+ (the macOS system `python3` is fine). No dependencies.

```sh
git clone https://github.com/falconsw/project-memory ~/code/project-memory
~/code/project-memory/bin/project-memory install
```

It detects your IDEs (`~/.claude`, `~/.cursor`, `~/.gemini`, `~/.codex`), prints exactly what it will change, and asks `Apply? [Y/n]`. It also links `~/.local/bin/project-memory` when that directory exists, so afterwards just type `project-memory`.

```sh
project-memory status        # what is wired where + tokens injected per project
project-memory uninstall     # remove IDE wiring; your notes stay
project-memory install --dry-run | --yes | --claude --cursor | --all | --store-only
```

| Flag | What it wires |
| --- | --- |
| *(none)* | Every detected IDE, plus the store and the CLI link |
| `--store-only` | Store only: `PROTOCOL.md`, `bin/`, `projects/_template/`, `USER.md` if missing |
| `--cursor` | `~/.cursor/rules/project-memory.mdc`, `sessionStart` + `beforeSubmitPrompt` + `stop` hooks |
| `--claude` | `SessionStart` + `Stop` hooks in `~/.claude/settings.json`, block in `~/.claude/CLAUDE.md` (the old skill is retired: it duplicated the rule) |
| `--gemini` | Block in `~/.gemini/GEMINI.md` (Gemini CLI, Antigravity) |
| `--codex` | Block in `~/.codex/AGENTS.md` |

Without a terminal (CI, scripts) `install` only prints the plan unless you pass `--yes`. Re-running is safe. Notes under `projects/<slug>/` are never touched. Every IDE file is backed up as `<file>.bak-project-memory` before its first change. If a file already has a hand-written memory rule, the installer leaves it alone and says so.

Requires Python 3.9+ (the macOS system `python3` is fine). No dependencies.

Custom store location: `project-memory install --store ~/notes/memory`, then `export PROJECT_MEMORY_HOME=~/notes/memory`. `AI_MEMORY_HOME` is still honoured for older installs.

## Commands

```sh
project-memory note|now|archive|doctor              # same tools as below, one command
~/ai-memory/bin/ensure-project.sh                # create/print this repo's project dir
~/ai-memory/bin/note.py --now --task "..." --state "..." --next "..." --files a.py,b.py   # handoff (or --now --done)
~/ai-memory/bin/note.py <topic> --status wip --summary "one line" --keys "words, files" --agent "Claude Code"
~/ai-memory/bin/note.py --archive [--days 30]    # move old `done` rows out of INDEX
~/ai-memory/bin/doctor.py [--slug S] [--tokens] [--check-ides]
```

`doctor.py` reports broken INDEX rows, orphan notes, secret-like strings, stale notes, **size budgets** (INDEX ≤ 40 rows, note ≤ 8 bullets, NOW ≤ 1500 chars), **key files deleted or changed in git since the note's commit**, and with `--tokens` how many tokens each project injects at session start.

## Slugs

The slug is the main repo's folder name; subfolders and git worktrees resolve to the same project. If a different repo already owns that name, the slug becomes `<name>-<6 hex>` (identity = git remote URL, else path; stored in `.origin`).

## Tests

```sh
python3 -m unittest discover -s tests   # installs into a throwaway HOME; also runs in CI (3.9 and 3.13)
```

## Sharing notes with a team

The store is personal by default. To share one project's notes, make `projects/<slug>/` a git repo of its own (or a folder inside the project repo and symlink it into the store). Run `doctor.py` before pushing: it flags tokens, keys, and `password=` style lines.

## Optional: OpenMemory MCP

`integrations/openmemory/` contains a launcher and an MCP config example for search across notes. Markdown stays the source of truth.

## Tested in practice

One real hand-off, Claude Code → Antigravity, on an unrelated project (2026-10-01):

1. **Claude Code**: started a task in an area no earlier session had touched ("add a border between the rows of the Market card"). When it finished it ran `note.py --now --task ... --state ...`, which wrote the project's `NOW.md`.
2. **Antigravity**: in a brand-new chat, the user asked a follow-up about the same area ("we added the borders, but there is no room above Add Symbol"). Its first moves were reading `INDEX.md` and `NOW.md` from the store (visible in its activity log), before opening any code.

What this shows: the handoff file written by one IDE is the first thing the other IDE reads, with no user prompting and no `git log`. What it does not show: whether the follow-up fix was correct, or how many tokens were saved; measure with `project-memory status` (tokens injected per project) and compare a session with and without the store.

## Known limitations

- Gemini CLI, Antigravity and Codex have no hooks: they only get the rule block and run `ensure-project.sh` themselves. `doctor.py --check-ides` shows what is wired, but only a new chat quoting the protocol proves a tool really loads its rule file.
- The Stop hook relies on each IDE's hook API (Claude Code `Stop`, Cursor `stop`); the Cursor one is untested against a live Cursor.
- Following the protocol on the write side still depends on the agent; the Stop hook is a safety net, not a guarantee.

---

## Türkçe özet

Yapay zeka kod asistanları (Claude Code, Cursor, Antigravity/Gemini, Codex) için ortak, yerel, Markdown tabanlı proje hafızası. Bir araçta yaptığınız iş, diğerinde kodu baştan taramadan bilinir. Oturum başında `NOW.md` (nerede kaldım) ve `INDEX.md` bağlama otomatik enjekte edilir, ajan sıfır tool çağrısıyla devam eder. Kurulum: `bin/project-memory install` (IDE'leri kendisi bulur, planı gösterir, onay ister); doğrulama: `project-memory status`; kaldırma: `project-memory uninstall`. Claude Code'dan Antigravity'ye gerçek bir devir testi yapıldı: Antigravity yeni sohbette önce `INDEX.md` ve `NOW.md`'yi okudu (README'deki "Tested in practice"). Notlarınız `~/ai-memory/projects/` altında kalır ve bu repoya girmez.
