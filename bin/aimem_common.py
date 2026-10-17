"""Shared helpers for ai-memory scripts. Standard library only (works on macOS /usr/bin/python3 3.9)."""
from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

__version__ = "0.1.0"
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RESERVED_SLUGS = {"_template", ".", ".."}
BEGIN = "<!-- project-memory:begin -->"
END = "<!-- project-memory:end -->"
INDEX_HEADER = ["Topic", "Status", "Note", "Keys"]
INDEX_BUDGET_CHARS = 3500
NOW_BUDGET_CHARS = 1500

BIN_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_TEMPLATES = os.path.join(os.path.dirname(BIN_DIR), "templates")


def store_root() -> str:
    """`$PROJECT_MEMORY_HOME`, else `$AI_MEMORY_HOME` (older installs), else `~/ai-memory`."""
    raw = os.environ.get("PROJECT_MEMORY_HOME") or os.environ.get("AI_MEMORY_HOME") or "~/ai-memory"
    return os.path.abspath(os.path.expanduser(raw))


def project_template_dir(root: str) -> str:
    """Installed store keeps its template at `projects/_template`; fall back to the repo copy."""
    installed = os.path.join(root, "projects", "_template")
    if os.path.isdir(installed):
        return installed
    return os.path.join(REPO_TEMPLATES, "project")


# -- files ---------------------------------------------------------------


def today() -> str:
    return _dt.date.today().isoformat()


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path: str, text: str) -> None:
    """Atomic: a reader in another IDE never sees a half-written file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = "%s.tmp%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


@contextlib.contextmanager
def lock(path: str, timeout: float = 3.0):
    """Best-effort lock around a read-modify-write; proceeds unlocked after `timeout` rather than hanging an IDE."""
    lp = path + ".lock"
    deadline = time.time() + timeout
    fd = None
    os.makedirs(os.path.dirname(lp) or ".", exist_ok=True)
    while fd is None:
        try:
            fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lp) > 10:
                    os.unlink(lp)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                break
            time.sleep(0.05)
        except OSError:
            break
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(lp)


# -- git / slug ----------------------------------------------------------


def git(cwd: str, *args: str, strip: bool = True) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", cwd] + list(args), capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if out.returncode != 0:
        return ""
    return out.stdout.strip() if strip else out.stdout


def repo_info(cwd: str) -> tuple[str, str]:
    """(main repo root, identity). Worktrees and subfolders resolve to the main repo; clones of one remote share identity."""
    cwd = os.path.realpath(os.path.expanduser(cwd or "."))
    common = git(cwd, "rev-parse", "--git-common-dir")
    root = cwd
    if common:
        common = common if os.path.isabs(common) else os.path.normpath(os.path.join(cwd, common))
        if os.path.basename(common) == ".git":
            root = os.path.dirname(common)
        else:
            root = git(cwd, "rev-parse", "--show-toplevel") or cwd
        remote = git(root, "config", "--get", "remote.origin.url")
        if remote:
            return root, remote
    return root, os.path.realpath(root)


def slug_from_path(path: str) -> str:
    path = os.path.abspath(os.path.expanduser(path or ""))
    return os.path.basename(path.rstrip(os.sep))


def valid_slug(slug: str) -> bool:
    return bool(slug) and slug not in RESERVED_SLUGS and bool(SLUG_RE.match(slug))


def project_dir(root: str, slug: str) -> str:
    return os.path.join(root, "projects", slug)


def read_origin(dest: str) -> dict:
    try:
        data = json.loads(read(os.path.join(dest, ".origin")))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_slug(store: str, cwd: str) -> tuple[str, dict]:
    """Folder name of the main repo; `<name>-<hash>` when another repo already owns that name."""
    root, ident = repo_info(cwd)
    base = slug_from_path(root)
    owner = read_origin(project_dir(store, base)).get("id")
    if owner and owner != ident:
        base = "%s-%s" % (base, hashlib.sha1(ident.encode("utf-8")).hexdigest()[:6])
    return base, {"id": ident, "root": root}


def ensure_project(root: str, slug: str, origin: "dict | None" = None) -> str:
    """Create `projects/<slug>/` from the template if missing. Never overwrites notes. Returns the path or ''."""
    if not valid_slug(slug):
        return ""
    dest = project_dir(root, slug)
    if not os.path.isdir(dest):
        template = project_template_dir(root)
        if not os.path.isdir(template):
            return ""
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(template, dest)
        index = os.path.join(dest, "INDEX.md")
        if os.path.isfile(index):
            text = read(index).replace("{{SLUG}}", slug)
            # Older templates shipped an example row and a placeholder slug line.
            text = text.replace("Slug: `_template` (replace after copy)", "Slug: `%s`" % slug)
            text = text.replace("| (example) auth | done | `features/auth.md` |\n", "")
            write(index, text)
    # Projects created before NOW.md existed get one on first contact.
    now = os.path.join(dest, "NOW.md")
    if not os.path.exists(now):
        tpl = os.path.join(project_template_dir(root), "NOW.md")
        write(now, read(tpl) if os.path.isfile(tpl) else "# Now\n\n(nothing in progress)\n")
    if origin and read_origin(dest) != origin:
        write(os.path.join(dest, ".origin"), json.dumps(origin, indent=1) + "\n")
    return dest


def parse_hook_cwd(raw: str) -> str:
    """Extract the workspace path from an IDE hook's JSON stdin (Cursor, Claude Code, …)."""
    data = parse_hook_json(raw)
    for key in ("cwd", "workspace_root", "workspaceRoot", "project_dir"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    roots = data.get("workspace_roots") or data.get("workspaceRoots") or data.get("roots")
    if isinstance(roots, list) and roots:
        first = roots[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            for key in ("path", "uri", "cwd"):
                val = first.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip().replace("file://", "", 1)
    return ""


def parse_hook_json(raw: str) -> dict:
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# -- INDEX table ---------------------------------------------------------


def _cells(line: str) -> list[str]:
    return [x.strip() for x in line.strip().strip("|").split("|")]


def _is_table_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|")


def index_rows(index_text: str) -> list[list[str]]:
    """Data rows of the INDEX table as cell lists (header and separator skipped)."""
    rows = []
    for line in index_text.splitlines():
        if not _is_table_line(line):
            continue
        cells = _cells(line)
        if not cells or cells[0].lower() == "topic" or set(cells[0]) <= set("-: "):
            continue
        rows.append(cells)
    return rows


def split_index(text: str) -> tuple[list[str], list[list[str]], list[str]]:
    """(lines before the table, rows padded to 4 cells, lines after the table)."""
    lines = text.splitlines()
    idx = [i for i, l in enumerate(lines) if _is_table_line(l)]
    if not idx:
        return lines, [], []
    pre, post = lines[: idx[0]], lines[idx[-1] + 1:]
    rows = [(r + [""] * 4)[:4] if len(r) <= 4 else r[:3] + [" / ".join(r[3:])] for r in index_rows(text)]
    return pre, rows, post


def render_index(pre: list[str], rows: list[list[str]], post: list[str]) -> str:
    table = ["| " + " | ".join(INDEX_HEADER) + " |", "| " + " | ".join("---" for _ in INDEX_HEADER) + " |"]
    table += ["| " + " | ".join(x.replace("|", "/") for x in r) + " |" for r in rows]
    while pre and not pre[-1].strip():
        pre = pre[:-1]
    return "\n".join(pre + ([""] if pre else []) + table + post) + "\n"


# -- session context -----------------------------------------------------


def compact(text: str, budget: int, more: str = "run note.py --archive") -> str:
    """Drop blank lines, boilerplate and table separators; cut to `budget` chars."""
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("Slug:") or s.startswith("Status:") or s.startswith("# "):
            continue
        if _is_table_line(s) and set(_cells(s)[0]) <= set("-: "):
            continue
        keep.append(s)
    out = "\n".join(keep)
    return out if len(out) <= budget else out[:budget].rsplit("\n", 1)[0] + "\n… (truncated; %s)" % more


def now_is_empty(text: str) -> bool:
    return "Task:" not in text


def session_context(store: str, dest: str) -> str:
    """What the SessionStart hook injects, so the agent starts with zero tool calls."""
    parts = [
        "project-memory: %s | protocol %s. INDEX and NOW below are already loaded: do not re-read them; "
        "open only the matching features/<topic>.md." % (dest, os.path.join(store, "PROTOCOL.md"))
    ]
    for label, name, budget in (("NOW", "NOW.md", NOW_BUDGET_CHARS), ("INDEX", "INDEX.md", INDEX_BUDGET_CHARS)):
        path = os.path.join(dest, name)
        if not os.path.isfile(path):
            continue
        text = read(path)
        if name == "NOW.md" and now_is_empty(text):
            continue
        body = compact(text, budget)
        if body:
            parts.append("%s:\n%s" % (label, body))
    return "\n".join(parts)


KEY_FILES_RE = re.compile(r"(?i)key files?\b")
TICKS_RE = re.compile(r"`([^`\s]+)`")


def key_files(text: str) -> list[str]:
    """Paths in a note's `Key files` line, or in the bullet list under a `## Key files` heading."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not KEY_FILES_RE.search(line):
            continue
        found = TICKS_RE.findall(line)
        if not found:
            for nxt in lines[i + 1:]:
                if nxt.startswith("#"):
                    break
                found += TICKS_RE.findall(nxt)
        return [f for f in found if "/" in f or "." in f]
    return []


def related_topics(dest: str, files: list[str]) -> list[str]:
    """Topics whose `Key files` overlap `files` (exact path, or same basename)."""
    wanted = {f.strip() for f in files if f.strip()}
    names = {os.path.basename(f) for f in wanted}
    feats = os.path.join(dest, "features")
    out = []
    for row in index_rows(read(os.path.join(dest, "INDEX.md"))) if os.path.isfile(os.path.join(dest, "INDEX.md")) else []:
        topic = row[0].strip("` ")
        note = os.path.join(feats, topic + ".md")
        if not os.path.isfile(note):
            continue
        for f in key_files(read(note)):
            f = f.split("(")[0].rstrip(",")
            if f in wanted or os.path.basename(f) in names or any(w.endswith("/" + f) or f.endswith("/" + w) for w in wanted):
                out.append(topic)
                break
    return out


# -- prompt topics (UserPromptSubmit hook) ---------------------------------

PROMPT_MIN_CHARS = 8
PROMPT_TOPICS_MAX = 2
PROMPT_NOTE_BUDGET_CHARS = 2500
PROMPT_SEEN = ".prompt-topics.json"
PROMPT_SEEN_SESSIONS = 20
NOTE_REF_RE = re.compile(r"features/([a-z0-9][a-z0-9-]*)\.md")
WORD_RE = re.compile(r"[\w./-]+")
PLACEHOLDER_KEYS = {"path/to/file", "words", "files"}


def _norm(text: str) -> str:
    # Turkish capital dotted I lowercases to "i" + a combining dot; fold it to a plain "i".
    return text.replace("İ", "i").lower()


def row_topic(row: list[str]) -> str:
    """The note an INDEX row points at: a `features/<x>.md` link in any cell, else the topic cell."""
    refs = NOTE_REF_RE.findall(" ".join(row))
    return refs[0] if refs else row[0].strip("` ")


def topic_terms(row: list[str], note_text: str) -> dict[str, int]:
    """Search terms of one topic with weights: Keys and the note's key files 2, topic-name parts 1."""
    topic = row_topic(row)
    terms = {}
    for part in topic.split("-"):
        if len(part) >= 4:
            terms[part] = 1
    terms[topic] = 2
    keys = row[3].split(",") if len(row) > 3 else []
    for raw in keys + [f.split("(")[0] for f in key_files(note_text)]:
        term = _norm(raw.strip(" `'\"")).strip("./-")
        if len(term) >= 2 and term not in PLACEHOLDER_KEYS:
            terms[term] = 2
    return terms


def _term_hit(term: str, words: list[str], text: str) -> bool:
    if " " in term:
        return term in text
    if "/" in term:
        base = term.rsplit("/", 1)[-1]
        return any(w == term or w.rsplit("/", 1)[-1] == base for w in words)
    # Prefix match lets suffixes through ("sepet" hits "sepetteki", "release" hits "releases").
    return any(w == term or w.rsplit("/", 1)[-1] == term or (len(term) >= 5 and w.startswith(term)) for w in words)


def match_topics(dest: str, prompt: str, skip: "set | None" = None, limit: int = PROMPT_TOPICS_MAX) -> list[str]:
    """Topics whose keys, key files or name appear in `prompt`, best first. Plain keyword overlap: no model."""
    index = os.path.join(dest, "INDEX.md")
    if not os.path.isfile(index):
        return []
    text = _norm(prompt)
    words = [w for w in (w.strip("./-") for w in WORD_RE.findall(text)) if w]
    scored = []
    for pos, row in enumerate(index_rows(read(index))):
        topic = row_topic(row)
        note = os.path.join(dest, "features", topic + ".md")
        if (skip and topic in skip) or not TOPIC_RE.match(topic) or not os.path.isfile(note):
            continue
        score = sum(w for t, w in topic_terms(row, read(note)).items() if _term_hit(t, words, text))
        if score >= 2:
            scored.append((-score, pos, topic))
    return [t for _, _, t in sorted(scored)[:limit]]


def prompt_context(dest: str, topics: list[str]) -> str:
    parts = ["project-memory: feature notes matching this prompt (already loaded: do not re-read them)."]
    for topic in topics:
        body = compact(read(os.path.join(dest, "features", topic + ".md")), PROMPT_NOTE_BUDGET_CHARS, "open the note for the rest")
        parts.append("features/%s.md:\n%s" % (topic, body))
    return "\n".join(parts)


def _load_prompt_seen(path: str) -> dict:
    try:
        data = json.loads(read(path))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def prompt_seen(dest: str, session: str) -> list[str]:
    """Topics the prompt hook already injected in `session`."""
    entry = _load_prompt_seen(os.path.join(dest, PROMPT_SEEN)).get(session)
    return list(entry.get("topics", [])) if isinstance(entry, dict) else []


def remember_prompt_topics(dest: str, session: str, topics: "list[str] | None") -> None:
    """Add `topics` to `session`'s injected set; None forgets the session (SessionStart, also after /compact). Best effort."""
    path = os.path.join(dest, PROMPT_SEEN)
    try:
        with lock(path, timeout=1.0):
            data = _load_prompt_seen(path)
            if topics is None:
                if data.pop(session, None) is None:
                    return
            else:
                old = data.get(session, {}).get("topics", []) if isinstance(data.get(session), dict) else []
                data[session] = {"topics": old + [t for t in topics if t not in old], "t": int(time.time())}
                recent = sorted(data, key=lambda k: data[k].get("t", 0) if isinstance(data[k], dict) else 0)
                for k in recent[:-PROMPT_SEEN_SESSIONS]:
                    del data[k]
            write(path, json.dumps(data, indent=1, sort_keys=True) + "\n")
    except OSError:
        pass


def mark_seen(store: str, key: str) -> None:
    """Record that a hook fired (`status` shows it), so a silently dead hook is noticeable. Best effort."""
    path = os.path.join(store, ".hooks-seen.json")
    try:
        with lock(path, timeout=1.0):
            try:
                data = json.loads(read(path))
            except (OSError, ValueError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            data[key] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            write(path, json.dumps(data, indent=1, sort_keys=True) + "\n")
    except OSError:
        pass


def read_seen(store: str) -> dict:
    try:
        data = json.loads(read(os.path.join(store, ".hooks-seen.json")))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def approx_tokens(text: str) -> int:
    return (len(text) + 3) // 4
