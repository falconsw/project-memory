"""pip / pipx / uv entry point: runs the `project-memory` launcher shipped inside this package.

IDE hooks never run from here: `project-memory install` copies the scripts into the store and the
hooks call those copies, so upgrading or removing the package (or uv clearing its cache) cannot
break a running IDE.
"""
from __future__ import annotations

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    launcher = os.path.join(HERE, "bin", "project-memory")
    sys.argv[0] = launcher
    runpy.run_path(launcher, run_name="__main__")
