"""Command line for the four documented tools.

No LLM is required: each call is one tool invocation, so the whole chain can be driven
step by step and every intermediate artifact is on disk for independent checking.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from agent.core import reporting  # noqa: E402
from agent.core.job import Job  # noqa: E402
from agent.core.paths import Workspace  # noqa: E402
from agent.core.tools import (  # noqa: E402
    ToolError, analyze_spectrum, compare_models, export_report, get_job_status,
)
from agent.orchestrator import OrchestrationError, orchestrate  # noqa: E402
from agent.host import HostError, detect_config  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE_ROOT = HERE.parent


def _workspace(args) -> Workspace:
    root = pathlib.Path(getattr(args, "workspace", None) or WORKSPACE_ROOT)
    return Workspace(root)


def _dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_analyze(args) -> int:
    workspace = _workspace(args)
    task_file = pathlib.Path(args.task_file)
    if not task_file.is_file():
        print(f"error: task file not found: {task_file}", file=sys.stderr)
        return 2
    try:
        result = analyze_spectrum(workspace, task_file, args.sample_description or "")
    except ToolError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 2
    _dump(result)
    return 0


def cmd_status(args) -> int:
    workspace = _workspace(args)
    try:
        result = get_job_status(workspace, args.job_id)
    except ToolError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 2
    _dump(result)
    return 0 if result.get("exists") else 1


def cmd_compare(args) -> int:
    workspace = _workspace(args)
    try:
        result = compare_models(workspace, args.job_id)
    except ToolError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 2
    _dump(result)
    return 0


def cmd_export(args) -> int:
    workspace = _workspace(args)
    try:
        result = export_report(workspace, args.job_id, args.include_comparison)
    except ToolError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 2
    _dump(result)
    if result.get("markdown_path"):
        print(f"\nreport written to {result['markdown_path']}", file=sys.stderr)
    return 0 if result.get("consistency_check") else 1


def cmd_agent_interactive(args) -> int:
    """Thin read-eval loop: one spectrum, repeated natural-language questions.

    Every question is a fresh orchestration run, so each answer is backed by a real tool
    trajectory and a job id. Follow-up questions re-run the chain; no state is resumed
    across turns, which keeps the interface from pretending to remember more than it does.
    """
    workspace = _workspace(args)
    task_file = pathlib.Path(args.task_file)
    if not task_file.is_file():
        print(f"error: task file not found: {task_file}", file=sys.stderr)
        return 2
    announced = _announce_host(args.host_mode)
    if announced:
        return announced
    sample_description = args.sample_description or ""

    try:
        result = orchestrate(
            workspace.root,
            user_query=args.query or "请分析这张谱",
            spectrum_path=str(task_file),
            sample_description=sample_description,
            include_comparison=args.compare,
            host_mode=args.host_mode,
        )
    except (OrchestrationError, ToolError, HostError) as exc:
        print(f"error [{getattr(exc, 'code', 'ORCHESTRATION_FAILURE')}]: {exc}", file=sys.stderr)
        return 2
    _print_summary(result, workspace)
    if args.once:
        return 0 if result.get("status") == "exported" else 1

    print("\n输入空行、q 或 exit 结束。")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line in ("", "q", "quit", "exit"):
            return 0
        try:
            result = orchestrate(
                workspace.root, user_query=line, spectrum_path=str(task_file),
                sample_description=sample_description, host_mode=args.host_mode)
        except (OrchestrationError, ToolError, HostError) as exc:
            print(f"error [{getattr(exc, 'code', 'ORCHESTRATION_FAILURE')}]: {exc}")
            continue
        _print_summary(result, workspace)


def _print_summary(result: dict, workspace: Workspace) -> None:
    status = result.get("status")
    print(f"  状态: {status} | 任务: {result.get('job_id')} | 宿主: {result.get('host_config', {}).get('host')}")
    if result.get("error_code"):
        print(f"  错误: {result['error_code']}")
    for warning in result.get("warnings") or []:
        print(f"  警告: {warning}")
    if status == "exported":
        print(f"  报告: {result.get('markdown_path')}")
        md = result.get("markdown") or ""
        for line in md.splitlines():
            if "formal_report_eligible" in line or "hardware_validated" in line or line.startswith("## 1"):
                print(f"  {line.strip()}")
    print()


def _announce_host(host_mode) -> int:
    """Resolve the host up front and say which one is in use, or fail loudly.

    Priority: an explicit --host-mode flag, then XRF_AGENT_LLM_HOST, then
    local_simulation. A real host asked for but not configured is an error, never a
    silent fall back to the simulator.
    """
    try:
        config = detect_config(host_mode)
    except HostError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 2
    print(f"宿主: {config.host} | 模型: {config.model or '-'} | 地址: {config.api_base or '-'} "
          f"| simulated={config.simulated}", file=sys.stderr)
    return 0


def cmd_agent(args) -> int:
    """Coordinate a natural-language request through the LLM host and the four tools."""
    if args.interactive:
        return cmd_agent_interactive(args)
    workspace = _workspace(args)
    announced = _announce_host(args.host_mode)
    if announced:
        return announced
    try:
        result = orchestrate(
            workspace.root,
            user_query=args.query or "请分析这张谱",
            spectrum_path=args.task_file,
            sample_description=args.sample_description or "",
            include_comparison=args.compare,
            no_export=args.no_export,
            host_mode=args.host_mode,
        )
    except (OrchestrationError, ToolError, HostError) as exc:
        print(f"error [{getattr(exc, 'code', 'ORCHESTRATION_FAILURE')}]: {exc}", file=sys.stderr)
        return 2
    _dump(result)
    if result.get("markdown_path"):
        print(f"\nreport written to {result['markdown_path']}", file=sys.stderr)
    if result.get("trajectory_ref"):
        print(f"\ntrajectory written to {result['trajectory_ref']}", file=sys.stderr)
    return 0 if result.get("status") == "exported" else (0 if result.get("status") == "succeeded" else 1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="xrf-agent", description="XRF spectrum analysis agent (tools only)")
    parser.add_argument("--workspace", default=str(WORKSPACE_ROOT), help="workspace root (default: script parent parent)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="ingest a spectrum and run V10")
    p.add_argument("--task-file", required=True, help="absolute path to the five-field task JSON")
    p.add_argument("--sample-description", default="", help="optional free-text user note, stored separately")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("status", help="inspect one job")
    p.add_argument("--job-id", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("compare", help="run V9 against an existing V10 job")
    p.add_argument("--job-id", required=True)
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("export", help="write JSON + Markdown report for a job")
    p.add_argument("--job-id", required=True)
    p.add_argument("--include-comparison", action="store_true", help="requires a completed compare run")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("agent", help="coordinate a natural-language request through the host")
    p.add_argument("--task-file", required=True, help="absolute path to the five-field task JSON")
    p.add_argument("--query", default="请分析这张谱", help="natural-language user request")
    p.add_argument("--sample-description", default="", help="optional free-text user note")
    p.add_argument("--compare", action="store_true", help="request a V9 comparison")
    p.add_argument("--no-export", action="store_true", help="stop after analysis/comparison")
    p.add_argument("--interactive", action="store_true",
                   help="keep asking follow-up questions about the same spectrum")
    p.add_argument("--once", action="store_true", help="with --interactive, run only the first turn")
    p.add_argument("--host-mode", default=None,
                   help="LLM host backend; flag wins over XRF_AGENT_LLM_HOST, then the env "
                        "var, then local_simulation")
    p.set_defaults(func=cmd_agent)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())