"""Workspace layout and path safety. Every filesystem operation is confined to workspace_root."""
from __future__ import annotations
import json, os, pathlib

STAGES = ("received", "validated", "running", "succeeded", "failed", "cancelled", "awaiting_input")
REPORT_STATES = ("draft", "exported", "failed")


class Workspace:
    def __init__(self, root: str | os.PathLike):
        self.root = pathlib.Path(root).resolve()

    def agent_root(self) -> pathlib.Path:
        """The agent code + registry tree, kept under the workspace root alongside jobs/."""
        out = self.root / "agent"
        self._confine(out)
        return out

    def job_dir(self, job_id: str) -> pathlib.Path:
        out = self.root / "jobs" / job_id
        self._confine(out)
        return out

    def sub(self, job_id: str, bucket: str) -> pathlib.Path:
        if bucket not in ("input", "parsed", "inference", "report", "audit"):
            raise ValueError(f"unknown bucket {bucket!r}")
        out = self.job_dir(job_id) / bucket
        out.mkdir(parents=True, exist_ok=True)
        return out

    def job_state(self, job_id: str) -> pathlib.Path:
        return self.sub(job_id, "audit") / "state.json"

    def job_log(self, job_id: str) -> pathlib.Path:
        return self.sub(job_id, "audit") / "run.log"

    def jobs_index(self) -> pathlib.Path:
        out = self.root / "jobs" / ".dedup-index.json"
        self._confine(out)
        return out

    def model_registry(self) -> pathlib.Path:
        return self.agent_root() / "registry" / "model_registry.json"

    def tool_contracts(self) -> pathlib.Path:
        return self.agent_root() / "registry" / "tool_contracts.json"

    def error_codes(self) -> pathlib.Path:
        return self.agent_root() / "registry" / "error_codes.json"

    def comparison_policy(self) -> pathlib.Path:
        return self.agent_root() / "registry" / "comparison_policy.json"

    def version_metadata(self) -> pathlib.Path:
        return self.agent_root() / "registry" / "version.json"

    def system_prompt(self) -> pathlib.Path:
        return self.agent_root() / "registry" / "prompts" / "system_v1.md"

    def report_template(self) -> pathlib.Path:
        return self.agent_root() / "registry" / "report_template.md"

    def python(self) -> pathlib.Path:
        """Interpreter the frozen model subprocess runs under.

        Confined to the workspace venv so a stray system interpreter cannot silently produce
        different (or failed) results. Falls back to the current interpreter only if the venv
        is absent; runtime.py fingerprints whatever this picks and verifies it against the
        declared policy before any result is produced or reused.
        """
        for candidate in self._python_candidates():
            if candidate.exists():
                return candidate
        import sys

        return pathlib.Path(sys.executable)

    def python_source(self) -> str:
        """How python() was chosen: 'workspace_venv' when a workspace venv exists, else
        'current_interpreter' (the unverified fallback the runtime check has to flag)."""
        for candidate in self._python_candidates():
            if candidate.exists():
                return "workspace_venv"
        return "current_interpreter"

    def _python_candidates(self) -> tuple:
        return (
            self.root / ".venv" / "Scripts" / "python.exe",
            self.root / ".venv" / "Scripts" / "python",
            self.root / ".venv" / "bin" / "python",
        )

    def _confine(self, path: pathlib.Path) -> None:
        resolved = path.resolve()
        if self.root.resolve() not in resolved.parents and resolved != self.root.resolve():
            raise ValueError(f"path escapes workspace root: {path}")


def read_json(path: pathlib.Path):
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(tmp, path)


def sha256_hex(path: pathlib.Path) -> str:
    import hashlib

    return hashlib.file_digest(open(path, "rb"), "sha256").hexdigest()