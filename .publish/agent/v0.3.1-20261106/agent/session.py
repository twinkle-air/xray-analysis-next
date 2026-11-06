"""Multi-turn session over one spectrum and one main job.

The session owns the conversation state the CLI used to throw away after every turn:
the spectrum, the main job id and the V9 comparison job id. Follow-up answers read the
existing result instead of re-running the model, and a V9 comparison is bound to the
main job rather than to a newly analysed task.
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone
from typing import Optional

from .core.job import Job
from .core.paths import Workspace, read_json, write_json
from .core.registry import ModelRegistry
from .core.tools import ToolError, compare_models, export_report
from .host import HostConfig, config_summary, detect_config, host_reply_unusable
from .orchestrator import OrchestrationError, _result_digest, follow_up, orchestrate

SESSION_SCHEMA = "1.0"

ELEMENT_NAMES_CN = {
    "Na": "钠", "Mg": "镁", "Al": "铝", "Si": "硅", "P": "磷", "S": "硫", "Cl": "氯",
    "K": "钾", "Ca": "钙", "Ti": "钛", "V": "钒", "Cr": "铬", "Mn": "锰", "Fe": "铁",
    "Co": "钴", "Ni": "镍", "Cu": "铜", "Zn": "锌", "As": "砷", "Se": "硒", "Rb": "铷",
    "Sr": "锶", "Y": "钇", "Zr": "锆", "Nb": "铌", "Mo": "钼", "Cd": "镉", "Sn": "锡",
    "Sb": "锑", "Ba": "钡", "W": "钨", "Pb": "铅",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _posix(path) -> str:
    return str(path).replace("\\", "/")


class Session:
    def __init__(self, workspace_root, task_file, sample_description: str = "",
                 host_mode: Optional[str] = None):
        self.workspace = Workspace(workspace_root)
        self.task_file = pathlib.Path(task_file)
        self.sample_description = sample_description
        self.config: HostConfig = detect_config(host_mode)
        self.main_job_id: Optional[str] = None
        self.comparison_job_id: Optional[str] = None
        self._session_path: Optional[pathlib.Path] = None
        self._record: Optional[dict] = None

    # ------------------------------------------------------------------ start/ask

    def start(self, user_query: str, include_comparison: bool = False) -> dict:
        result = orchestrate(
            self.workspace.root,
            user_query=user_query,
            spectrum_path=str(self.task_file),
            sample_description=self.sample_description,
            include_comparison=include_comparison,
            host_mode=self.config.host,
        )
        self.main_job_id = result.get("job_id")
        if self.main_job_id:
            job = Job.open(self.workspace, self.main_job_id)
            if job is not None:
                self.comparison_job_id = job.get("comparison_job_id")
                self._session_path = job.sub("audit") / "session.json"
                self._record = {
                    "schema_version": SESSION_SCHEMA,
                    "created_at": _utc_now(),
                    "spectrum_path": _posix(self.task_file),
                    "sample_description": self.sample_description,
                    "host_config": config_summary(self.config),
                    "main_job_id": self.main_job_id,
                    "comparison_job_id": self.comparison_job_id,
                    "turns": [],
                }
                self._record_turn({
                    "type": "analysis",
                    "query": user_query,
                    "job_id": self.main_job_id,
                    "status": result.get("status"),
                    "reused_from": result.get("reused_from"),
                    "report": result.get("markdown_path"),
                    "tool_calls": self._initial_tool_calls(job),
                })
        return result

    def ask(self, question: str) -> dict:
        if self.main_job_id is None:
            raise OrchestrationError("session has no main job; start the session first")
        job = Job.open(self.workspace, self.main_job_id)
        if job is None:
            raise OrchestrationError(f"job {self.main_job_id} does not exist")
        if job.stage() != "succeeded":
            return self._answer_deterministic(
                question, "status",
                f"主任务 {self.main_job_id} 状态为 {job.stage()}"
                f"（{job.get('error_code') or '无错误码'}），没有可回答的成功结果。",
                [])

        intent = self._classify(question)
        if self.config.simulated:
            return self._deterministic(question, intent, job)
        return self._host_follow_up(question, intent, job)

    # ------------------------------------------------------------------ intents

    @staticmethod
    def _classify(question: str) -> str:
        q = question.lower()
        if any(word in question for word in ("对照", "V9", "差异复核")) or "compare" in q:
            return "compare"
        if "ppm" in q or "换算" in question:
            return "ppm"
        if any(word in question for word in ("未报出", "不存在", "为零", "没有报出")):
            return "unreported"
        if any(word in question for word in ("复用", "重复", "相同", "同一个文件")):
            return "reuse"
        if any(word in question for word in ("导出", "报告")):
            return "export"
        return "freeform"

    def _deterministic(self, question: str, intent: str, job: Job) -> dict:
        if intent == "compare":
            return self._compare(question, job)
        if intent == "ppm":
            return self._ppm(question, job)
        if intent == "unreported":
            return self._unreported(question, job)
        if intent == "reuse":
            return self._reuse(question, job)
        if intent == "export":
            return self._export(question, job)
        digest = _result_digest(self.workspace, self.main_job_id)
        reported = ", ".join(
            f"{e['element']}={e['mass_percent']:.6f}%（{e['mass_percent_ppm']:.4f} ppm）"
            for e in digest.get("reported_elements", []))
        answer = (
            f"当前会话主任务 `{self.main_job_id}`（{job.get('model_version')}）。"
            f"本地模拟宿主不生成自由文本回答；可直接问：某元素 ppm 换算、V9 对照、"
            f"未报出的含义或导出报告。\n已报出元素：{reported or '无'}。")
        return self._answer_deterministic(question, intent, answer, [])

    # ------------------------------------------------------------------ handlers

    def _compare(self, question: str, job: Job) -> dict:
        calls = []
        comparison_path = job.sub("inference") / "comparison.json"
        if comparison_path.exists():
            comparison = read_json(comparison_path)
            calls.append({"name": "compare_models", "origin": "reused_existing",
                          "job_id": self.main_job_id,
                          "v9_job_id": comparison.get("v9_job_id")})
        else:
            comparison = compare_models(self.workspace, self.main_job_id)
            calls.append({"name": "compare_models", "origin": "session",
                          "job_id": self.main_job_id,
                          "v9_job_id": comparison.get("v9_job_id")})
        if comparison.get("error_code"):
            answer = (f"V9 对照失败：{comparison.get('error_code')}。"
                      f"V10 结果保留在任务 `{self.main_job_id}`，未受影响。")
            return self._answer_deterministic(question, "compare", answer, calls)

        self.comparison_job_id = comparison.get("v9_job_id")
        job = Job.open(self.workspace, self.main_job_id)
        try:
            exported = export_report(self.workspace, self.main_job_id, include_comparison=True)
        except ToolError as exc:
            exported = {"status": "failed", "error_code": getattr(exc, "code", "NUMERICAL_FAILURE"),
                        "markdown_path": ""}
        report_path = exported.get("markdown_path") or None
        export_failed = exported.get("status") != "exported" or not report_path
        calls.append({"name": "export_report", "origin": "session",
                      "job_id": self.main_job_id,
                      "markdown_path": report_path,
                      "failed": export_failed,
                      "status": exported.get("status"),
                      "error_code": exported.get("error_code")})
        answer = self._comparison_text(comparison, None if export_failed else report_path)
        if export_failed:
            answer += (f"\n报告导出失败：{exported.get('error_code') or exported.get('status')}。"
                       f"报告未发布，两版数值结果仍分别保留在主任务 "
                       f"`{self.main_job_id}` 与对照任务 `{self.comparison_job_id}`。")
        return self._answer_deterministic(question, "compare", answer, calls)

    def _comparison_text(self, comparison: dict, report_path: str | None = None) -> str:
        self.comparison_job_id = comparison.get("v9_job_id") or self.comparison_job_id
        text = (
            f"V9 对照已完成并关联主任务 `{self.main_job_id}`；"
            f"V9 结果保存在对照任务 `{self.comparison_job_id}`，两版结果分别保留、不平均、不覆盖。\n"
            f"{comparison.get('note')}\n"
            f"V10 结果：{_posix(self.workspace.job_dir(self.main_job_id) / 'inference' / 'result.json')}\n"
            f"V9 结果：{_posix(self.workspace.job_dir(self.comparison_job_id) / 'inference' / 'result.json')}")
        if report_path:
            text += f"\n报告（含 V9 列）：{report_path}"
        return text

    def _ppm(self, question: str, job: Job) -> dict:
        digest = _result_digest(self.workspace, self.main_job_id)
        reported = digest.get("reported_elements", [])
        model = ModelRegistry(self.workspace).model(job.get("model_version"))
        elements = model.get("elements", [])
        chosen = self._element_in(question, elements)
        if chosen is None and reported:
            chosen = max(reported, key=lambda e: e["mass_percent"])["element"]
        if chosen is None:
            answer = "已有结果中没有可换算的报出元素。"
            return self._answer_deterministic(question, "ppm", answer, [])

        entry = next((e for e in reported if e["element"] == chosen), None)
        if entry is None:
            answer = (
                f"元素 {chosen}（{ELEMENT_NAMES_CN.get(chosen, chosen)}）本模型未报出，"
                "没有可换算的含量；**未报出不等于含量为零，也不等于该元素不存在**。")
        else:
            answer = (
                f"元素 {chosen}（{ELEMENT_NAMES_CN.get(chosen, chosen)}）由任务 "
                f"`{self.main_job_id}` 的 {digest.get('model_version')} 结果报出："
                f"质量百分含量 {entry['mass_percent']:.6f}%，"
                f"换算为 {entry['mass_percent'] * 10000.0:.4f} ppm"
                f"（{entry['mass_percent']:.6f}% × 10000）。\n"
                "该换算直接读取已有结果，未重新运行模型。"
                "ppm 值不回写数值结果；未报出也不等于元素不存在。")
        evidence = [{
            "name": "read_existing_result",
            "origin": "session",
            "job_id": self.main_job_id,
            "artifact": _posix(job.sub("inference") / "result.json"),
        }]
        return self._answer_deterministic(question, "ppm", answer, evidence)

    def _unreported(self, question: str, job: Job) -> dict:
        digest = _result_digest(self.workspace, self.main_job_id)
        reported = [e["element"] for e in digest.get("reported_elements", [])]
        missing = digest.get("not_reported", [])
        answer = (
            f"“未报出”只表示 {digest.get('model_version')} 在该元素上没有给出非零含量，"
            "**不等于含量为零，也不等于该元素不存在**。报告中的分类概率是原始输出，"
            "未校准，不能当作存在/不存在的判定。\n"
            f"本任务报出：{', '.join(reported) or '无'}。\n"
            f"未报出：{', '.join(missing) or '无'}。\n"
            "若需要确认某个未报出元素是否真的不存在，需要独立方法或标样验证，"
            "不能由本模型的下限式输出推断。")
        return self._answer_deterministic(question, "unreported", answer, [])

    def _reuse(self, question: str, job: Job) -> dict:
        source = job.get("reused_from")
        if source:
            answer = (
                f"本任务 `{self.main_job_id}` 复用了任务 `{source}` 的计算结果，未重新推理；"
                f"输入 SHA-256 `{job.get('input_sha256')}` 与来源一致，"
                f"模型 {job.get('model_version')}，模型包 SHA-256 "
                f"`{job.get('model_package_sha256')}`。")
        else:
            answer = (f"本任务 `{self.main_job_id}` 为独立运行，未复用旧任务；"
                      f"输入 SHA-256 `{job.get('input_sha256')}`。")
        return self._answer_deterministic(question, "reuse", answer, [])

    def _export(self, question: str, job: Job) -> dict:
        include = (job.sub("inference") / "comparison.json").exists()
        try:
            exported = export_report(self.workspace, self.main_job_id, include_comparison=include)
        except ToolError as exc:
            return self._answer_deterministic(
                question, "export",
                f"报告导出失败：{getattr(exc, 'code', 'NUMERICAL_FAILURE')}。报告未发布，"
                f"数值结果仍保留在任务 `{self.main_job_id}` 的 inference/result.json。",
                [{"name": "export_report", "origin": "session", "job_id": self.main_job_id,
                  "failed": True, "error_code": getattr(exc, "code", "NUMERICAL_FAILURE")}])
        failed = (exported.get("status") != "exported"
                  or not exported.get("markdown_path")
                  or exported.get("consistency_check") is not True)
        if failed:
            reason = exported.get("error_code") or "consistency_check 未通过"
            warnings = "; ".join(exported.get("warnings") or []) or "无附加说明"
            return self._answer_deterministic(
                question, "export",
                f"报告导出失败：{reason}。报告未发布，数值结果仍保留在任务 "
                f"`{self.main_job_id}` 的 inference/result.json。失败说明：{warnings}",
                [{"name": "export_report", "origin": "session", "job_id": self.main_job_id,
                  "failed": True, "status": exported.get("status"),
                  "error_code": exported.get("error_code")}])
        answer = f"报告已导出（include_comparison={include}）：{exported.get('markdown_path')}"
        return self._answer_deterministic(question, "export", answer, [{
            "name": "export_report", "origin": "session", "job_id": self.main_job_id,
            "markdown_path": exported.get("markdown_path"),
        }])

    # ------------------------------------------------------------------ api host

    def _host_follow_up(self, question: str, intent: str, job: Job) -> dict:
        try:
            result = follow_up(
                self.workspace.agent_root(),
                user_query=question,
                job_id=self.main_job_id,
                workspace=self.workspace,
                host_mode=self.config.host,
            )
        except (OrchestrationError, ToolError) as exc:
            return self._answer_deterministic(
                question, intent, f"多轮调用失败：{exc}", [])
        job = Job.open(self.workspace, self.main_job_id)
        if job is not None:
            self.comparison_job_id = job.get("comparison_job_id")
        details = list(result.get("tool_calls_detail", []))
        names = [d.get("name") for d in details]
        exported_path = result.get("markdown_path")
        if "compare_models" in names and "export_report" not in names:
            try:
                exported = export_report(self.workspace, self.main_job_id, include_comparison=True)
                exported_path = exported.get("markdown_path")
                details.append({"name": "export_report", "origin": "session",
                                "job_id": self.main_job_id,
                                "markdown_path": exported_path})
                names.append("export_report")
            except ToolError:
                pass
        answer = result.get("answer") or ""
        unusable = self._looks_like_tool_markup(answer)
        if unusable:
            answer = ""
        if result.get("blocked_tool_calls") and not details and job is not None:
            return self._deterministic(question, intent, job)
        if not answer.strip():
            comparison_path = job.sub("inference") / "comparison.json" if job is not None else None
            if "compare_models" in names and comparison_path is not None and comparison_path.exists():
                comparison = read_json(comparison_path)
                return self._answer_deterministic(
                    question, intent, self._comparison_text(comparison, exported_path), details,
                    blocked=result.get("blocked_tool_calls", []),
                    record_trajectory=False,
                    answer_source="program_fallback",
                    fallback_reason=result.get("fallback_reason")
                    or "host returned no answer text after the tool round")
            if job is not None:
                return self._deterministic(question, intent, job)
            return self._answer_deterministic(
                question, intent, "宿主没有返回回答。", details,
                blocked=result.get("blocked_tool_calls", []),
                record_trajectory=False,
                answer_source="program_fallback",
                fallback_reason=result.get("fallback_reason") or "host returned no answer text")
        return self._answer_deterministic(
            question, intent, answer, details,
            blocked=result.get("blocked_tool_calls", []),
            record_trajectory=False,
            answer_source="model")

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _looks_like_tool_markup(text: str) -> bool:
        return host_reply_unusable(text)

    @staticmethod
    def _element_in(text: str, elements: list[str]) -> Optional[str]:
        for symbol in re.findall(r"(?<![A-Za-z])([A-Z][a-z]?)(?![A-Za-z0-9])", text):
            if symbol in elements:
                return symbol
        for symbol, cn in ELEMENT_NAMES_CN.items():
            if symbol in elements and cn in text:
                return symbol
        return None

    def _initial_tool_calls(self, job: Job) -> list:
        path = job.sub("audit") / "trajectory.json"
        if not path.exists():
            return []
        try:
            trajectory = read_json(path)
        except (OSError, json.JSONDecodeError):
            return []
        calls = []
        for turn in trajectory.get("turns", []):
            for call in turn.get("tool_calls_executed", []):
                calls.append({
                    "name": call.get("name"),
                    "origin": call.get("origin"),
                    "job_id": (call.get("result") or {}).get("job_id", self.main_job_id),
                })
        return calls

    def _answer_deterministic(self, question: str, intent: str, answer: str,
                              calls: list, blocked: list | None = None,
                              record_trajectory: bool = True,
                              answer_source: str = "program_fallback",
                              fallback_reason: str | None = None) -> dict:
        if fallback_reason is None and answer_source == "program_fallback":
            fallback_reason = ("deterministic host (local_simulation); no generative model"
                               if self.config.simulated
                               else "program summary built from stored results")
        self._record_turn({
            "type": "follow_up",
            "query": question,
            "intent": intent,
            "answer": answer,
            "answer_source": answer_source,
            "fallback_reason": fallback_reason,
            "job_id": self.main_job_id,
            "comparison_job_id": self.comparison_job_id,
            "tool_calls": calls,
            "blocked_tool_calls": blocked or [],
        })
        if record_trajectory:
            self._append_trajectory_turn(question, intent, answer, calls, blocked or [],
                                         answer_source=answer_source,
                                         fallback_reason=fallback_reason)
        return {
            "schema_version": SESSION_SCHEMA,
            "job_id": self.main_job_id,
            "comparison_job_id": self.comparison_job_id,
            "intent": intent,
            "answer": answer,
            "answer_source": answer_source,
            "fallback_reason": fallback_reason,
            "tool_calls": calls,
            "blocked_tool_calls": blocked or [],
        }

    def _record_turn(self, payload: dict) -> None:
        if self._record is None or self._session_path is None:
            return
        payload["turn"] = len(self._record["turns"]) + 1
        payload["at"] = _utc_now()
        self._record["turns"].append(payload)
        self._record["comparison_job_id"] = self.comparison_job_id
        write_json(self._session_path, self._record)

    def _append_trajectory_turn(self, question: str, intent: str, answer: str,
                                calls: list, blocked: list,
                                answer_source: str = "program_fallback",
                                fallback_reason: str | None = None) -> None:
        if self.main_job_id is None:
            return
        job = Job.open(self.workspace, self.main_job_id)
        if job is None:
            return
        path = job.sub("audit") / "trajectory.json"
        if not path.exists():
            return
        try:
            trajectory = read_json(path)
        except (OSError, json.JSONDecodeError):
            return
        trajectory.setdefault("turns", []).append({
            "turn": len(trajectory.get("turns", [])) + 1,
            "messages": [{"role": "user", "content": question}],
            "origin": "session",
            "intent": intent,
            "answer": answer,
            "answer_source": answer_source,
            "fallback_reason": fallback_reason,
            "host": {
                "host_label": "session_deterministic_read",
                "simulated": self.config.simulated,
                "tool_calls": [],
            },
            "blocked_tool_calls": blocked,
            "tool_calls_executed": [
                {"name": c.get("name"), "origin": c.get("origin"),
                 "arguments": {}, "executed_arguments": {"job_id": c.get("job_id")},
                 "result": {"job_id": c.get("job_id")}, "error": None}
                for c in calls
            ],
        })
        write_json(path, trajectory)
