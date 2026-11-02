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
from typing import Optional

from .job import INFERENCE_NAME, Job
from .paths import Workspace, read_json, write_json, sha256_hex
from .registry import ModelRegistry

SCHEMA_VERSION = "1.0"
TOOL_NAME = "xrf-agent"
TOOL_VERSION = "1.0.0-p1"

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
    pass


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
                    include_md: bool = True, hash_paths: dict | None = None) -> list:
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


def _back_up_existing(targets, report_dir) -> pathlib.Path | None:
    """Snapshot the published triset before the atomic commit replaces it.

    Only used to roll back a *partial* commit: the whole candidate lives in scratch until
    the commit, so every failure before it leaves the published files untouched.
    """
    backup_dir = None
    for target in targets:
        if target.exists():
            if backup_dir is None:
                backup_dir = report_dir / ".backup_old"
                backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_dir / target.name)
    return backup_dir


def _restore_from_backup(backup_dir: pathlib.Path | None, report_dir) -> None:
    if backup_dir is None or not backup_dir.exists():
        return
    for name in ("results.json", "report.md", "evidence_manifest.json"):
        src = backup_dir / name
        if src.exists():
            try:
                shutil.copy2(src, report_dir / name)
            except OSError:
                pass


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

    elements = _build_elements(inference, model, comparison)

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
        "scope": inference.get("scope"),
        "formal_report_eligible": bool(inference.get("formal_report_eligible")),
        "hardware_validated": bool(inference.get("hardware_validated")),
        "sample_description": state.get("sample_description"),
        "elapsed_s": state.get("elapsed_s"),
        "error_code": state.get("error_code"),
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
    comparison_note = (
        f"V9 对照已完成，任务编号 `{comparison['v9_job_id']}`。"
        f"V10 报出 {comparison['n_reported_v10']} 个元素，V9 报出 {comparison['n_reported_v9']} 个元素；"
        f"{len(comparison.get('differing_elements', []))} 个元素两版含量不同。"
        if comparison else "未运行 V9 对照。用户请求或登记规则触发时才会调用 V9，V9 不是真值。"
    )
    analyst_note = (
        f"本报告为**研究分析草稿**（formal_report_eligible={envelope['formal_report_eligible']}，"
        f"hardware_validated={envelope['hardware_validated']}），不构成定量验收结论，"
        f"不代表任何误差目标已经通过。{comparison_note}"
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
        "elapsed_s": str(state.get("elapsed_s", "")),
        "error_code": str(state.get("error_code") or "无"),
        "evidence_index": "{evidence_index}",
        "tool_name": TOOL_NAME,
        "tool_version": TOOL_VERSION,
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
                               include_md=True, hash_paths=hashed)

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
    backups = _back_up_existing((json_path, md_path, manifest_path), report_dir)
    try:
        _write_manifest(tmp_manifest, final_manifest)
        os.replace(tmp_json, json_path)
        os.replace(tmp_md, md_path)
        os.replace(tmp_manifest, manifest_path)
    except OSError as e:
        _restore_from_backup(backups, report_dir)
        raise ReportError(f"failed to publish the report atomically: {e}") from e
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if backups is not None:
            shutil.rmtree(backups, ignore_errors=True)

    return {
        "markdown": markdown,
        "json_path": str(json_path),
        "markdown_path": str(md_path),
        "consistency_check": bool(consistency),
        "warnings": [],
    }
