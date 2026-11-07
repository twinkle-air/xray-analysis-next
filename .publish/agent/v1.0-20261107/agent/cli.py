"""Command line for the four documented tools.

No LLM is required: each call is one tool invocation, so the whole chain can be driven
step by step and every intermediate artifact is on disk for independent checking.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# the package's parent, so the module works both as `python -m agent.cli` and as a bare
# script (`python -I agent/cli.py`), where sys.path[0] is the package directory itself.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from agent.core import reporting  # noqa: E402
from agent.core.job import Job  # noqa: E402
from agent.core.paths import Workspace  # noqa: E402
from agent.core.tools import (  # noqa: E402
    ToolError, analyze_spectrum, compare_models, export_report, get_job_status,
)
from agent.orchestrator import OrchestrationError, orchestrate  # noqa: E402
from agent.host import HostError, detect_config  # noqa: E402
from agent.session import Session  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def _default_workspace_root() -> pathlib.Path:
    """The workspace the CLI drives without --workspace: where the registry actually lives.

    In the flat layout that is the package's parent; in the checked-out repository the
    package sits under agent-workspace/ and the workspace root is one level above that --
    agent-workspace/ itself would double the agent-workspace path segment. The inner
    directory does contain a registry, so it must only win when the package is *not* under
    an agent-workspace/ directory.
    """
    if HERE.parent.name == "agent-workspace":
        try:
            if Workspace(HERE.parent.parent).model_registry().is_file():
                return HERE.parent.parent
        except (OSError, ValueError):
            pass
    try:
        if Workspace(HERE.parent).model_registry().is_file():
            return HERE.parent
    except (OSError, ValueError):
        pass
    return HERE.parent


WORKSPACE_ROOT = _default_workspace_root()


def _workspace(args) -> Workspace:
    root = pathlib.Path(getattr(args, "workspace", None) or WORKSPACE_ROOT)
    return Workspace(root)


def _dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _print_warnings(result: dict) -> None:
    for warning in result.get("warnings") or []:
        print(f"warning: {warning}", file=sys.stderr)


def cmd_analyze(args) -> int:
    workspace = _workspace(args)
    task_file = pathlib.Path(args.task_file)
    if not task_file.is_file():
        print(f"error: task file not found: {task_file}", file=sys.stderr)
        return 2
    try:
        result = analyze_spectrum(workspace, task_file, args.sample_description or "",
                                  allow_unverified_runtime=args.allow_unverified_runtime)
    except ToolError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        if getattr(exc, "user_message", None):
            print(f"用户提示: {exc.user_message}", file=sys.stderr)
        return 2
    _dump(result)
    _print_warnings(result)
    return 0


def cmd_status(args) -> int:
    workspace = _workspace(args)
    try:
        result = get_job_status(workspace, args.job_id)
    except ToolError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        if getattr(exc, "user_message", None):
            print(f"用户提示: {exc.user_message}", file=sys.stderr)
        return 2
    _dump(result)
    return 0 if result.get("exists") else 1


def cmd_compare(args) -> int:
    workspace = _workspace(args)
    try:
        result = compare_models(workspace, args.job_id,
                                allow_unverified_runtime=args.allow_unverified_runtime)
    except ToolError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        if getattr(exc, "user_message", None):
            print(f"用户提示: {exc.user_message}", file=sys.stderr)
        return 2
    _dump(result)
    _print_warnings(result)
    return 0


def cmd_export(args) -> int:
    workspace = _workspace(args)
    try:
        result = export_report(workspace, args.job_id, args.include_comparison)
    except ToolError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        if getattr(exc, "user_message", None):
            print(f"用户提示: {exc.user_message}", file=sys.stderr)
        return 2
    _dump(result)
    if result.get("markdown_path"):
        print(f"\nreport written to {result['markdown_path']}", file=sys.stderr)
    return 0 if result.get("consistency_check") else 1


def cmd_agent_interactive(args) -> int:
    """Session loop: one spectrum, one main job, repeated questions.

    The session keeps the spectrum, the main job id and the V9 comparison job id, so a
    follow-up reads the existing result instead of re-analysing the spectrum. Deterministic
    reads (ppm, non-detection meaning, reuse source) never call the numerical backend.
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
        session = Session(workspace.root, task_file, sample_description,
                          host_mode=args.host_mode,
                          allow_unverified_runtime=args.allow_unverified_runtime)
        result = session.start(args.query or "请分析这张谱",
                               include_comparison=args.compare)
    except (OrchestrationError, ToolError, HostError, ValueError) as exc:
        print(f"error [{getattr(exc, 'code', 'ORCHESTRATION_FAILURE')}]: {exc}", file=sys.stderr)
        return 2
    _print_summary(result, workspace)
    print(f"  会话主任务: {session.main_job_id} | 对照任务: {session.comparison_job_id or '-'}")
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
            turn = session.ask(line)
        except (OrchestrationError, ToolError, HostError, ValueError) as exc:
            print(f"error [{getattr(exc, 'code', 'ORCHESTRATION_FAILURE')}]: {exc}\n")
            continue
        print(f"\n{turn.get('answer', '')}\n")
        print(f"  任务: {turn.get('job_id')} | 对照: {turn.get('comparison_job_id') or '-'} | "
              f"会话记录: {session._session_path}")
        print()


def _print_summary(result: dict, workspace: Workspace) -> None:
    status = result.get("status")
    print(f"  状态: {status} | 任务: {result.get('job_id')} | 宿主: {result.get('host_config', {}).get('host')}")
    if result.get("answer"):
        source = result.get("answer_source") or "program"
        print(f"  回答（{source}）: {result['answer']}")
    if result.get("model_version"):
        print(f"  模型: {result.get('model_version')} | 输入 SHA-256: {str(result.get('input_sha256') or '-')[:16]}…")
    if result.get("reused_from"):
        print(f"  复用来源: 任务 {result['reused_from']} 的计算结果（未重新推理）")
    if result.get("comparison_job_id"):
        print(f"  对照任务: {result['comparison_job_id']}")
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
        if getattr(exc, "user_message", None):
            print(f"用户提示: {exc.user_message}", file=sys.stderr)
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
            allow_unverified_runtime=args.allow_unverified_runtime,
            host_mode=args.host_mode,
        )
    except (OrchestrationError, ToolError, HostError) as exc:
        print(f"error [{getattr(exc, 'code', 'ORCHESTRATION_FAILURE')}]: {exc}", file=sys.stderr)
        return 2
    _dump(result)
    _print_warnings(result)
    if result.get("reused_from"):
        print(f"\n复用来源: 任务 {result['reused_from']} 的计算结果（未重新推理）", file=sys.stderr)
    if result.get("markdown_path"):
        print(f"\nreport written to {result['markdown_path']}", file=sys.stderr)
    if result.get("trajectory_ref"):
        print(f"\ntrajectory written to {result['trajectory_ref']}", file=sys.stderr)
    return 0 if result.get("status") == "exported" else (0 if result.get("status") == "succeeded" else 1)


def _force_utf8_stdio() -> None:
    """Make Chinese prompts, reports and piped stdin work without manual env vars.

    On Windows the default stdio encoding follows the console code page (often cp936), which
    breaks UTF-8 pipes and Chinese interactive input. A real console gets its code page set
    to UTF-8 first, so the reconfigured streams stay readable on screen; redirected streams
    simply become UTF-8, which is what logs and the verify suites already expect.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if sys.stdin.isatty():
            kernel32.SetConsoleCP(65001)
        if sys.stdout.isatty():
            kernel32.SetConsoleOutputCP(65001)
        if sys.stderr.isatty():
            kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            if stream.encoding.lower() not in ("utf-8", "utf8"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


def main(argv=None) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(prog="xrf-agent", description="XRF spectrum analysis agent (tools only)")
    parser.add_argument("--workspace", default=str(WORKSPACE_ROOT), help="workspace root (default: script parent parent)")
    parser.add_argument("--allow-unverified-runtime", action="store_true",
                        help="run even when the numerical runtime (Python / numpy / scipy / "
                             "xraylib) does not match the declared policy; the unverified "
                             "status and reason are recorded in the job, JSON and report")
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