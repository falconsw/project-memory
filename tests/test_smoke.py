"""End-to-end checks in a throwaway HOME. Run: python3 -m unittest discover -s tests"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self.tmp.name)
        self.store = os.path.join(self.home, "ai-memory")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("PROJECT_MEMORY", "AI_MEMORY", "CLAUDE_"))}
        self.env.update(HOME=self.home, PROJECT_MEMORY_HOME=self.store, GIT_CONFIG_GLOBAL=os.devnull)
        self.addCleanup(self.tmp.cleanup)

    def run_py(self, script, *args, cwd=None, stdin=None, check=True):
        p = subprocess.run([PY, script, *args], cwd=cwd or self.home, env=self.env, input=stdin,
                           capture_output=True, text=True)
        if check:
            self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def bin(self, name):
        return os.path.join(self.store, "bin", name)

    def git(self, cwd, *args):
        subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                       env=self.env, check=True, capture_output=True)

    def repo(self, name, remote=None):
        path = os.path.join(self.home, name)
        os.makedirs(path)
        self.git(path, "init", "-q")
        if remote:
            self.git(path, "remote", "add", "origin", remote)
        open(os.path.join(path, "a.py"), "w").write("x=1\n")
        self.git(path, "add", ".")
        self.git(path, "commit", "-qm", "init")
        return path

    def install(self, *flags):
        return self.run_py(os.path.join(REPO, "bin", "install.py"), "--yes", "--store", self.store, *flags)


class InstallTests(Sandbox):
    def snapshot(self):
        out = {}
        for d, _, files in os.walk(self.home):
            for f in files:
                p = os.path.join(d, f)
                out[p] = open(p, "rb").read()
        return out

    def test_install_is_idempotent_and_uninstall_restores(self):
        os.makedirs(os.path.join(self.home, ".claude"))
        settings = os.path.join(self.home, ".claude", "settings.json")
        json.dump({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}, open(settings, "w"))
        self.install("--all")
        first = {p: v for p, v in self.snapshot().items() if not p.endswith(".bak-project-memory")}
        self.install("--all")
        second = {p: v for p, v in self.snapshot().items() if not p.endswith(".bak-project-memory")}
        self.assertEqual(first, second)
        data = json.load(open(settings))
        cmds = [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]]
        self.assertEqual(sum("stop-check.py" in c for c in cmds), 1)
        self.assertIn("echo mine", cmds)

        self.install("--uninstall", "--all")
        data = json.load(open(settings))
        self.assertEqual([h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]], ["echo mine"])
        self.assertNotIn("SessionStart", data["hooks"])
        self.assertNotIn("project-memory", open(os.path.join(self.home, ".claude", "CLAUDE.md")).read())
        self.assertTrue(os.path.isdir(os.path.join(self.store, "projects", "_template")))

    def test_autodetect_wires_only_present_ides_and_cli_roundtrip(self):
        os.makedirs(os.path.join(self.home, ".cursor"))
        os.makedirs(os.path.join(self.home, ".local", "bin"))
        out = self.install().stdout
        self.assertIn("IDEs: cursor", out)
        self.assertTrue(os.path.exists(os.path.join(self.home, ".cursor", "hooks.json")))
        self.assertFalse(os.path.exists(os.path.join(self.home, ".claude")))
        link = os.path.join(self.home, ".local", "bin", "project-memory")
        self.assertTrue(os.path.islink(link))
        status = self.run_py(link, "status").stdout
        self.assertIn("ok   cursor  hooks", status)
        self.assertIn("miss claude  rule", status)
        # the store copy still finds the repo to uninstall/reinstall
        self.run_py(link, "uninstall", "--yes")
        self.assertFalse(os.path.lexists(link))
        self.assertNotIn("ensure-project", open(os.path.join(self.home, ".cursor", "hooks.json")).read())

    def test_without_terminal_or_yes_nothing_changes(self):
        p = self.run_py(os.path.join(REPO, "bin", "install.py"), "--store", self.store, "--all", check=False)
        self.assertEqual(p.returncode, 1)
        self.assertFalse(os.path.exists(self.store))

    def test_dry_run_writes_nothing(self):
        self.install("--all", "--dry-run")
        self.assertFalse(os.path.exists(self.store))


class FlowTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.install()
        self.proj = self.repo("shop", "git@example.com:a/shop.git")

    def test_session_hook_injects_now_and_index(self):
        self.run_py(self.bin("note.py"), "--now", "--task", "build cart", "--next", "tests", cwd=self.proj)
        self.run_py(self.bin("note.py"), "cart", "--summary", "cart logic", "--keys", "cart.py", cwd=self.proj)
        os.makedirs(os.path.join(self.proj, "sub"))
        p = self.run_py(self.bin("ensure-project.py"), "--hook-claude", cwd=self.proj,
                        stdin=json.dumps({"cwd": os.path.join(self.proj, "sub")}))
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Task: build cart", ctx)
        self.assertIn("| cart | wip | cart logic | cart.py |", ctx)
        self.assertLess(len(ctx), 1200)

    def test_note_upgrades_old_index_and_stamps_commit(self):
        dest = os.path.join(self.store, "projects", "shop")
        self.run_py(self.bin("ensure-project.py"), cwd=self.proj)
        open(os.path.join(dest, "INDEX.md"), "w").write(
            "# Project index\n\nSlug: `shop`\n\n| Topic | Status | Note |\n| --- | --- | --- |\n| auth | done | login |\n\nStatus: x\n")
        self.run_py(self.bin("note.py"), "billing", "--agent", "Cursor", cwd=self.proj)
        text = open(os.path.join(dest, "INDEX.md")).read()
        self.assertIn("| Topic | Status | Note | Keys |", text)
        self.assertIn("| auth | done | login |  |", text)
        self.assertRegex(open(os.path.join(dest, "features", "billing.md")).read(), r"Updated: \d{4}-\d\d-\d\d — Cursor @ [0-9a-f]{7}")

    def test_slug_collision_and_worktree(self):
        other = os.path.join(self.home, "x", "shop")
        os.makedirs(other)
        self.git(other, "init", "-q")
        self.run_py(self.bin("ensure-project.py"), cwd=self.proj)
        a = self.run_py(self.bin("ensure-project.py"), cwd=other).stdout.strip()
        self.assertRegex(os.path.basename(a), r"^shop-[0-9a-f]{6}$")
        wt = os.path.join(self.home, "wt-feature")
        self.git(self.proj, "worktree", "add", "-q", wt, "-b", "f")
        self.assertEqual(os.path.basename(self.run_py(self.bin("ensure-project.py"), cwd=wt).stdout.strip()), "shop")

    def test_archive_moves_old_done_rows(self):
        self.run_py(self.bin("note.py"), "old", "--status", "done", cwd=self.proj)
        dest = os.path.join(self.store, "projects", "shop")
        note = os.path.join(dest, "features", "old.md")
        with open(note) as fh:
            body = fh.read()
        with open(note, "w") as fh:
            fh.write(body.replace("Updated: ", "Updated: 2020-01-01 — x\n#", 1))
        self.assertIn("archived 1", self.run_py(self.bin("note.py"), "--archive", cwd=self.proj).stdout)
        self.assertNotIn("| old |", open(os.path.join(dest, "INDEX.md")).read())
        self.assertIn("| old |", open(os.path.join(dest, "ARCHIVE.md")).read())
        self.assertNotIn("orphan", self.run_py(self.bin("doctor.py"), "--slug", "shop", check=False).stdout)

    def stop(self, mode="--claude", **extra):
        payload = {"cwd": self.proj, **extra}
        return json.loads(self.run_py(self.bin("stop-check.py"), mode, cwd=self.proj, stdin=json.dumps(payload)).stdout or "{}")

    def test_stop_hook_nags_once_only_after_edits(self):
        self.run_py(self.bin("ensure-project.py"), "--hook-claude", cwd=self.proj, stdin=json.dumps({"cwd": self.proj}))
        self.assertEqual(self.stop(), {})
        time.sleep(0.05)
        open(os.path.join(self.proj, "a.py"), "w").write("x=2\n")
        self.assertEqual(self.stop()["decision"], "block")
        self.assertEqual(self.stop(stop_hook_active=True), {})
        self.assertIn("followup_message", self.stop("--cursor"))
        self.assertEqual(self.stop("--cursor", loop_count=1), {})
        self.run_py(self.bin("note.py"), "--now", "--task", "edit a", cwd=self.proj)
        self.assertEqual(self.stop(), {})

    def test_now_reports_related_topics_and_agent(self):
        self.run_py(self.bin("note.py"), "pay", "--summary", "payments", cwd=self.proj)
        note = os.path.join(self.store, "projects", "shop", "features", "pay.md")
        with open(note) as fh:
            body = fh.read()
        with open(note, "w") as fh:
            fh.write(body.replace("`path/to/file`", "`src/pay.py`"))
        out = self.run_py(self.bin("note.py"), "--now", "--task", "t", "--files", "src/pay.py", "--agent", "Antigravity", cwd=self.proj).stdout
        self.assertIn("Topics whose key files you touched: pay", out)
        out = self.run_py(self.bin("note.py"), "--now", "--task", "t", "--files", "other.py", "--agent", "Antigravity", cwd=self.proj).stdout
        self.assertIn("No topic lists these files", out)
        with open(os.path.join(self.store, "projects", "shop", "NOW.md")) as fh:
            self.assertIn("— Antigravity @", fh.read())

    def test_old_style_key_files_heading_is_understood(self):
        sys.path.insert(0, os.path.join(REPO, "bin"))
        import aimem_common as c
        text = "# X\n\n## Key files\n\n- `ios/Podfile`\n- `a/b.swift` (app)\n\n## Decisions\n- `not/this.py`\n"
        self.assertEqual(c.key_files(text), ["ios/Podfile", "a/b.swift"])

    def test_stop_hook_nags_after_a_later_commit_and_status_shows_seen(self):
        self.run_py(self.bin("ensure-project.py"), "--hook-claude", cwd=self.proj, stdin=json.dumps({"cwd": self.proj}))
        self.run_py(self.bin("note.py"), "--now", "--task", "x", cwd=self.proj)
        self.assertEqual(self.stop(), {})
        time.sleep(1.1)
        open(os.path.join(self.proj, "a.py"), "w").write("x=3\n")
        self.git(self.proj, "commit", "-qam", "later")
        self.assertEqual(self.stop()["decision"], "block")
        # commit-only case: nothing edited after the handoff, but a commit landed
        self.run_py(self.bin("note.py"), "--now", "--task", "y", cwd=self.proj)
        self.assertEqual(self.stop(), {})
        time.sleep(1.1)
        self.git(self.proj, "commit", "-q", "--allow-empty", "-m", "empty")
        self.assertEqual(self.stop()["decision"], "block")
        out = self.run_py(self.bin("doctor.py"), "--check-ides", "--slug", "shop", check=False).stdout
        self.assertRegex(out, r"seen claude/session-start\s+\d{4}-")
        self.assertRegex(out, r"seen claude/stop-reminded\s+\d{4}-")
        self.assertIn("never", out)

    def test_doctor_budget_drift_and_tokens(self):
        self.run_py(self.bin("note.py"), "pay", cwd=self.proj)
        note = os.path.join(self.store, "projects", "shop", "features", "pay.md")
        text = open(note).read().replace("`path/to/file`", "`gone.py`") + "".join("- x\n" for _ in range(9))
        open(note, "w").write(text)
        out = self.run_py(self.bin("doctor.py"), "--slug", "shop", "--tokens", check=False).stdout
        self.assertIn("over budget", out)
        self.assertIn("no longer exist", out)
        self.assertIn("injected at session start", out)


if __name__ == "__main__":
    unittest.main()
