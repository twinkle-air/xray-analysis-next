"""The four documented tool interfaces.

These are the only entry points that touch jobs or the frozen backend. They return
versioned envelopes; every failure path carries an explicit error_code and never
publishes a content guess.
"""
from __future__ import annotations

import json
import math
import pathlib
import shutil
from typing import Optional

from .input_contract import ContractError
from .job import (
    COMPARISON_NAME, COUNTS_BLOB, INFERENCE_NAME, Job, Job as _Job, lookup_dedup, register_dedup,
    _posix,
)
from .paths import Workspace, read_json, write_json, sha256_hex
from .registry import ModelRegistry, RegistryError
from .runner import RunResult, run_model

SCHEMA_VERSION = "1.0"
THRESHOLD_DEFAULT = 0.9


class ToolError(Exception):
    """A documented tool contract was broken. Carries the error_code surface to the caller."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ validation


def _constrain(workspace: Workspace, task_file: pathlib.Path) -> pathlib.Path:
    raw = pathlib.Path(task_file)
    # a relative path is resolved against the workspace root, never the caller's cwd
    resolved = raw.resolve() if raw.is_absolute() else (workspace.root / raw).resolve()
    root = workspace.root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ToolError("PATH_TRAVERSAL", f"task file escapes the workspace: {task_file}")
    if not resolved.is_file():
        raise ToolError("NOT_FOUND", f"task file does not exist: {task_file}")
    return resolved


def _check_inference(result: dict, model: dict, version: str) -> None:
    """Validate shape, element set and finiteness. Raises ToolError on any mismatch."""
    if result.get("version") != version:
        raise ToolError(
            "NUMERICAL_FAILURE",
            f"published result version {result.get('version')!r}, expected {version!r}")
    predictions = result.get("predicted_element_percent")
    if not isinstance(predictions, dict):
        raise ToolError("NUMERICAL_FAILURE", "result has no element predictions")
    expected = model.get("elements", [])
    if set(predictions) != set(expected):
        missing = sorted(set(expected) - set(predictions))
        extra = sorted(set(predictions) - set(expected))
        raise ToolError(
            "NUMERICAL_FAILURE",
            f"element set mismatch: missing {missing}, unexpected {extra}")
    for element, value in predictions.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ToolError(
                "NUMERICAL_FAILURE", f"non-finite prediction for {element}: {value!r}")
    probs = result.get("classification_probability")
    if isinstance(probs, dict) and set(probs) != set(expected):
        raise ToolError(
            "NUMERICAL_FAILURE", f"classification_probability covers {len(probs)} of {len(expected)} elements")


def _read_inference(job: Job) -> dict:
    path = job.sub("inference") / INFERENCE_NAME
    if not path.exists():
        raise FileNotFoundError(f"inference artifact missing: {path}")
    return read_json(path)


# ------------------------------------------------------------------ envelopes


def _envelope(job: _Job, elapsed_s: Optional[float] = None) -> dict:
    state = job.as_dict()
    return {
        "schema_version": SCHEMA_VERSION,
        "status": state["stage"],
        "job_id": state["job_id"],
        "input_sha256": state["input_sha256"],
        "model_version": state["model_version"],
        "model_package_sha256": state["model_package_sha256"],
        "warnings": list(state["warnings"]),
        "error_code": state["error_code"],
        "elapsed_s": round(elapsed_s, 3) if elapsed_s is not None else state.get("stage_elapsed_s"),
    }


# ------------------------------------------------------------------ dedup


def _reuse_if_valid(workspace: Workspace, entry: dict, job: Job, model_version: str) -> Job | None:
    """Reuse a cached result only when the cache itself and the current package still agree.

    Returns the job whose result was copied, or None when the cache must not be trusted.
    """
    existing = Job.open(workspace, entry["job_id"])
    if existing is None or existing.stage() != "succeeded":
        return None
    if existing.get("model_version") != model_version:
        return None
    if existing.get("adapter") != job.get("adapter"):
        return None
    if existing.get("model_package_sha256") != job.get("model_package_sha256"):
        return None
    if existing.get("input_sha256") != job.get("input_sha256"):
        return None

    cached = existing.sub("inference") / INFERENCE_NAME
    if not cached.exists():
        return None
    if _posix(cached) not in existing.get("artifact_refs", []):
        return None
    if sha256_hex(cached) != existing.get("inference_sha256"):
        return None

    try:
        result = read_json(cached)
        _check_inference(result, ModelRegistry(workspace).model(model_version), model_version)
    except (OSError, json.JSONDecodeError, ToolError):
        job.add_warning(f"dedup cache {entry['job_id']} is damaged; recomputing")
        return None

    dst = job.sub("inference") / INFERENCE_NAME
    shutil.copy2(cached, dst)
    job.set("reused_from", entry["job_id"])
    job.set("input_sha256", existing.get("input_sha256"))
    job.append_artifact(str(dst))
    job.log().write_text(f"reused result of {entry['job_id']} (dedup key match, cache verified)\n", encoding="utf-8")
    job.transition("succeeded")
    return job


# ------------------------------------------------------------------ tools


def analyze_spectrum(
    workspace: Workspace, task_file: pathlib.Path, sample_description: str = ""
) -> dict:
    """Ingest a spectrum, validate it, lock the version and run V10. Never overwrites."""
    task_file = _constrain(workspace, task_file)
    registry = ModelRegistry(workspace)
    model_version = registry.default_model
    model = registry.model(model_version)
    package_sha = registry.package_sha(model_version)
    adapter = registry.adapter()

    # the package is verified before any result is trusted; a tampered or incomplete
    # installation fails closed instead of serving a stale cached value.
    try:
        integrity = registry.verify_package(model_version)
    except RegistryError as exc:
        job = Job.create(workspace, task_file, model_version, f'{adapter["name"]}:{adapter["version"]}', package_sha, sample_description)
        job.fail("INTEGRITY_FAILED")
        job.add_warning(str(exc))
        return _envelope(job)
    if not integrity["ok"]:
        bad = ", ".join(f"{rel} ({status})" for rel, _, status in integrity["mismatches"][:3])
        job = Job.create(workspace, task_file, model_version, f'{adapter["name"]}:{adapter["version"]}', package_sha, sample_description)
        job.fail("INTEGRITY_FAILED")
        job.add_warning(f"model package integrity check failed for {model_version}: {bad} "
                        f"({integrity['checked']} files, {len(integrity['mismatches'])} mismatches)")
        return _envelope(job)

    job = Job.create(workspace, task_file, model_version, f'{adapter["name"]}:{adapter["version"]}', package_sha, sample_description)
    try:
        job.parse_input(sample_description)
    except ContractError as exc:
        job.fail(exc.code)
        job.add_warning(str(exc))
        return _envelope(job)

    entry = lookup_dedup(workspace, job.get("dedup_key"))
    if entry is not None:
        existing = _reuse_if_valid(workspace, entry, job, model_version)
        if existing is not None:
            return _envelope(existing)
    register_dedup(workspace, job.get("dedup_key"), job.job_id, model_version, adapter, package_sha)

    job.transition("running")
    counts_file = pathlib.Path(job.get("model_input_ref"))
    out = job.sub("inference") / INFERENCE_NAME
    if out.exists():
        out.unlink()
    try:
        run: RunResult = run_model(workspace, model_version, counts_file, out)
    except OSError as exc:
        job.fail("INTEGRITY_FAILED")
        job.add_warning(str(exc))
        return _envelope(job)

    if run["error_code"]:
        job.fail(run["error_code"])
        job.add_warning(run["stderr"][-600:])
        return _envelope(job, run["wall_s"])

    try:
        result = _read_inference(job)
        _check_inference(result, model, model_version)
    except (ToolError, OSError, json.JSONDecodeError) as exc:
        job.fail("NUMERICAL_FAILURE")
        job.add_warning(str(exc))
        return _envelope(job, run["wall_s"])

    job.set("inference_sha256", sha256_hex(job.sub("inference") / INFERENCE_NAME))
    job.set("elapsed_s", run["wall_s"])
    job.append_artifact(str(job.sub("inference") / INFERENCE_NAME))
    job.transition("succeeded")
    return _envelope(job, run["wall_s"])


def get_job_status(workspace: Workspace, job_id: str) -> dict:
    """Return stage, elapsed time, error code and artifact refs. Unknown ids stay unknown."""
    job = Job.open(workspace, job_id)
    if job is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "stage": None,
            "stage_elapsed_s": None,
            "error_code": "NOT_FOUND",
            "artifact_refs": [],
            "exists": False,
        }
    state = job.as_dict()
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "stage": state["stage"],
        "stage_elapsed_s": state.get("stage_elapsed_s"),
        "error_code": state.get("error_code"),
        "artifact_refs": list(state.get("artifact_refs", [])),
        "exists": True,
    }


def compare_models(workspace: Workspace, job_id: str) -> dict:
    """Run V9 once on the same input as a completed V10 job. Does not replace V10."""
    registry = ModelRegistry(workspace)
    v10 = registry.model("V10")
    v9 = registry.model("V9")
    v9_package_sha = registry.package_sha("V9")
    adapter = registry.adapter()

    job = Job.open(workspace, job_id)
    if job is None:
        raise ToolError("NOT_FOUND", f"no job {job_id}")
    if job.stage() != "succeeded":
        raise ToolError(
            "CONTRACT_VIOLATION",
            f"compare_models requires a succeeded job, stage={job.stage()}")
    if job.get("model_version") != "V10":
        raise ToolError(
            "CONTRACT_VIOLATION",
            f"compare_models requires a V10 job, model={job.get('model_version')!r}")

    existing_comparison = job.sub("inference") / COMPARISON_NAME
    if existing_comparison.exists():
        try:
            comp = read_json(existing_comparison)
            return {k: comp[k] for k in (
                "job_id", "v9_job_id", "v9_status", "n_reported_v10", "n_reported_v9",
                "differing_elements", "error_code", "note")}
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            raise ToolError("NUMERICAL_FAILURE", f"comparison artifact unreadable: {exc}")

    # V9 runs on the same five-field counts; write a minimal file so validation passes.
    counts = read_json(job.sub("parsed") / "validated.json")
    minimal = {k: counts[k] for k in ("axis", "signal_unit", "synthetic", "x", "counts")}
    compare_dir = job.sub("input")
    compare_dir.mkdir(parents=True, exist_ok=True)
    counts_file = compare_dir / COUNTS_BLOB
    write_json(counts_file, minimal)

    v9_job = Job.create(
        workspace, counts_file, "V9", f'{adapter["name"]}:{adapter["version"]}', v9_package_sha,
        sample_description=f"V9对照 for job {job_id}")
    try:
        v9_job.parse_input(f"V9对照 for job {job_id}")
        v9_job.transition("running")
        v9_out = v9_job.sub("inference") / INFERENCE_NAME
        if v9_out.exists():
            v9_out.unlink()
        v9_run = run_model(workspace, "V9", pathlib.Path(v9_job.get("model_input_ref")), v9_out)
        if v9_run["error_code"]:
            v9_job.fail(v9_run["error_code"])
            v9_job.add_warning(v9_run["stderr"][-600:])
            v9_job.save()
            return _compare_result(job.job_id, None, None, None, None, [], "V9对照失败",
                                   v9_run["error_code"])
        v9_result = _read_inference(v9_job)
        _check_inference(v9_result, v9, "V9")
        v9_job.set("elapsed_s", v9_run["wall_s"])
        v9_job.append_artifact(str(v9_out))
        v9_job.transition("succeeded")
    except (ToolError, ContractError, OSError) as exc:
        v9_job.fail(getattr(exc, "code", "NUMERICAL_FAILURE"))
        v9_job.add_warning(str(exc))
        return _compare_result(job.job_id, None, None, None, None, [],
                               f"V9对照准备失败: {exc}", getattr(exc, "code", "NUMERICAL_FAILURE"))

    differing, note = _diff(v10, v9, _read_inference(job), v9_result)
    comparison = {
        "job_id": job_id,
        "v9_job_id": v9_job.job_id,
        "v9_status": v9_job.stage(),
        "n_reported_v10": _n_reported(_read_inference(job)),
        "n_reported_v9": _n_reported(v9_result),
        "differing_elements": differing,
        "error_code": None,
        "note": note,
        # the full V9 result, so the report can show "V9 agrees" instead of "V9 did not report"
        # when the two versions happen to match.
        "v9_predicted_element_percent": v9_result.get("predicted_element_percent", {}),
    }
    write_json(existing_comparison, comparison)
    job.set("comparison_job_id", v9_job.job_id)
    job.set("comparison_ref", _posix(existing_comparison))
    job.append_artifact(str(existing_comparison))
    job.save()
    return _compare_result(job.job_id, v9_job.job_id, v9_job.stage(),
                           comparison["n_reported_v10"], comparison["n_reported_v9"],
                           differing, note, None)


def export_report(
    workspace: Workspace, job_id: str, include_comparison: bool = False
) -> dict:
    """Emit structured JSON and a Chinese Markdown report, then check they agree."""
    job = Job.open(workspace, job_id)
    if job is None:
        raise ToolError("NOT_FOUND", f"no job {job_id}")
    if job.stage() != "succeeded":
        raise ToolError(
            "CONTRACT_VIOLATION",
            f"export_report requires a succeeded job, stage={job.stage()}")

    from .reporting import build_report, ReportError

    try:
        comparison = None
        comp_path = job.sub("inference") / COMPARISON_NAME
        if comp_path.exists():
            comparison = read_json(comp_path)
            if include_comparison and comparison.get("error_code") is not None:
                raise ToolError(
                    "CONTRACT_VIOLATION",
                    "include_comparison requires a completed compare_models run; comparison failed")
        elif include_comparison:
            raise ToolError(
                "CONTRACT_VIOLATION",
                "include_comparison requires a completed compare_models run; none found")
        result = build_report(job, comparison=comparison)
    except ReportError as exc:
        job.set("report_state", "failed")
        job.add_warning(str(exc))
        job.save()
        return {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "markdown": "",
            "json_path": "",
            "markdown_path": "",
            "status": "failed",
            "consistency_check": False,
            "warnings": [f"report generation failed: {exc}"],
            "error_code": "NUMERICAL_FAILURE",
        }
    except ToolError:
        raise
    except Exception as exc:
        job.set("report_state", "failed")
        job.add_warning(f"report generation failed: {exc}")
        job.save()
        return {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "markdown": "",
            "json_path": "",
            "markdown_path": "",
            "status": "failed",
            "consistency_check": False,
            "warnings": [f"report generation failed: {exc}"],
            "error_code": "NUMERICAL_FAILURE",
        }

    job.set("report_state", "exported")
    job.set("report_json_ref", _posix(result["json_path"]))
    job.set("report_md_ref", _posix(result["markdown_path"]))
    job.append_artifact(result["json_path"])
    job.append_artifact(result["markdown_path"])
    job.save()
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "markdown": result["markdown"],
        "json_path": result["json_path"],
        "markdown_path": result["markdown_path"],
        "status": "exported",
        "consistency_check": result["consistency_check"],
        "warnings": list(result.get("warnings", [])),
        "error_code": None,
    }


# ------------------------------------------------------------------ comparison


def _n_reported(result: dict) -> int:
    return sum(1 for v in result.get("predicted_element_percent", {}).values() if v > 0)


def _diff(v10_model: dict, v9_model: dict, v10_result: dict, v9_result: dict):
    elements = v10_model.get("elements", [])
    v10 = v10_result.get("predicted_element_percent", {})
    v9 = v9_result.get("predicted_element_percent", {})
    differing = []
    n = 0
    for element in elements:
        a = v10.get(element, 0.0)
        b = v9.get(element, 0.0)
        diff_pp = abs(a - b) * 10000.0
        if diff_pp > 1e-6:
            differing.append({
                "element": element,
                "v10_mass_percent": a,
                "v9_mass_percent": b,
                "abs_diff_ppm": round(diff_pp, 6),
            })
            n += 1
    reported_v10 = _n_reported(v10_result)
    reported_v9 = _n_reported(v9_result)
    note = (
        f"V9对照已完成：V10 报出 {reported_v10} 个元素，V9 报出 {reported_v9} 个元素。"
        f"{n} 个元素两版含量差 > 0 ppm。"
        + (" 两版均报出的元素差异最大者见 differing_elements。" if n else " 两版逐元素一致。")
        + " V9 不是真值，一致不代表结果正确。")
    return differing, note


def _compare_result(job_id, v9_job_id, v9_status, n10, n9, differing, note, error_code):
    return {
        "job_id": job_id,
        "v9_job_id": v9_job_id,
        "v9_status": v9_status,
        "n_reported_v10": n10,
        "n_reported_v9": n9,
        "differing_elements": differing,
        "error_code": error_code,
        "note": note,
    }