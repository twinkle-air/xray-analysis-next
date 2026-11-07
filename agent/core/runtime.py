"""Numerical runtime environment check.

`Workspace.python()` picks the interpreter the frozen model subprocess runs under, but it
only checks that the executable exists: without a workspace venv it silently falls back to
the current interpreter, so a different Python or different package versions can produce
results that look the same and are not. This module fingerprints the interpreter the runner
will actually use and checks it against the declared policy, before any inference or cached
result is trusted.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Optional

from .paths import Workspace, read_json

PROBE_SOURCE = (
    "import json, platform, sys\n"
    "out = {'python': sys.version.split()[0], 'platform': platform.machine(),\n"
    "       'executable': sys.executable}\n"
    "for name in ('numpy', 'scipy', 'xraylib'):\n"
    "    module = __import__(name)\n"
    "    out[name] = getattr(module, '__version__', 'unknown')\n"
    "print(json.dumps(out))\n"
)

POLICY_NAME = "runtime_policy.json"
PROBE_TIMEOUT_S = 30.0


class RuntimeCheckError(Exception):
    """The numerical runtime does not satisfy the declared policy. Carries the error_code
    the tool surface reports (RUNTIME_MISMATCH, DEPENDENCY_MISSING or INTEGRITY_FAILED)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _version_tuple(text: str) -> tuple:
    digits = []
    for chunk in str(text).split("."):
        num = "".join(c for c in chunk if c.isdigit())
        digits.append(int(num) if num else 0)
    return tuple(digits)


def load_policy(workspace: Workspace) -> dict:
    path = workspace.agent_root() / "registry" / POLICY_NAME
    if not path.exists():
        raise RuntimeCheckError("INTEGRITY_FAILED", f"runtime policy missing: {path}")
    try:
        policy = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeCheckError("INTEGRITY_FAILED", f"runtime policy unreadable: {exc}")
    packages = policy.get("packages") if isinstance(policy, dict) else None
    python_min = (policy.get("python") or {}).get("min") if isinstance(policy, dict) else None
    if not isinstance(packages, dict) or not isinstance(python_min, str):
        raise RuntimeCheckError("INTEGRITY_FAILED", f"runtime policy malformed: {path}")
    return {"packages": packages, "python_min": python_min}


def probe(workspace: Workspace) -> dict:
    """Run the probe with the interpreter runner.py will use. Returns the raw fingerprint."""
    interpreter = workspace.python()
    try:
        proc = subprocess.run(
            [str(interpreter), "-c", PROBE_SOURCE],
            capture_output=True, text=True, encoding="utf-8",
            timeout=PROBE_TIMEOUT_S,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeCheckError(
            "DEPENDENCY_MISSING", f"数值解释器无法运行探针: {interpreter} ({exc})")
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        detail = tail[-1][:300] if tail else f"exit code {proc.returncode}"
        raise RuntimeCheckError(
            "DEPENDENCY_MISSING",
            f"数值运行环境缺少依赖或解释器不可用: {interpreter}\n{detail}")
    stdout = (proc.stdout or "").strip().splitlines()
    try:
        fingerprint = json.loads(stdout[-1])
        assert isinstance(fingerprint, dict)
    except (json.JSONDecodeError, AssertionError, IndexError) as exc:
        raise RuntimeCheckError("DEPENDENCY_MISSING", f"运行环境探针输出无法解析: {exc}")
    fingerprint["interpreter"] = str(interpreter).replace("\\", "/")
    fingerprint["selection_source"] = workspace.python_source()
    return fingerprint


def runtime_id(fingerprint: dict) -> str:
    """Exact identity of the numerical runtime. Two analyses under the same runtime share a
    dedup entry; any version difference produces a different id and a fresh computation."""
    return "|".join(f"{name}:{fingerprint.get(name, '?')}"
                    for name in ("python", "platform", "numpy", "scipy", "xraylib"))


def check(workspace: Workspace, fingerprint: dict, policy: Optional[dict] = None) -> dict:
    """Annotate the fingerprint with `verified` and `id`, or raise RUNTIME_MISMATCH listing
    every discrepancy against the declared policy."""
    policy = policy or load_policy(workspace)
    problems = []
    for name, expected in policy["packages"].items():
        actual = fingerprint.get(name)
        if str(actual) != str(expected):
            problems.append(f"{name}: 期望 {expected}，实际 {actual}")
    python_actual = _version_tuple(str(fingerprint.get("python", "")))
    python_min = _version_tuple(policy["python_min"])
    if python_actual < python_min:
        problems.append(f"python: 最低要求 {policy['python_min']}，实际 {fingerprint.get('python')}")
    if problems:
        raise RuntimeCheckError(
            "RUNTIME_MISMATCH",
            "数值运行环境与声明策略不符：" + "; ".join(problems)
            + "。请核对解释器环境，或用 --allow-unverified-runtime 显式放行（会记录未验证状态）。")
    annotated = dict(fingerprint)
    annotated["verified"] = True
    annotated["id"] = runtime_id(fingerprint)
    return annotated


def verify(workspace: Workspace) -> dict:
    """Fingerprint the numerical runtime and check the policy.

    Always returns an annotated fingerprint when the interpreter is usable: `verified` True
    when the policy passes, otherwise False with `reason` and `error_code` (RUNTIME_MISMATCH)
    plus the measured versions, so a refusal is auditable and an opt-in can record exactly
    what ran. Only an unusable interpreter (DEPENDENCY_MISSING) or a broken policy itself
    (INTEGRITY_FAILED) raises; the caller decides whether a mismatch refuses or proceeds.
    """
    fingerprint = probe(workspace)
    try:
        return check(workspace, fingerprint)
    except RuntimeCheckError as exc:
        annotated = dict(fingerprint)
        annotated["verified"] = False
        annotated["id"] = runtime_id(fingerprint)
        annotated["reason"] = str(exc)
        annotated["error_code"] = "RUNTIME_MISMATCH"
        return annotated
