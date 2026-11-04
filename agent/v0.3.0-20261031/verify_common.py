"""Shared helpers for the verify_p*.py suites.

Two things the stock stdlib gets wrong on a Chinese Windows developer machine, which turned
into intermittent suite failures:

* subprocess stdout is decoded with the ANSI code page (CP936) unless UTF-8 is requested, so
  the CLI's Chinese JSON either fails to parse or silently mangles paths.
* `shutil.rmtree(ignore_errors=True)` leaves read-only files behind, so a second suite run
  starts from a non-empty jobs/ directory.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import stat
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE
# The `agent` package sits either directly under this directory (flat developer layout) or
# under `agent-workspace/` (checked-out repository layout). Both the suites and the CLI
# subprocess import it, so the package parent is what goes on the search path either way.
PACKAGE = next(p for p in (HERE / "agent", HERE / "agent-workspace" / "agent") if p.is_dir())
PACKAGE_PARENT = PACKAGE.parent
CLI = [sys.executable, "-m", "agent.cli"]


def env(extra=None) -> dict:
    paths = [str(PACKAGE_PARENT)]
    if str(ROOT) not in paths:
        paths.append(str(ROOT))
    out = dict(os.environ, PYTHONPATH=os.pathsep.join(paths))
    # Decode subprocess stdout/stderr as UTF-8 instead of the ANSI code page.
    out["PYTHONUTF8"] = "1"
    out["PYTHONIOENCODING"] = "utf-8"
    if extra:
        out.update(extra)
    return out


def run(args, extra=None) -> tuple:
    """Run one CLI command. Returns (parsed_stdoutObject, returncode, stderr_text)."""
    proc = subprocess.run(
        CLI + args, capture_output=True, text=True, encoding="utf-8",
        env=env(extra), cwd=str(ROOT))
    body = proc.stdout.strip()
    try:
        obj = __import__("json").loads(body) if body else {}
    except __import__("json").JSONDecodeError as exc:
        obj = {"_raw": body[:2000], "_parse_error": str(exc)}
    return obj, proc.returncode, proc.stderr


def run_text(args, extra=None) -> tuple:
    """Run one CLI command and return the raw stdout text, for human-facing output."""
    proc = subprocess.run(
        CLI + args, capture_output=True, text=True, encoding="utf-8",
        env=env(extra), cwd=str(ROOT))
    return proc.stdout, proc.returncode, proc.stderr


def rmtree(path: pathlib.Path) -> None:
    """Remove a tree even when some files were marked read-only by the agent under test.

    shutil hands the failing entry to the callback as a plain str, and only Python >= 3.12
    has the non-deprecated `onexc` keyword; support both without pinning the interpreter.
    """
    target = pathlib.Path(path)
    if not target.exists():
        return

    def unlock(_func, bad_path, _exc) -> None:
        p = pathlib.Path(bad_path)
        try:
            os.chmod(p, stat.S_IWRITE)
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        except OSError:
            pass

    try:
        shutil.rmtree(target, onexc=unlock)
    except TypeError:
        shutil.rmtree(target, onerror=unlock)