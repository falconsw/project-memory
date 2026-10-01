#!/usr/bin/env python3
"""Install or update project-memory into the store and wire it into IDEs.

Usage (normally via the `project-memory` command):
  install.py [--yes] [--dry-run] [--store PATH] [--store-only] [--cursor --claude --gemini --codex | --all]
  install.py --uninstall [--yes] [--dry-run] [same IDE flags]

Without IDE flags it detects installed IDEs (~/.claude, ~/.cursor, ~/.gemini, ~/.codex), prints the plan
and asks before changing anything. Without a terminal it only prints the plan unless --yes is given.
--uninstall removes the IDE wiring (rule blocks, hooks, legacy skill, CLI link). The store and your notes stay.

The store (default ~/ai-memory, or $PROJECT_MEMORY_HOME) receives:
  PROTOCOL.md, GLOBAL-RULE.md, bin/*, projects/_template/, USER.md (only if missing)
Your notes under projects/<slug>/ are never touched.

IDE wiring (every changed file is backed up as <file>.bak-project-memory first):
  --cursor  ~/.cursor/rules/project-memory.mdc + sessionStart/beforeSubmitPrompt/stop hooks in ~/.cursor/hooks.json
  --claude  SessionStart + Stop hooks in ~/.claude/settings.json + marked block in ~/.claude/CLAUDE.md
            (the old skill is retired: it duplicated the rule and cost tokens every session)
  --gemini  marked block in ~/.gemini/GEMINI.md (Gemini CLI / Antigravity)
  --codex   marked block in ~/.codex/AGENTS.md
Re-running is safe: marked blocks are replaced, hooks are not duplicated.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aimem_common as c  # noqa: E402

REPO = os.path.dirname(c.BIN_DIR)
HOME = os.path.expanduser("~")
BEGIN, END = c.BEGIN, c.END
IDES = ("claude", "cursor", "gemini", "codex")
BIN_FILES = ("project-memory", "aimem_common.py", "ensure-project.py", "ensure-project.sh", "stop-check.py", "note.py", "doctor.py", "install.py")
MARKERS = ("ensure-project.py", "stop-check.py")
# Rules written by hand before this installer existed; we update those instead of adding a second copy.
LEGACY_CURSOR_RULES = ("shared-ai-memory.mdc",)


class Installer:
    def __init__(self, store: str, dry_run: bool, quiet: bool = False) -> None:
        self.store = store
        self.dry = dry_run
        self.quiet = quiet
        self.backed_up: set[str] = set()

    # -- helpers ---------------------------------------------------------

    def log(self, msg: str) -> None:
        if not self.quiet:
            print("  " + msg)

    def render(self, text: str) -> str:
        return text.replace("{{STORE}}", self.store)

    def backup(self, path: str) -> None:
        if path in self.backed_up or not os.path.isfile(path):
            return
        self.backed_up.add(path)
        if not self.dry:
            shutil.copy2(path, path + ".bak-project-memory")

    def put(self, path: str, text: str, backup: bool = True) -> None:
        old = c.read(path) if os.path.isfile(path) else None
        if old == text:
            return
        if backup and old is not None:
            self.backup(path)
        self.log(("update " if old is not None else "create ") + path)
        if not self.dry:
            c.write(path, text)

    def put_block(self, path: str, body: str) -> None:
        """Insert or replace the marked block. Skips files that already carry a hand-written rule."""
        old = c.read(path) if os.path.isfile(path) else ""
        block = "%s\n%s\n%s" % (BEGIN, body.strip(), END)
        if BEGIN in old and END in old:
            start = old.index(BEGIN)
            end = old.index(END) + len(END)
            new = old[:start] + block + old[end:]
        elif "ai-memory/PROTOCOL.md" in old or "project-memory/PROTOCOL.md" in old:
            self.log("skip   %s (already has a hand-written memory rule; remove it to let the installer manage it)" % path)
            return
        else:
            new = (old.rstrip() + "\n\n" if old.strip() else "") + block + "\n"
        self.put(path, new)

    def load_json(self, path: str) -> dict:
        if not os.path.isfile(path):
            return {}
        try:
            data = json.loads(c.read(path))
        except ValueError:
            raise SystemExit("install: %s is not valid JSON; fix it first" % path)
        return data if isinstance(data, dict) else {}

    def put_json(self, path: str, data: dict) -> None:
        self.put(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def hook_command(self, script: str, mode: str) -> str:
        return "python3 %s %s" % (os.path.join(self.store, "bin", script), mode)

    # -- store -------------------------------------------------------------

    def install_store(self) -> None:
        self.log("store  %s" % self.store)
        for name in ("PROTOCOL.md", "GLOBAL-RULE.md"):
            self.put(os.path.join(self.store, name), self.render(c.read(os.path.join(REPO, name))))
        for name in BIN_FILES:
            dest = os.path.join(self.store, "bin", name)
            self.put(dest, c.read(os.path.join(REPO, "bin", name)))
            if not self.dry and os.path.isfile(dest) and not name.endswith("aimem_common.py"):
                os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        tpl_src = os.path.join(REPO, "templates", "project")
        tpl_dest = os.path.join(self.store, "projects", "_template")
        for dirpath, _, files in os.walk(tpl_src):
            for f in files:
                src = os.path.join(dirpath, f)
                rel = os.path.relpath(src, tpl_src)
                self.put(os.path.join(tpl_dest, rel), c.read(src))
        user = os.path.join(self.store, "USER.md")
        if not os.path.exists(user):
            self.put(user, c.read(os.path.join(REPO, "templates", "USER.md")))
        self.put(os.path.join(self.store, ".repo"), REPO + "\n", backup=False)
        integrations = os.path.join(REPO, "integrations")
        for dirpath, _, files in os.walk(integrations):
            for f in files:
                src = os.path.join(dirpath, f)
                rel = os.path.relpath(src, REPO)
                self.put(os.path.join(self.store, rel), self.render(c.read(src)))

    def cli_link(self) -> str:
        return os.path.join(HOME, ".local", "bin", "project-memory")

    def link_cli(self) -> None:
        """Put `project-memory` on PATH via ~/.local/bin when that directory exists or is already on PATH."""
        bindir = os.path.dirname(self.cli_link())
        if not (os.path.isdir(bindir) or bindir in os.environ.get("PATH", "").split(os.pathsep)):
            return
        target = os.path.join(self.store, "bin", "project-memory")
        if os.path.islink(self.cli_link()) and os.readlink(self.cli_link()) == target:
            return
        if os.path.lexists(self.cli_link()) and not os.path.islink(self.cli_link()):
            self.log("skip   %s (exists and is not ours)" % self.cli_link())
            return
        self.log("link   %s -> %s" % (self.cli_link(), target))
        if not self.dry:
            os.makedirs(bindir, exist_ok=True)
            if os.path.islink(self.cli_link()):
                os.remove(self.cli_link())
            os.symlink(target, self.cli_link())

    def unlink_cli(self) -> None:
        link = self.cli_link()
        if os.path.islink(link) and os.path.realpath(link).startswith(os.path.realpath(self.store)):
            self.log("remove %s" % link)
            if not self.dry:
                os.remove(link)

    def rule_body(self) -> str:
        return self.render(c.read(os.path.join(REPO, "GLOBAL-RULE.md")))

    # -- IDEs --------------------------------------------------------------

    def install_cursor(self) -> None:
        rules = os.path.join(HOME, ".cursor", "rules")
        target = os.path.join(rules, "project-memory.mdc")
        for legacy in LEGACY_CURSOR_RULES:
            if os.path.isfile(os.path.join(rules, legacy)):
                target = os.path.join(rules, legacy)
                break
        front = "---\ndescription: Default every chat — read/write project-memory before exploring code\nalwaysApply: true\n---\n\n"
        self.put(target, front + self.rule_body())

        path = os.path.join(HOME, ".cursor", "hooks.json")
        data = self.load_json(path)
        data.setdefault("version", 1)
        hooks = data.setdefault("hooks", {})
        for event, script, mode in (
            ("sessionStart", "ensure-project.py", "--hook-cursor"),
            ("beforeSubmitPrompt", "ensure-project.py", "--hook-cursor"),
            ("stop", "stop-check.py", "--cursor"),
        ):
            cmd = self.hook_command(script, mode)
            self.upsert_hook(hooks.setdefault(event, []), script, {"command": cmd, "timeout": 15}, key="command")
        self.put_json(path, data)

    def install_claude(self) -> None:
        self.retire_skill()
        self.put_block(os.path.join(HOME, ".claude", "CLAUDE.md"), self.rule_body())
        path = os.path.join(HOME, ".claude", "settings.json")
        data = self.load_json(path)
        hooks = data.setdefault("hooks", {})
        for event, script, mode in (
            ("SessionStart", "ensure-project.py", "--hook-claude"),
            ("Stop", "stop-check.py", "--claude"),
        ):
            cmd = self.hook_command(script, mode)
            groups = hooks.setdefault(event, [])
            for g in groups:
                inner = [h for h in (g.get("hooks", []) if isinstance(g, dict) else []) if isinstance(h, dict)]
                found = [h for h in inner if script in str(h.get("command", ""))]
                if found:
                    found[0]["command"] = cmd
                    break
            else:
                groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 15}]})
        self.put_json(path, data)

    def retire_skill(self) -> None:
        """The skill repeated the CLAUDE.md block; keep one copy. Only removes a skill this project installed."""
        skill = os.path.join(HOME, ".claude", "skills", "project-memory", "SKILL.md")
        if os.path.isfile(skill) and "project-memory" in c.read(skill) and "PROTOCOL.md" in c.read(skill):
            self.log("retire %s (duplicated the rule; backup kept)" % skill)
            if not self.dry:
                shutil.move(skill, skill + ".bak-project-memory")

    def install_gemini(self) -> None:
        self.put_block(os.path.join(HOME, ".gemini", "GEMINI.md"), self.rule_body())

    def install_codex(self) -> None:
        self.put_block(os.path.join(HOME, ".codex", "AGENTS.md"), self.rule_body())

    @staticmethod
    def upsert_hook(entries: list, script: str, entry: dict, key: str) -> None:
        for e in entries:
            if isinstance(e, dict) and script in str(e.get(key, "")):
                e[key] = entry[key]
                return
        entries.insert(0, entry)

    # -- uninstall ---------------------------------------------------------

    def drop_block(self, path: str) -> None:
        old = c.read(path) if os.path.isfile(path) else ""
        if BEGIN not in old or END not in old:
            return
        new = (old[: old.index(BEGIN)].rstrip() + "\n\n" + old[old.index(END) + len(END):].lstrip()).strip()
        self.put(path, new + "\n" if new else "")

    def drop_hooks(self, path: str, claude: bool) -> None:
        if not os.path.isfile(path):
            return
        data = self.load_json(path)
        hooks = data.get("hooks")
        if not isinstance(hooks, dict):
            return
        for event in list(hooks):
            entries = hooks[event]
            if not isinstance(entries, list):
                continue
            kept = []
            for e in entries:
                if claude and isinstance(e, dict) and isinstance(e.get("hooks"), list):
                    e["hooks"] = [h for h in e["hooks"] if not any(m in str(h.get("command", "")) for m in MARKERS)]
                    if e["hooks"]:
                        kept.append(e)
                elif not (isinstance(e, dict) and any(m in str(e.get("command", "")) for m in MARKERS)):
                    kept.append(e)
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
        self.put_json(path, data)

    def uninstall(self, which: set) -> None:
        if "cursor" in which:
            rules = os.path.join(HOME, ".cursor", "rules")
            for name in ("project-memory.mdc",) + LEGACY_CURSOR_RULES:
                f = os.path.join(rules, name)
                if os.path.isfile(f):
                    self.backup(f)
                    self.log("remove %s" % f)
                    if not self.dry:
                        os.remove(f)
            self.drop_hooks(os.path.join(HOME, ".cursor", "hooks.json"), claude=False)
        if "claude" in which:
            self.retire_skill()
            self.drop_block(os.path.join(HOME, ".claude", "CLAUDE.md"))
            self.drop_hooks(os.path.join(HOME, ".claude", "settings.json"), claude=True)
        if "gemini" in which:
            self.drop_block(os.path.join(HOME, ".gemini", "GEMINI.md"))
        if "codex" in which:
            self.drop_block(os.path.join(HOME, ".codex", "AGENTS.md"))
        self.unlink_cli()


def detect() -> list:
    return [n for n in IDES if os.path.isdir(os.path.join(HOME, "." + n))]


def apply(a, store: str, which: list, quiet: bool, dry: bool) -> None:
    inst = Installer(store, dry, quiet)
    if a.uninstall:
        inst.uninstall(set(which))
        return
    inst.install_store()
    for name in which:
        getattr(inst, "install_" + name)()
    inst.link_cli()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", default="")
    for flag in IDES + ("all",):
        p.add_argument("--" + flag, action="store_true")
    p.add_argument("--store-only", action="store_true", help="install the store and CLI, wire no IDE")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", "-y", action="store_true", help="do not ask for confirmation")
    p.add_argument("--uninstall", action="store_true")
    a = p.parse_args()

    store = os.path.abspath(os.path.expanduser(a.store)) if a.store else c.store_root()
    if a.all:
        which = list(IDES)
    elif any(getattr(a, n) for n in IDES):
        which = [n for n in IDES if getattr(a, n)]
    elif a.store_only:
        which = []
    else:
        which = detect()
    verb = "Uninstall" if a.uninstall else "Install"
    print("%s project-memory (store %s)" % (verb, store))
    print("IDEs: %s" % (", ".join(which) or "none detected"))
    print("Plan:")
    apply(a, store, which, quiet=False, dry=True)
    if a.dry_run:
        print("dry-run: nothing changed.")
        return 0
    if not a.yes:
        if not sys.stdin.isatty():
            print("No terminal to confirm on: nothing changed. Re-run with --yes to apply.")
            return 1
        if input("Apply? [Y/n] ").strip().lower() not in ("", "y", "yes", "e", "evet"):
            print("Cancelled.")
            return 1
    apply(a, store, which, quiet=True, dry=False)
    if a.uninstall:
        print("Done. The store and your notes were left in place: %s" % store)
        return 0
    print("Done. Backups: <file>.bak-project-memory")
    if store != os.path.expanduser("~/ai-memory"):
        print("note: custom store: export PROJECT_MEMORY_HOME=%s in your shell profile" % store)
    link = os.path.join(HOME, ".local", "bin", "project-memory")
    print("Next: `%s status` to verify%s." % ("project-memory" if os.path.islink(link) else os.path.join(store, "bin", "project-memory"),
                                              "" if os.path.islink(link) else " (add ~/.local/bin to PATH for the short command)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
