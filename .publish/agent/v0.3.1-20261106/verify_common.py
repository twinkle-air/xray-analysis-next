"""Shared helpers for the verify_p*.py suites.

Four guarantees the stock stdlib does not give on a Chinese Windows developer machine:

* subprocess stdout is decoded with the ANSI code page (CP936) unless UTF-8 is requested, so
  the CLI's Chinese JSON either fails to parse or silently mangles paths.
* `shutil.rmtree(ignore_errors=True)` leaves read-only files behind, so a second suite run
  starts from a non-empty jobs/ directory.
* a regression never deletes or reuses a real workspace: each suite runs against a throwaway
  copy of the agent tree, the test spectra and the frozen model package, and the CLI is
  pointed at that copy through --workspace. Only data the suite itself creates is removed.
* the default regression is deterministic: the local stand-in host runs, and no ambient
  XRF_AGENT_LLM_* configuration leaks in (or is depended on) from the machine — the
  current process and every subprocess both get a scrubbed environment, restored on exit.
  A real host is an explicit, opt-in entry point, never the default.
"""
from __future__ import annotations

import contextlib
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
# `agent` sits either directly under this directory (flat developer layout) or under
# `agent-workspace/` (checked-out repository layout).
PACKAGE = next(p for p in (HERE / "agent", HERE / "agent-workspace" / "agent") if p.is_dir())
PACKAGE_PARENT = PACKAGE.parent
# The workspace everything is resolved against: the directory holding the agent tree and
# deliverables/. agent-workspace/ nests the package one level deeper than the flat layout.
WORKSPACE = PACKAGE_PARENT if (PACKAGE_PARENT / "deliverables").is_dir() else PACKAGE_PARENT.parent
PACKAGE_REL = PACKAGE.relative_to(WORKSPACE)
# host.py reads every host knob from the XRF_AGENT_LLM_* namespace: HOST, API_BASE/API_URL,
# API_KEY/KEY, MODEL, TIMEOUT, MAX_TOKENS, TEMPERATURE. Scrubbing by prefix covers all of
# them, aliases included, without maintaining an ever-growing allowlist.
LLM_PREFIX = "XRF_AGENT_LLM_"

ACTIVE = None  # the TestWorkspace of the running suite; its main() sets this


def scrub_host_env(out) -> None:
    """Replace every XRF_AGENT_LLM_* in a mapping (os.environ, or a subprocess env copy) with
    an explicit local stand-in host."""
    for key in [k for k in out if k.startswith(LLM_PREFIX)]:
        del out[key]
    out["XRF_AGENT_LLM_HOST"] = "local_simulation"


@contextlib.contextmanager
def isolated_host_env(real_host: bool = False, ambient=None):
    """Keep the default regression deterministic whatever this machine happens to have
    configured: scrub XRF_AGENT_LLM_* from this process for the duration and restore the
    exact previous environment on exit. Subprocesses are scrubbed separately by env().

    `ambient` first injects a machine-style configuration (a fully configured real host, or
    invalid numeric values) so a regression of the scrub is what a test catches; a working
    scrub is what keeps it out of the code under test. `real_host=True` leaves the ambient
    configuration in place for the explicit --real-host entry.
    """
    saved = dict(os.environ)
    try:
        if ambient:
            os.environ.update(ambient)
        if not real_host:
            scrub_host_env(os.environ)
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


class TestWorkspace:
    """A throwaway workspace mirroring the source layout: only suite-created data is touched."""

    def __init__(self, root: pathlib.Path):
        self.root = root

    @classmethod
    def create(cls) -> "TestWorkspace":
        root = pathlib.Path(tempfile.mkdtemp(prefix="xrf-verify-"))
        shutil.copytree(WORKSPACE / PACKAGE_REL, root / PACKAGE_REL,
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(WORKSPACE / "deliverables", root / "deliverables",
                        ignore=shutil.ignore_patterns("__pycache__"))
        print(f"isolated test workspace: {root}")
        return cls(root)

    @property
    def package_parent(self) -> pathlib.Path:
        return self.root / PACKAGE_REL.parent

    def env(self, extra=None, real_host: bool = False) -> dict:
        paths = [str(self.package_parent)]
        if str(self.root) not in paths:
            paths.append(str(self.root))
        out = dict(os.environ, PYTHONPATH=os.pathsep.join(paths))
        if not real_host:
            scrub_host_env(out)
        out["PYTHONUTF8"] = "1"
        out["PYTHONIOENCODING"] = "utf-8"
        if extra:
            out.update(extra)
        return out

    def cli(self) -> list:
        return [sys.executable, "-m", "agent.cli", "--workspace", str(self.root)]

    def close(self) -> None:
        rmtree(self.root)


def env(extra=None, real_host: bool = False) -> dict:
    """UTF-8 subprocess environment for the active test workspace (or the source tree)."""
    if ACTIVE is not None:
        return ACTIVE.env(extra, real_host)
    out = dict(os.environ, PYTHONPATH=str(PACKAGE_PARENT), PYTHONUTF8="1",
               PYTHONIOENCODING="utf-8")
    if not real_host:
        scrub_host_env(out)
    if extra:
        out.update(extra)
    return out


def run(args, extra=None, real_host: bool = False) -> tuple:
    """Run one CLI command against the active test workspace."""
    base = ACTIVE.cli() if ACTIVE else [sys.executable, "-m", "agent.cli"]
    cwd = str(ACTIVE.root) if ACTIVE else str(HERE)
    proc = subprocess.run(
        base + args, capture_output=True, text=True, encoding="utf-8",
        env=env(extra, real_host), cwd=cwd)
    body = proc.stdout.strip()
    try:
        import json
        obj = json.loads(body) if body else {}
    except json.JSONDecodeError as exc:
        obj = {"_raw": body[:2000], "_parse_error": str(exc)}
    return obj, proc.returncode, proc.stderr


def run_text(args, extra=None, real_host: bool = False) -> tuple:
    """Run one CLI command and return the raw stdout text, for human-facing output."""
    base = ACTIVE.cli() if ACTIVE else [sys.executable, "-m", "agent.cli"]
    cwd = str(ACTIVE.root) if ACTIVE else str(HERE)
    proc = subprocess.run(
        base + args, capture_output=True, text=True, encoding="utf-8",
        env=env(extra, real_host), cwd=cwd)
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
