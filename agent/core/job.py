"""Job lifecycle: stages, per-job buckets, dedup, and an append-only audit trace.

The LLM may read state; only this module writes state.json.
"""
from __future__ import annotations

import json
import os
import pathlib
import stat
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from .input_contract import ContractError, describe, parse_and_save
from .paths import STAGES, REPORT_STATES, Workspace, read_json, write_json, sha256_hex

SCHEMA_VERSION = "1.0"
COUNTS_BLOB = "original.json"
PARSED_NAME = "validated.json"
INFERENCE_NAME = "result.json"
COMPARISON_NAME = "comparison.json"
RESULTS_NAME = "results.json"
REPORT_NAME = "report.md"
STATE_NAME = "state.json"
LOG_NAME = "run.log"

INDEX = "index"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _posix(path) -> str:
    """Path as stored JSON: forward slashes, so Windows backslashes never form bad escapes."""
    return str(path).replace("\\", "/")


def _dedup_key(input_sha256: str, adapter: str, package_sha256: str, model_version: str) -> str:
    import hashlib

    payload = f"{input_sha256}|{adapter}|{package_sha256}|{model_version}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_index(workspace: Workspace) -> dict:
    path = workspace.jobs_index()
    if not path.exists():
        return {}
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get(INDEX, {}) if isinstance(data, dict) else {}


def write_index(workspace: Workspace, index: dict) -> None:
    path = workspace.jobs_index()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, {INDEX: index, "updated_at": _utc_now(), "schema_version": SCHEMA_VERSION})


def lookup_dedup(workspace: Workspace, key: str) -> dict | None:
    """Return the cached entry bound to this dedup key, or None.

    A v0.2.4-style index holds a bare job id; migrate it once so the cached result can be
    verified against the current model and adapter instead of being trusted blindly.
    """
    index = read_index(workspace)
    entry = index.get(key)
    if isinstance(entry, str):
        job = Job.open(workspace, entry)
        if job is None:
            del index[key]
            write_index(workspace, index)
            return None
        entry = {
            "job_id": job.job_id,
            "model_version": job.get("model_version"),
            "adapter": job.get("adapter"),
            "package_sha256": job.get("model_package_sha256"),
            "created_at": index.get("updated_at"),
        }
        index[key] = entry
        write_index(workspace, index)
    if not isinstance(entry, dict):
        return None
    adapter = entry.get("adapter")
    if isinstance(adapter, dict):
        entry["adapter"] = f'{adapter.get("name")}:{adapter.get("version")}'
    return entry


def register_dedup(workspace: Workspace, key: str, job_id: str, model_version: str, adapter: str,
                   package_sha256: str) -> None:
    index = read_index(workspace)
    if key not in index:
        index[key] = {
            "job_id": job_id,
            "model_version": model_version,
            "adapter": adapter,
            "package_sha256": package_sha256,
            "created_at": _utc_now(),
        }
        write_index(workspace, index)


class Job:
    """A single analysis task. `open` returns None for unknown ids without creating dirs."""

    def __init__(self, workspace: Workspace, job_id: str):
        self.workspace = workspace
        self.job_id = job_id
        self._dir = workspace.job_dir(job_id)
        self._state: dict | None = None

    # ------------------------------------------------------------------ creation

    @classmethod
    def create(
        cls,
        workspace: Workspace,
        task_file: pathlib.Path,
        model_version: str,
        adapter: str,
        package_sha256: str,
        sample_description: str = "",
    ) -> "Job":
        job_id = uuid.uuid4().hex[:12]
        job = cls(workspace, job_id)
        job.sub("audit")  # ensure the audit bucket exists before any save
        src = task_file.resolve()
        dst = job.sub("input") / task_file.name
        if dst.exists():
            raise ValueError(f"refusing to overwrite existing input artifact {dst}")
        with src.open("rb") as fin, dst.open("wb") as fout:
            while chunk := fin.read(1 << 20):
                fout.write(chunk)
        job._state = {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "created_at": _utc_now(),
            "stage": "received",
            "stage_started_at": _utc_now(),
            "stage_elapsed_s": 0.0,
            "error_code": None,
            "report_state": None,
            "model_version": model_version,
            "input_filename": task_file.name,
            "input_ref": _posix(dst),
            "parsed_ref": _posix(job.sub("parsed") / PARSED_NAME),
            "inference_ref": _posix(job.sub("inference") / INFERENCE_NAME),
            "comparison_ref": None,
            "report_json_ref": None,
            "report_md_ref": None,
            "model_package_sha256": package_sha256,
            "adapter": adapter,
            "interpreter": _posix(workspace.python()),
            "dedup_key": _dedup_key(sha256_hex(dst), adapter, package_sha256, model_version),
            "reused_from": None,
            "comparison_job_id": None,
            "sample_description": sample_description,
            "warnings": [],
            "artifact_refs": [],
        }
        # immutable once staged: strip write permission so nothing downstream can alter it.
        try:
            os.chmod(dst, stat.S_IREAD)
        except OSError:
            pass
        job._state["input_sha256"] = sha256_hex(dst)
        job._state["artifact_refs"] = [_posix(dst)]
        job._append_audit("immutable original copied and made read-only")
        job.save()
        job._start_clock()
        return job

    def _start_clock(self) -> None:
        import time

        self._start = time.perf_counter()

    # ------------------------------------------------------------------- access

    @classmethod
    def open(cls, workspace: Workspace, job_id: str) -> Optional["Job"]:
        state_file = workspace.job_dir(job_id) / "audit" / STATE_NAME
        if not state_file.exists():
            return None
        job = cls(workspace, job_id)
        job._state = read_json(state_file)
        job._start_clock()
        return job

    @property
    def dir(self) -> pathlib.Path:
        return self._dir

    def sub(self, bucket: str) -> pathlib.Path:
        return self.workspace.sub(self.job_id, bucket)

    def log(self) -> pathlib.Path:
        return self.workspace.job_log(self.job_id)

    def stage(self) -> str:
        return self._state["stage"]

    def exists(self) -> bool:
        return self._state is not None

    # ------------------------------------------------------------------- state

    def transition(self, stage: str, error_code: Optional[str] = None) -> None:
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}; allowed {STAGES}")
        if self._state is None:
            raise RuntimeError("job state not loaded")
        prev = self._state["stage"]
        if stage == prev:
            return
        self._state["stage_elapsed_s"] = round(time.perf_counter() - self._start, 3)
        self._state["stage"] = stage
        self._state["stage_started_at"] = _utc_now()
        if error_code is not None:
            self._state["error_code"] = error_code
        self._append_audit(f"stage {prev} -> {stage}" + (f" error={error_code}" if error_code else ""))
        self.save()

    def fail(self, error_code: str) -> None:
        self.transition("failed", error_code)

    def save(self) -> None:
        if self._state is None:
            raise RuntimeError("job state not loaded")
        write_json(self.sub("audit") / STATE_NAME, self._state)

    def add_warning(self, message: str) -> None:
        if message and message not in self._state["warnings"]:
            self._state["warnings"].append(message)
            self.save()

    def append_artifact(self, ref: str) -> None:
        ref = _posix(ref)
        if ref not in self._state["artifact_refs"]:
            self._state["artifact_refs"].append(ref)
            self.save()

    def _append_audit(self, message: str) -> None:
        line = f"{_utc_now()} [{self.job_id}] {message}\n"
        path = self.log()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)

    def as_dict(self) -> dict:
        if self._state is None:
            raise RuntimeError("job state not loaded")
        return dict(self._state)

    def set(self, key: str, value) -> None:
        if self._state is None:
            raise RuntimeError("job state not loaded")
        self._state[key] = value

    def get(self, key, default=None):
        if self._state is None:
            return default
        return self._state.get(key, default)

    # ------------------------------------------------------------------ parsing

    def parse_input(self, original_notes: str = "") -> dict:
        """Validate the immutable original and write the parsed record."""
        original = self.sub("input") / self._state["input_filename"]
        record = parse_and_save(original, self.sub("parsed") / PARSED_NAME, original_notes)
        self._state["input_sha256"] = record["input_sha256"]
        # the record carries provenance; the model only ever sees the bare five fields.
        clean = {k: record[k] for k in ("axis", "signal_unit", "synthetic", "x", "counts")}
        counts_file = self.sub("parsed") / "counts.json"
        write_json(counts_file, clean)
        self._state["model_input_ref"] = _posix(counts_file)
        # the dedup key must be recomputed from the real input hash
        self._state["dedup_key"] = _dedup_key(
            record["input_sha256"], self._state["adapter"],
            self._state["model_package_sha256"], self._state["model_version"])
        self.append_artifact(self._state["parsed_ref"])
        return record

    def describe(self) -> str:
        if self._state is None:
            return ""
        parsed_file = self.sub("parsed") / PARSED_NAME
        if not parsed_file.exists():
            return f"{self._state['input_filename']} (unparsed)"
        try:
            record = read_json(parsed_file)
            return describe(record)
        except (OSError, json.JSONDecodeError, KeyError):
            return f"{self._state['input_filename']} (unparsable)"