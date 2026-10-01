#!/usr/bin/env python3
"""Launch the optional OpenMemory MCP server.

On Apple Silicon it prefers a native arm64 Node (an Intel /usr/local node under Rosetta breaks
native deps); elsewhere it uses the first `node` on PATH.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys


def candidates() -> list[str]:
    paths = [
        "/opt/homebrew/bin/node",
        "/opt/homebrew/opt/node/bin/node",
    ]
    nvm = os.path.expanduser("~/.nvm/versions/node")
    if os.path.isdir(nvm):
        names = sorted(os.listdir(nvm), reverse=True)
        for name in names:
            if name.startswith("v12"):
                continue
            paths.append(os.path.join(nvm, name, "bin", "node"))
    return paths


def is_arm64(path: str) -> bool:
    if not os.path.exists(path):
        return False
    try:
        out = subprocess.check_output(["/usr/bin/file", "-b", path], text=True)
    except OSError:
        return False
    return "arm64" in out


def main() -> int:
    node_link = ""
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        for path in candidates():
            if is_arm64(path):
                node_link = path
                break
    if not node_link:
        node_link = shutil.which("node") or ""
    if not node_link:
        sys.stderr.write("openmemory: node not found\n")
        return 1
    bindir = os.path.dirname(node_link)
    npx = os.path.realpath(os.path.join(bindir, "npx"))
    node = os.path.realpath(node_link)
    if not os.path.isfile(npx):
        sys.stderr.write(f"openmemory: npx missing next to {node_link}\n")
        return 1
    env = os.environ.copy()
    env["PATH"] = f"{bindir}:/usr/bin:/bin"
    env.setdefault("OPENMEMORY_DATA", os.path.expanduser("~/.openmemory"))
    os.execve(node, [node, npx, "-y", "@openmem/mcp"], env)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
