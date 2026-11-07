"""Report generation: JSON envelope + Chinese Markdown from the fixed template.

The elements table is derived from the JSON envelope, then re-parsed out of the written
markdown so a program can prove the published numbers still match the numerical result.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import re
import shutil
import time
from typing import Optional

from .job import INFERENCE_NAME, Job
from .paths import Workspace, read_json, write_json, sha256_hex
from .registry import ModelRegistry

SCHEMA_VERSION = "1.0"
TOOL_NAME = "xrf-agent"
TOOL_VERSION = "1.1.0"
REPORTED_UNKNOWN = "未记录"

STAGE_CN = {
    "received": "已接收",
    "validated": "已校验",
    "running": "运行中",
    "succeeded": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "awaiting_input": "待补充输入",
}
REPORT_STATE_CN = {"draft": "草稿", "exported": "已导出", "failed": "失败"}

LIMITATIONS = [
    "32 个元素含量之和**不归一化为 100%**，差额不自动填成氧。",
    "分类概率是分类器原始输出，未经独立校准，不能写成“该含量有 90% 准确率”。",
    "模型未报出**不等于含量为零，也不等于该元素不存在**。",
]
SUPPLEMENTARY = [
    "真实仪器的能量刻度（gain / zero）与响应函数",
    "样品基体与几何条件（粉末 / 块状、测量距离、气氛、测量时间）",
    "可追溯成分标样，用于区分合成研究结果与实测准确度",
]


class ReportError(Exception):
    """A documented report-generation failure. Carries no error_code surface."""


class ReportRollbackError(ReportError):
    """Publication failed and the previous published version could not be fully restored.

    The backup is intentionally left on disk; see ``backup_dir`` for the last good copy.
    """

    def __init__(self, publish_error, backup_dir, failed):
        self.publish_error = str(publish_error)
        self.backup_dir = None if backup_dir is None else str(backup_dir)
        self.failed = dict(failed)
        detail = "; ".join(f"{name}: {reason}" for name, reason in self.failed.items())
        if self.backup_dir:
            msg = (
                f"report publication failed ({self.publish_error}) and the previous "
                f"version could not be fully restored ({detail}). The last good copy is "
                f"kept at {self.backup_dir}; restore it manually before the next export, "
                "which will refuse to overwrite that backup until it is removed."
            )
        else:
            msg = (
                f"report publication failed ({self.publish_error}) and the files created "
                f"by this attempt could not be removed ({detail}). No backup exists for a "
                "first export; remove the listed files before exporting again."
            )
        super().__init__(msg)


def _read_inference(job: Job) -> dict:
    path = job.sub("inference") / INFERENCE_NAME
    if not path.exists():
        raise FileNotFoundError(f"inference artifact missing: {path}")
    return read_json(path)


def _fmt(value: float, reported: bool) -> str:
    return "本模型未报出" if not reported else f"{value:.6f}"


def _fmt_ppm(value: float, reported: bool) -> str:
    return "本模型未报出" if not reported else f"{value:.4f}"


def _parse_number(text: str) -> Optional[float]:
    text = text.strip().strip("（）()").replace(",", "")
    if not text or text == "本模型未报出":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _num_equal(a: str, b: str, tol: float = 1e-6) -> bool:
    fa, fb = _parse_number(a), _parse_number(b)
    if fa is None or fb is None:
        return a.strip() == b.strip()
    return math.isfinite(fa) and math.isfinite(fb) and abs(fa - fb) <= tol


def _between(text: str, start: str, end: str) -> str:
    i = text.find(start)
    j = text.find(end, i) if i != -1 else -1
    if i == -1 or j == -1:
        return ""
    return text[i + len(start):j]


def _table_rows(text: str):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line.strip("|").replace(" ", "")) <= {"-"}:
            continue
        out.append([c.strip() for c in line.strip("|").split("|")])
    return out


def _posix(path) -> str:
    return str(path).replace("\\", "/")


def _registry_json(path: pathlib.Path, what: str) -> dict:
    """Read a registry file that the report depends on. Missing or broken = no report."""
    if not path.exists():
        raise ReportError(f"{what} missing: {path}")
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"{what} unreadable: {path} ({exc})")


def comparison_status(comparison: dict | None) -> str:
    """The report's view of the comparison: not_run / succeeded / failed.

    A comparison artifact belongs to the job it was computed for, so any artifact that
    exists and did not fail counts as this job's own completed comparison.
    """
    if comparison is None:
        return "not_run"
    if comparison.get("error_code"):
        return "failed"
    return "succeeded"


def comparison_status_text(policy: dict, comparison: dict | None) -> str:
    """Short status line for the body. Carries the phrase the suites grep for, nothing more:
    the *policy* itself is stated once, in section 7."""
    status = comparison_status(comparison)
    text = (policy.get("statuses") or {}).get(status) or ""
    if status == "succeeded":
        v9_job_id = (comparison or {}).get("v9_job_id")
        n10 = (comparison or {}).get("n_reported_v10")
        n9 = (comparison or {}).get("n_reported_v9")
        text = (f"V9 对照已完成，关联对照任务 `{v9_job_id}`；"
                f"V10 报出 {n10} 个元素，V9 报出 {n9} 个元素。")
    return text


def comparison_policy_text(policy: dict, comparison: dict | None) -> str:
    """The one place the report states what V9 is for. Read from the registry, never
    improvised by the host, so the report and the session answers share one source."""
    status = comparison_status(comparison)
    parts = [f"- {policy.get('role', 'V10 是主结果，V9 是独立差异参考。')}"]
    for rule in policy.get("rules", []):
        parts.append(f"- {rule}")
    statuses = policy.get("statuses") or {}
    parts.append(f"- 本次对照状态：{statuses.get(status, status)}")
    return "\n".join(parts)


def _fmt_pct(value) -> str:
    return REPORTED_UNKNOWN if value is None else f"{value:.6f}"


def comparison_top_text(comparison: dict | None) -> str:
    """Top-N differences as a small table, straight out of the computed summary."""
    if comparison is None:
        return "未运行 V9 对照，本节不提供差异摘要。"
    summary = comparison.get("comparison_summary") or {}
    if comparison.get("error_code"):
        return "V9 对照失败，本节不提供差异摘要。"
    top = summary.get("top_n") or []
    if not top:
        threshold = summary.get("threshold_ppm")
        threshold_text = f"{threshold:g}" if isinstance(threshold, (int, float)) else ">"
        return (f"两版逐元素一致：没有元素含量差超过比较阈值 {threshold_text} ppm，"
                "没有可列出的差异。")
    lines = ["| 元素 | V10 含量 (%) | V9 含量 (%) | 差值 ppm（V10−V9） | 绝对差 ppm |",
             "|---|---|---|---|---|"]
    for entry in top:
        lines.append(
            f"| {entry['element']} | {_fmt_pct(entry.get('v10_mass_percent'))} | "
            f"{_fmt_pct(entry.get('v9_mass_percent'))} | {entry.get('delta_ppm'):.4f} | "
            f"{entry.get('abs_diff_ppm'):.4f} |")
    groups = summary.get("groups") or {}
    lines.append("")
    lines.append(
        f"仅 V10 报出：{', '.join(groups.get('only_v10_reported') or []) or '无'}；"
        f"仅 V9 报出：{', '.join(groups.get('only_v9_reported') or []) or '无'}；"
        f"两版均报出：{', '.join(groups.get('both_reported') or []) or '无'}。")
    threshold = summary.get("threshold_ppm")
    threshold_text = f"{threshold:g}" if isinstance(threshold, (int, float)) else "未记录"
    lines.append(
        f"上方为差异最大的前 {summary.get('top_n_limit', len(top))} 个元素；"
        f"比较阈值为 {threshold_text} ppm，超过该阈值即计为有差异。"
        "完整差异清单见结构化 JSON 的 differing_elements。"
        "“未报出”不是零含量，也不是元素不存在。")
    return "\n".join(lines)


def runtime_summary(state: dict) -> str:
    """The runtime fingerprint as one report row: what actually ran, and whether it was
    verified against the declared policy."""
    fingerprint = state.get("runtime_fingerprint") or {}
    if not fingerprint:
        return "未记录（本任务未绑定运行环境指纹）"
    versions = " / ".join(f"{name} {fingerprint.get(name, '?')}"
                          for name in ("python", "numpy", "scipy", "xraylib"))
    machine = fingerprint.get("platform") or "?"
    source = fingerprint.get("selection_source")
    source_cn = {"workspace_venv": "工作区虚拟环境",
                 "current_interpreter": "当前解释器（无工作区 venv）"}.get(source, source or "?")
    verified = fingerprint.get("verified")
    if verified is True:
        verdict = "已按声明策略核验"
    elif verified is False:
        verdict = "未通过策略核验（--allow-unverified-runtime 显式放行，结果按未验证记录）"
    else:
        verdict = "核验状态未知"
    return f"{versions}（{machine}，{source_cn}）— {verdict}"


def _timing_text(value) -> str:
    return REPORTED_UNKNOWN if value is None else f"{value:.3f} s"


def timing_block(state: dict, reuse_source: dict | None) -> dict:
    """F05: keep the four clocks apart. `current_request_wall_s` is this job's own wall
    time (creation -> final stage), `inference_wall_s` the model subprocess time, and
    `source_inference_wall_s` the source job's model time when this result was reused.
    A reused job never claims the source's inference time as its own."""
    reused_from = state.get("reused_from")
    if reused_from:
        execution_mode = "缓存复用（未重新推理）"
        inference_wall_s = None
    else:
        execution_mode = "独立运行数值模型"
        inference_wall_s = state.get("elapsed_s")
    source_inference = None
    if reuse_source:
        source_inference = reuse_source.get("inference_wall_s")
    return {
        "execution_mode": execution_mode,
        "current_request_wall_s": state.get("stage_elapsed_s"),
        "inference_wall_s": inference_wall_s,
        "source_inference_wall_s": source_inference,
    }


def _fill(template: str, values: dict) -> str:
    def repl(match):
        key = match.group(1)
        return str(values[key]) if key in values else match.group(0)

    return re.sub(r"\{([a-z0-9_]+)\}", repl, template)


def _build_elements(inference: dict, model: dict, comparison: dict | None) -> list:
    elements = model.get("elements", [])
    predictions = inference.get("predicted_element_percent", {})
    probs = inference.get("classification_probability", {}) or {}
    threshold = model.get("classification_threshold")
    # the comparison carries the full V9 prediction when it ran; differing_elements alone
    # cannot tell "V9 agrees" apart from "V9 did not report".
    v9 = comparison.get("v9_predicted_element_percent", {}) if comparison else {}
    out = []
    for element in elements:
        value = predictions.get(element, 0.0)
        prob = probs.get(element)
        reported = (value > 0) if threshold is None else (prob is not None and prob >= threshold and value > 0)
        entry = {
            "element": element,
            "reported": bool(reported),
            "mass_percent": float(value),
            "mass_percent_ppm": float(value) * 10000.0,
            "classification_probability": (float(prob) if isinstance(prob, (int, float)) and math.isfinite(prob) else None),
            "threshold": threshold,
            "v9_mass_percent": v9.get(element),
            "abs_diff_ppm": None,
        }
        if element in v9 and entry["v9_mass_percent"] is not None:
            entry["abs_diff_ppm"] = abs(value - entry["v9_mass_percent"]) * 10000.0
        out.append(entry)
    return out


def _elements_table(elements, comparison: dict | None) -> str:
    """Data rows only: the template already carries the header and separator."""
    lines = []
    has_comparison = bool(comparison and comparison.get("v9_job_id"))
    for e in elements:
        note = "未运行 V9 对照"
        if has_comparison:
            if e["v9_mass_percent"] is None:
                note = "V9 未报出"
            else:
                note = f"V9={_fmt(e['v9_mass_percent'], e['v9_mass_percent'] > 0)}%，差 {e['abs_diff_ppm']:.2f} ppm"
        lines.append(
            f"| {e['element']} | {'报出' if e['reported'] else '未报出'} | "
            f"{_fmt(e['mass_percent'], e['reported'])} | {_fmt_ppm(e['mass_percent_ppm'], e['reported'])} | {note} |")
    return "\n".join(lines)


def _verify_report_table(markdown: str, elements: list) -> bool:
    section = _between(markdown, "## 2. 候选元素与估计含量", "## 3. 诊断与限制")
    names = {e["element"] for e in elements}
    rows = [row for row in _table_rows(section) if row and row[0] in names]
    if len(rows) != len(elements):
        return False
    for row in rows:
        if len(row) < 5:
            return False
        element = row[0]
        match = [e for e in elements if e["element"] == element]
        if not match:
            return False
        e = match[0]
        if row[1] != ("报出" if e["reported"] else "未报出"):
            return False
        if not _num_equal(row[2], _fmt(e["mass_percent"], e["reported"])):
            return False
        if not _num_equal(row[3], _fmt_ppm(e["mass_percent_ppm"], e["reported"])):
            return False
    return True


def _evidence_index(job: Job, json_path, md_path, comparison: dict | None, inference: dict,
                    include_md: bool = True, hash_paths: dict | None = None,
                    reuse_source: dict | None = None) -> list:
    """Build the published evidence index.

    `json_path` and `md_path` are the *names* the manifest carries: they always point at the
    published locations, so the index stays readable after publication. The SHA-256 is taken
    from the file whose content is authoritative instead, which lets us hash the scratch
    copies while building and prove the published hashes before anything moves.

    `include_md` controls whether the report's own entry is emitted: the manifest file
    (`evidence_manifest.json`) lists both published artifacts, but the Markdown must not
    summarize a version of itself, so the report's own hash is excluded from section 6.
    """
    entries = [
        (job.get("input_ref"), "不可变原始输入"),
        (job.get("parsed_ref"), "校验与解析结果"),
        (job.get("inference_ref"), "数值输出"),
        (job.get("comparison_ref"), "V9 对照输出" if comparison else "未运行"),
        (_posix(json_path), "结构化结果"),
    ]
    if reuse_source:
        entries.append((reuse_source.get("inference_ref"), "复用来源数值输出"))
    if include_md:
        entries.append((_posix(md_path), "Markdown 报告"))
    source = hash_paths or {}
    items = []
    for ref, note in entries:
        if not ref:
            continue
        path = pathlib.Path(ref)
        if not path.is_absolute():
            path = job.workspace.root / path
        target = source.get(ref, path)
        items.append({
            "artifact": ref,
            "sha256": sha256_hex(target) if target.exists() else None,
            "note": note,
        })
    return items


def _write_manifest(manifest_path: pathlib.Path, manifest: list) -> None:
    """Persist the evidence manifest next to the report, so it survives publication."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _back_up_existing(targets, report_dir) -> tuple[pathlib.Path | None, set[str]]:
    """Snapshot the published triset before the atomic commit replaces it.

    Only used to roll back a *partial* commit: the whole candidate lives in scratch until
    the commit, so every failure before it leaves the published files untouched. Returns
    the backup directory, if any, and the names that were already on disk, so a failed
    commit can both restore the old files and drop the ones it created.

    A leftover recovery backup is never overwritten: it carries a RECOVERY_NEEDED.json the
    publishing tooling cannot rebuild, so the export stops before touching the triset.
    """
    # a recovery backup from an earlier failure is still waiting for a manual pick;
    # it is not a usable snapshot and must not be silently replaced.
    leftover = report_dir / ".backup_old"
    if leftover.exists() and any((leftover / n).exists() for n in _TRIO):
        raise ReportError(
            f"cannot publish the report: {leftover} still holds the previous version and an "
            f"unprocessed recovery note. Copy the old files back from {leftover} into the "
            f"report directory and delete {leftover}; the next export will refuse to "
            "overwrite that backup until it is removed."
        )

    backup_dir = None
    existed = set()
    for target in targets:
        if target.exists():
            existed.add(target.name)
            if backup_dir is None:
                backup_dir = report_dir / ".backup_old"
                backup_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(target, backup_dir / target.name)
            except OSError as exc:
                # leave no half-written snapshot behind: the un-backed-up files are still
                # publishing on the side while the candidate is still in scratch.
                shutil.rmtree(backup_dir, ignore_errors=True)
                raise ReportError(
                    f"failed to snapshot the published triset: "
                    f"{type(exc).__name__}: {exc} ({backup_dir}); delete the partial "
                    "backup and export again, otherwise this error repeats"
                ) from exc
    return backup_dir, existed


_TRIO = ("results.json", "report.md", "evidence_manifest.json")


def _restore_from_backup(backup_dir, existed, report_dir):
    """Undo a partial commit. Returns (restored, failed); never hides a failure.

    A file is only counted as restored after its hash matches the backup copy, so a
    copy that raised no exception but wrote garbage is still reported. Each name is
    attempted independently: one failure does not stop the others.
    """
    restored, failed = [], {}
    for name in _TRIO:
        dst = report_dir / name
        if name in existed:
            src = None if backup_dir is None else backup_dir / name
            if src is None or not src.exists():
                failed[name] = "backup copy is missing"
                continue
            try:
                shutil.copy2(src, dst)
                if sha256_hex(src) != sha256_hex(dst):
                    failed[name] = "restored file hash does not match the backup"
                else:
                    restored.append(name)
            except OSError as exc:
                failed[name] = f"{type(exc).__name__}: {exc}"
        elif dst.exists():
            try:
                dst.unlink()
                restored.append(name)
            except OSError as exc:
                failed[name] = f"{type(exc).__name__}: {exc}"
    return restored, failed


def _write_recovery_report(backup_dir, publish_error, failed):
    """Record what went wrong and how to recover, inside the backup directory.

    `publish_error` is the publication failure that triggered the write, `failed_restores`
    lists the names the restore could not recover, and `files` records the SHA-256 of the
    backup copies so a manual recovery can be verified afterwards. Returns the report
    path, or None if it could not be written.
    """
    payload = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "publish_error": str(publish_error),
        "failed_restores": failed,
        "backup_dir": _posix(backup_dir),
        "files": {
            n: sha256_hex(backup_dir / n)
            for n in _TRIO if (backup_dir / n).exists()
        },
        "manual_recovery": (
            "copy each file from backup_dir into the report directory, verify the sha256 "
            "above, then delete backup_dir"
        ),
    }
    path = backup_dir / "RECOVERY_NEEDED.json"
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return None
    return path


def build_report(job: Job, comparison: dict | None = None, warnings: Optional[list] = None) -> dict:
    """Write the JSON envelope and Markdown report; return paths plus a consistency flag.

    Everything is built in a private scratch directory first. A failed consistency check
    leaves no published artifact; the published hashes are computed after the envelope is
    final and recorded in a separate manifest, so the report never has to summarize a
    version of itself that did not yet exist.
    """
    workspace = job.workspace
    registry = ModelRegistry(workspace)
    model = registry.model(job.get("model_version"))
    adapter = registry.adapter()
    state = job.as_dict()
    inference = _read_inference(job)
    policy = _registry_json(workspace.comparison_policy(), "comparison policy")
    versions = _registry_json(workspace.version_metadata(), "version metadata")

    elements = _build_elements(inference, model, comparison)

    reused_from = state.get("reused_from")
    reuse_source = None
    if reused_from:
        source = Job.open(workspace, reused_from)
        if source is not None:
            source_state = source.as_dict()
            reuse_source = {
                "job_id": reused_from,
                "model_version": source_state.get("model_version"),
                "input_sha256": source_state.get("input_sha256"),
                "model_package_sha256": source_state.get("model_package_sha256"),
                "created_at": source_state.get("created_at"),
                "inference_ref": source_state.get("inference_ref"),
                "inference_wall_s": source_state.get("elapsed_s"),
            }
            reuse_note = (
                f"本次复用任务 `{reused_from}` 的计算结果（未重新推理）；来源模型 "
                f"{reuse_source['model_version']}，来源输入 SHA-256 "
                f"`{reuse_source['input_sha256']}`，模型包 SHA-256 "
                f"`{reuse_source['model_package_sha256']}`。本任务输入哈希与来源一致。")
        else:
            reuse_note = (f"本次复用任务 `{reused_from}` 的计算结果（未重新推理）；"
                          "来源任务状态不可读，仅保留任务号。")
    else:
        reuse_note = "本次独立运行数值模型，未复用旧任务。"

    timing = timing_block(state, reuse_source)
    agent_version = versions.get("agent_version") or "未记录"
    agent_display_version = versions.get("agent_display_version") or f"V{agent_version}"
    generator_version = versions.get("report_generator_version") or TOOL_VERSION
    report_schema_version = versions.get("report_schema_version") or SCHEMA_VERSION
    source_commit = versions.get("source_commit") or None
    comp_status = comparison_status(comparison)

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "status": STAGE_CN.get(state["stage"], state["stage"]),
        "report_state": REPORT_STATE_CN.get(state.get("report_state"), "草稿"),
        "job_id": state["job_id"],
        "created_at": state.get("created_at"),
        "input_sha256": state.get("input_sha256"),
        "input_ref": state.get("input_ref"),
        "model_version": state.get("model_version"),
        "model_revision": model.get("revision"),
        "model_package_sha256": state.get("model_package_sha256"),
        "adapter_name": adapter.get("name"),
        "adapter_version": adapter.get("version"),
        "interpreter": state.get("interpreter"),
        "runtime_id": state.get("runtime_id"),
        "runtime_verified": state.get("runtime_verified"),
        "runtime_fingerprint": state.get("runtime_fingerprint"),
        "execution_mode": timing["execution_mode"],
        "current_request_wall_s": timing["current_request_wall_s"],
        "inference_wall_s": timing["inference_wall_s"],
        "source_inference_wall_s": timing["source_inference_wall_s"],
        "agent_version": agent_version,
        "agent_display_version": agent_display_version,
        "report_generator_name": versions.get("report_generator_name") or TOOL_NAME,
        "report_generator_version": generator_version,
        "report_schema_version": report_schema_version,
        "source_commit": source_commit,
        "scope": inference.get("scope"),
        "formal_report_eligible": bool(inference.get("formal_report_eligible")),
        "hardware_validated": bool(inference.get("hardware_validated")),
        "sample_description": state.get("sample_description"),
        "elapsed_s": state.get("elapsed_s"),
        "error_code": state.get("error_code"),
        "reused_from": reused_from,
        "reuse_source": reuse_source,
        "comparison_status": comp_status,
        "comparison_policy": {
            "primary_model": policy.get("primary_model"),
            "reference_model": policy.get("reference_model"),
            "role": policy.get("role"),
            "rules": list(policy.get("rules", [])),
        },
        "comparison_job_id": state.get("comparison_job_id"),
        "warnings": list(state.get("warnings", []) + (warnings or [])),
        "artifact_refs": list(state.get("artifact_refs", [])),
        "elements": elements,
        "axis_diagnostics": inference.get("axis_diagnostics"),
        "comparison": comparison,
    }

    report_dir = job.sub("report")
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "results.json"
    md_path = report_dir / "report.md"

    scratch = report_dir / ".tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    tmp_json = scratch / "results.json"
    tmp_md = scratch / "report.md"

    template = workspace.report_template().read_text(encoding="utf-8")
    diagnostics = json.dumps(inference.get("axis_diagnostics"), ensure_ascii=False, indent=2)
    if not inference.get("axis_diagnostics"):
        diagnostics = "模型未返回刻度诊断信息。"
    limitations = "\n".join(f"- {LIMITATIONS[i]}" for i in range(len(LIMITATIONS)))
    if model.get("cannot_infer"):
        limitations += f"\n- {model['cannot_infer']}"
    supplementary = "\n".join(f"- {SUPPLEMENTARY[i]}" for i in range(len(SUPPLEMENTARY)))
    comparison_note = comparison_status_text(policy, comparison)
    analyst_note = (
        f"本报告为**研究分析草稿**（formal_report_eligible={envelope['formal_report_eligible']}，"
        f"hardware_validated={envelope['hardware_validated']}），不构成定量验收结论，"
        f"不代表任何误差目标已经通过。{comparison_note}"
        f"V9 的角色、对照策略与差异摘要在第 7 节统一说明，正文不重复。"
    )

    markdown = _fill(template, {
        "job_id": state["job_id"],
        "created_at": state.get("created_at", ""),
        "input_sha256": state.get("input_sha256", ""),
        "model_version": state.get("model_version", ""),
        "model_revision": model.get("revision", ""),
        "model_package_sha256": state.get("model_package_sha256", ""),
        "adapter_name": adapter.get("name", ""),
        "adapter_version": adapter.get("version", ""),
        "runtime_summary": runtime_summary(state),
        "reuse_note": reuse_note,
        "status": STAGE_CN.get(state["stage"], state["stage"]),
        "sample_description": state.get("sample_description") or "（无）",
        "elements_table": _elements_table(elements, comparison),
        "diagnostics": f"```\n{diagnostics}\n```",
        "limitations": limitations,
        "supplementary_info_needed": supplementary,
        "analyst_note": analyst_note,
        "input_ref": state.get("input_ref", ""),
        "parsed_ref": state.get("parsed_ref", ""),
        "inference_ref": state.get("inference_ref", ""),
        "axis_diagnostics": diagnostics,
        "comparison_note": comparison_note,
        "execution_mode": timing["execution_mode"],
        "current_request_wall_s": _timing_text(timing["current_request_wall_s"]),
        "inference_wall_s": _timing_text(timing["inference_wall_s"]),
        "source_inference_wall_s": _timing_text(timing["source_inference_wall_s"]),
        "comparison_policy_text": comparison_policy_text(policy, comparison),
        "comparison_top_text": comparison_top_text(comparison),
        "elapsed_s": str(state.get("elapsed_s", "")),
        "error_code": str(state.get("error_code") or "无"),
        "evidence_index": "{evidence_index}",
        "tool_name": TOOL_NAME,
        "tool_version": generator_version,
        "agent_version": agent_version,
        "agent_display_version": agent_display_version,
        "report_schema_version": report_schema_version,
        "consistency_check": "{consistency_check}",
    })

    # 1. write the draft envelope and the draft report into the scratch directory
    write_json(tmp_json, envelope)
    tmp_md.write_text(markdown, encoding="utf-8")

    # 2. the consistency check runs against the draft; the report is not published yet
    consistency = _verify_report_table(markdown, elements)
    if not consistency:
        shutil.rmtree(scratch, ignore_errors=True)
        raise ReportError(
            "generated Markdown table does not match the numerical result; refusing to publish")

    # 3. the envelope is now final, so its hash and the report hash can be recorded
    envelope["consistency_check"] = bool(consistency)
    write_json(tmp_json, envelope)

    # 4. the whole triset -- JSON, Markdown, manifest -- is built inside the scratch
    #    directory. Nothing outside scratch is touched until the commit, so a failure at any
    #    point leaves the previously published version byte-identical.
    manifest_path = report_dir / "evidence_manifest.json"
    tmp_manifest = scratch / "evidence_manifest.json"

    def _manifest(hashed):
        # the manifest names the published files but hashes the scratch copies: the content
        # is identical once committed, and only a final file has a trustworthy hash.
        return _evidence_index(job, json_path, md_path, comparison, inference,
                               include_md=True, hash_paths=hashed,
                               reuse_source=reuse_source)

    section_manifest = [m for m in _manifest({_posix(json_path): tmp_json, _posix(md_path): tmp_md})
                        if not m["artifact"].endswith("report.md")]
    markdown = _fill(markdown, {
        "consistency_check": "通过" if consistency else "不一致",
        "evidence_index": "\n".join(
            f"- `{m['artifact']}` — {m['note']}，SHA-256 `{m['sha256']}`"
            for m in section_manifest),
    })
    tmp_md.write_text(markdown, encoding="utf-8")

    final_manifest = _manifest({_posix(json_path): tmp_json, _posix(md_path): tmp_md})
    # the manifest is what section 6 quotes, so re-deriving section 6 from it must reproduce
    # the Markdown we just wrote; otherwise the published report would summarize a manifest
    # it does not match.
    non_md = [m for m in final_manifest if not m["artifact"].endswith("report.md")]
    if non_md != section_manifest:
        shutil.rmtree(scratch, ignore_errors=True)
        raise ReportError("evidence index does not match the generated report")

    # 6. commit atomically: the three published files move together, or not at all.
    #    the manifest is written into scratch first, so a failure here leaves no trace.
    backups, existed = _back_up_existing((json_path, md_path, manifest_path), report_dir)
    keep_backup = False
    try:
        _write_manifest(tmp_manifest, final_manifest)
        os.replace(tmp_json, json_path)
        os.replace(tmp_md, md_path)
        os.replace(tmp_manifest, manifest_path)
    except OSError as e:
        restored, failed = _restore_from_backup(backups, existed, report_dir)
        if failed:
            # the last published copy is not yet restored, so it stays on disk and a
            # recovery report points at it: the operator has to intervene before
            # publishing again.
            keep_backup = True
            if backups is not None:
                _write_recovery_report(backups, e, failed)
            raise ReportRollbackError(e, backups, failed) from e
        raise ReportError(f"failed to publish the report atomically: {e}") from e
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if backups is not None and not keep_backup:
            shutil.rmtree(backups, ignore_errors=True)

    return {
        "markdown": markdown,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "consistency_check": bool(consistency),
        "warnings": [],
    }