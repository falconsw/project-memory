#!/usr/bin/env python3
"""Install or update project-memory into the store and wire it into IDEs.

Usage:
  install.py [--store PATH] [--cursor] [--claude] [--gemini] [--codex] [--all] [--dry-run]

Without IDE flags only the store is installed/updated.

The store (default ~/ai-memory, or $PROJECT_MEMORY_HOME) receives:
  PROTOCOL.md, GLOBAL-RULE.md, bin/*, projects/_template/, skills/, USER.md (only if missing)
Your notes under projects/<slug>/ are never touched.

IDE wiring (every changed file is backed up as <file>.bak-project-memory first):
  --cursor  ~/.cursor/rules/project-memory.mdc + sessionStart/beforeSubmitPrompt hooks in ~/.cursor/hooks.json
  --claude  ~/.claude/skills/project-memory/ + SessionStart hook in ~/.claude/settings.json
            + marked block in ~/.claude/CLAUDE.md
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
BEGIN = "<!-- project-memory:begin -->"
END = "<!-- project-memory:end -->"
BIN_FILES = ("aimem_common.py", "ensure-project.py", "ensure-project.sh", "note.py", "doctor.py", "install.py")
# Rules written by hand before this installer existed; we update those instead of adding a second copy.
LEGACY_CURSOR_RULES = ("shared-ai-memory.mdc",)


class Installer:
    def __init__(self, store: str, dry_run: bool) -> None:
        self.store = store
        self.dry = dry_run
        self.backed_up: set[str] = set()

    # -- helpers ---------------------------------------------------------

    def log(self, msg: str) -> None:
        print(("[dry-run] " if self.dry else "") + msg)

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

    def hook_command(self, mode: str) -> str:
        return "python3 %s %s" % (os.path.join(self.store, "bin", "ensure-project.py"), mode)

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
        skill = os.path.join(REPO, "skills", "project-memory", "SKILL.md")
        self.put(os.path.join(self.store, "skills", "project-memory", "SKILL.md"), self.render(c.read(skill)))
        integrations = os.path.join(REPO, "integrations")
        for dirpath, _, files in os.walk(integrations):
            for f in files:
                src = os.path.join(dirpath, f)
                rel = os.path.relpath(src, REPO)
                self.put(os.path.join(self.store, rel), self.render(c.read(src)))

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
        for event in ("sessionStart", "beforeSubmitPrompt"):
            entries = hooks.setdefault(event, [])
            cmd = self.hook_command("--hook-cursor")
            self.upsert_hook(entries, cmd, lambda e: {"command": cmd, "timeout": 15}, key="command")
        self.put_json(path, data)

    def install_claude(self) -> None:
        skill_src = os.path.join(REPO, "skills", "project-memory", "SKILL.md")
        self.put(os.path.join(HOME, ".claude", "skills", "project-memory", "SKILL.md"), self.render(c.read(skill_src)))
        self.put_block(os.path.join(HOME, ".claude", "CLAUDE.md"), self.rule_body())

        path = os.path.join(HOME, ".claude", "settings.json")
        data = self.load_json(path)
        hooks = data.setdefault("hooks", {})
        groups = hooks.setdefault("SessionStart", [])
        cmd = self.hook_command("--hook-claude")
        for group in groups:
            inner = group.get("hooks", []) if isinstance(group, dict) else []
            if any("ensure-project.py" in str(h.get("command", "")) for h in inner if isinstance(h, dict)):
                for h in inner:
                    if isinstance(h, dict) and "ensure-project.py" in str(h.get("command", "")):
                        h["command"] = cmd
                break
        else:
            groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 15}]})
        self.put_json(path, data)

    def install_gemini(self) -> None:
        self.put_block(os.path.join(HOME, ".gemini", "GEMINI.md"), self.rule_body())

    def install_codex(self) -> None:
        self.put_block(os.path.join(HOME, ".codex", "AGENTS.md"), self.rule_body())

    @staticmethod
    def upsert_hook(entries: list, cmd: str, make, key: str) -> None:
        for e in entries:
            if isinstance(e, dict) and "ensure-project.py" in str(e.get(key, "")):
                e[key] = cmd
                return
        entries.insert(0, make(None))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", default="")
    for flag in ("cursor", "claude", "gemini", "codex", "all"):
        p.add_argument("--" + flag, action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    store = os.path.abspath(os.path.expanduser(a.store)) if a.store else c.store_root()
    inst = Installer(store, a.dry_run)
    inst.install_store()
    if a.all or a.cursor:
        inst.install_cursor()
    if a.all or a.claude:
        inst.install_claude()
    if a.all or a.gemini:
        inst.install_gemini()
    if a.all or a.codex:
        inst.install_codex()
    if store != os.path.expanduser("~/ai-memory"):
        print("note: custom store — export PROJECT_MEMORY_HOME=%s in your shell profile" % store)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
