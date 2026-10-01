"""Shared helpers for ai-memory scripts. Standard library only (works on macOS /usr/bin/python3 3.9)."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil

SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TOPIC_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RESERVED_SLUGS = {"_template", ".", ".."}

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


def slug_from_path(path: str) -> str:
    path = os.path.abspath(os.path.expanduser(path or ""))
    return os.path.basename(path.rstrip(os.sep))


def valid_slug(slug: str) -> bool:
    return bool(slug) and slug not in RESERVED_SLUGS and bool(SLUG_RE.match(slug))


def project_dir(root: str, slug: str) -> str:
    return os.path.join(root, "projects", slug)


def ensure_project(root: str, slug: str) -> str:
    """Create `projects/<slug>/` from the template if missing. Never overwrites. Returns the path or ''."""
    if not valid_slug(slug):
        return ""
    dest = project_dir(root, slug)
    if os.path.isdir(dest):
        return dest
    template = project_template_dir(root)
    if not os.path.isdir(template):
        return ""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(template, dest)
    index = os.path.join(dest, "INDEX.md")
    if os.path.isfile(index):
        text = read(index)
        text = text.replace("{{SLUG}}", slug)
        # Older templates shipped an example row and a placeholder slug line.
        text = text.replace("Slug: `_template` (replace after copy)", "Slug: `%s`" % slug)
        text = text.replace("| (example) auth | done | `features/auth.md` |\n", "")
        write(index, text)
    return dest


def parse_hook_cwd(raw: str) -> str:
    """Extract the workspace path from an IDE hook's JSON stdin (Cursor, Claude Code, …)."""
    if not raw.strip():
        return ""
    try:
        data = json.loads(raw)
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
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


def today() -> str:
    return _dt.date.today().isoformat()


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def index_rows(index_text: str) -> list[list[str]]:
    """Data rows of the INDEX table as cell lists (header and separator skipped)."""
    rows = []
    for line in index_text.splitlines():
        s = line.strip()
        if not s.startswith("|") or not s.endswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells or cells[0].lower() == "topic" or set(cells[0]) <= set("-: "):
            continue
        rows.append(cells)
    return rows
