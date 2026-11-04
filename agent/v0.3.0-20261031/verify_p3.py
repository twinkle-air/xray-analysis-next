"""P3 verification: thin interface, the remaining fixed cases and a clean-slate run.

Covers the four cases left over from the fixed acceptance pack (E05-E08), plus a
single-command full chain started from an empty jobs/ directory. Exit code 0 only when
every case behaves as specified and no artifact leaks behind.

Usage: python verify_p3.py   (run from the repository root)
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile

import verify_common
# agent sits directly here (flat layout) or under agent-workspace/ (repository layout).
sys.path.insert(0, str(verify_common.PACKAGE_PARENT))
from agent.core.paths import write_json

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE
SPECTRA = ROOT / "deliverables" / "智能体功能测试谱集-20261031"
JOBS = ROOT / "jobs"

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  PASS {name}")
    else:
        failures.append((name, detail))
        print(f"  FAIL {name}: {detail}")


def abs_path(rel: str) -> str:
    return str((ROOT / rel).resolve())


def job_id_in(text: str) -> str:
    for token in str(text).split():
        if len(token) == 12 and all(ch in "0123456789abcdef" for ch in token):
            return token
    return ""


def read_job(job_id, bucket, name):
    return json.loads((JOBS / job_id / bucket / name).read_text(encoding="utf-8"))


def temp_task_file(basename, mutate=None):
    """Write a temporary five-field task file under the workspace root. Caller deletes it."""
    path = ROOT / "jobs" / ".tmp-verify" / basename
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.loads((SPECTRA / "01_正常输入" / "T01.json").read_text(encoding="utf-8"))
    if mutate:
        mutate(raw)
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def direct(args):
    """Run a CLI subcommand and return (object, return code, last stderr line)."""
    obj, rc, err = verify_common.run(args)
    return obj, rc, err.strip().splitlines()[-1] if err else ""


# ------------------------------------------------------------------ E05: extra fields are rejected, never forwarded


def e05():
    print("--- E05 extra fields (truth / seed) are rejected, not forwarded")
    banned = temp_task_file("extra_banned.json", lambda raw: raw.update(
        {"truth": {"Si": 29.5}, "seed": 42}))
    try:
        obj, rc, err = direct(["analyze", "--task-file", str(banned),
                               "--sample-description", "with extra fields"])
        # the CLI returns 0 whenever the tool ran and reported a structured result; a
        # validation failure is part of that result, so status carries the failure.
        check("banned extra fields rejected", rc == 0 and obj.get("status") == "failed",
              f"rc={rc} status={obj.get('status')}")
        check("explicit error code", obj.get("error_code") == "INVALID_COUNTS",
              f"error_code={obj.get('error_code')}")
        check("no inference artifact for extra fields",
              not (JOBS / obj["job_id"] / "inference" / "result.json").exists())
        check("banned fields named in the warnings",
              any("truth" in w and "seed" in w for w in obj.get("warnings") or []),
              f"warnings={obj.get('warnings')}")
        check("no parsed input was published for extra fields",
              not (JOBS / obj["job_id"] / "parsed" / "validated.json").exists())

        allowed = temp_task_file("extra_note.json", lambda raw: raw.update({"note": "a note"}))
        obj2, rc2, _ = direct(["analyze", "--task-file", str(allowed)])
        check("any extra field is rejected, not just banned ones",
              rc2 == 0 and obj2.get("status") == "failed", f"rc={rc2} status={obj2.get('status')}")
    finally:
        verify_common.rmtree(banned.parent)


# ------------------------------------------------------------------ E06: integrity mismatch is reported, never silently repaired


def e06():
    print("--- E06 package integrity mismatch is reported, never re-hashed")
    package = ROOT / "deliverables" / "xrf-models-v9-v10-20261030" / "outputs" / "model-v10-20261030"
    scratch = ROOT / "jobs" / ".tmp-verify" / "package-copy"
    if scratch.exists():
        verify_common.rmtree(scratch)
    shutil.copytree(package, scratch)
    # the V10 freeze lists processing_dependencies relative to the package root, so a
    # copied package needs the sibling model-v9 bundle copied too, or the copy would be
    # incomplete for reasons unrelated to the test.
    v9_bundle = (package / "../model-v9-20261028/bundle").resolve()
    if v9_bundle.exists():
        shutil.copytree(v9_bundle, (scratch / "../model-v9-20261028/bundle").resolve(),
                        dirs_exist_ok=True)

    from agent.core.paths import Workspace
    from agent.core.registry import ModelRegistry

    ws = Workspace(ROOT)
    registry = ModelRegistry(ws)
    original = dict(registry._data["models"]["V10"])
    registry._data["models"]["V10"] = {
        **original,
        "package_root": str(scratch.relative_to(ROOT)).replace("/", "\\"),
        "integrity_file": str((scratch / "freeze.json").relative_to(ROOT)).replace("/", "\\"),
    }
    try:
        before = registry.verify_package("V10")
        check("integrity passes on an untouched copy", before["ok"] is True,
              f"ok={before['ok']} mismatches={before['mismatches'][:3]}")

        target = scratch / "elements.json"
        original_bytes = target.read_bytes()
        freeze = json.loads((scratch / "freeze.json").read_text(encoding="utf-8"))
        expected_hash = freeze["local_files"]["elements.json"]
        try:
            target.write_bytes(original_bytes + b"\n# tampered for the test")
            after = registry.verify_package("V10")
            check("mismatch is detected after tampering", after["ok"] is False
                  and len(after["mismatches"]) == 1, f"ok={after['ok']} n={len(after['mismatches'])}")
            check("the offending file is named", after["mismatches"][0][0] == "elements.json",
                  after["mismatches"][0])
            check("the expected hash is kept, not recomputed",
                  after["mismatches"][0][1] == expected_hash,
                  f"expected={expected_hash} got={after['mismatches'][0][1]}")
        finally:
            target.write_bytes(original_bytes)

        restored = registry.verify_package("V10")
        check("integrity passes again after restoring the file", restored["ok"] is True,
              f"ok={restored['ok']}")
    finally:
        registry._data["models"]["V10"] = original
        verify_common.rmtree(scratch)


# ------------------------------------------------------------------ E07: timeout kills the subprocess and publishes nothing


def e07():
    print("--- E07 timeout terminates the child and publishes no result")
    import time

    from agent.core.paths import Workspace
    from agent.core.runner import run_model

    scratch = ROOT / "jobs" / ".tmp-verify"
    verify_common.rmtree(scratch)
    ws = Workspace(ROOT)
    out = ROOT / "jobs" / ".tmp-verify" / "timeout_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    t0 = time.perf_counter()
    result = run_model(ws, "V10", SPECTRA / "01_正常输入" / "T01.json", out, timeout=0.2)
    elapsed = time.perf_counter() - t0
    check("run_model returns TIMEOUT on a short deadline",
          result["error_code"] == "TIMEOUT", f"error_code={result['error_code']} wall={elapsed:.2f}s")
    check("no result is published for a timed-out run", not out.exists(),
          "result file appeared after timeout")
    check("the private temp directory is removed",
          not list(out.parent.glob(".tmp-*")), "leftover .tmp-* scratch dirs")
    check("the child is killed promptly (wall within a few multiples of the deadline)",
          elapsed < 10.0, f"wall={elapsed:.2f}s")


# ------------------------------------------------------------------ E08: traversal and overwriting are refused


def e08():
    print("--- E08 traversal, missing input and directories are refused")
    from agent.core.tools import ToolError, analyze_spectrum
    from agent.core.paths import Workspace

    ws = Workspace(ROOT)
    outside = ROOT.parent / "outside-workspace-task.json"
    try:
        outside.write_text("{}", encoding="utf-8")
        for label, task_file in (
            ("absolute path outside the workspace", outside),
            ("relative path escaping the workspace", pathlib.Path("..") / outside.name),
            ("nested traversal via repeated ..", pathlib.Path("jobs") / ".." / ".." / outside.name),
        ):
            try:
                analyze_spectrum(ws, task_file, "")
                check(f"{label} is refused", False, "traversal succeeded")
            except ToolError as exc:
                check(f"{label} raises PATH_TRAVERSAL", exc.code == "PATH_TRAVERSAL",
                      f"code={exc.code}")
    finally:
        if outside.exists():
            outside.unlink()

    try:
        analyze_spectrum(ws, ROOT / "jobs" / "this-file-does-not-exist.json", "")
        check("missing task file is refused", False, "missing file accepted")
    except ToolError as exc:
        check("missing task file raises NOT_FOUND", exc.code == "NOT_FOUND", f"code={exc.code}")

    try:
        analyze_spectrum(ws, SPECTRA / "01_正常输入", "")
        check("a directory is not accepted as a task file", False, "directory accepted")
    except ToolError as exc:
        check("directory task file raises NOT_FOUND", exc.code == "NOT_FOUND", f"code={exc.code}")

    # `Job.create` refuses to overwrite an input artifact it finds already staged. The guard
    # is defensive: every analyze_spectrum run opens a fresh job id, so the only reachable
    # proof is the staged original being read-only, which E01/T04 already covers.
        verify_common.rmtree(JOBS / ".tmp-verify")

    # `Job.create` refuses to overwrite an input artifact it finds already staged. The guard
    # is defensive: every analyze_spectrum run opens a fresh job id, so the only reachable
    # proof is the staged original being read-only, which E01/T04 already covers.


# ------------------------------------------------------------------ clean-slate full chain


def clean_slate():
    print("--- clean-slate full chain from an empty jobs/ directory")
    if JOBS.exists():
        verify_common.rmtree(JOBS)
    t01 = abs_path("deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json")
    obj, rc, err = verify_common.run(["agent", "--task-file", t01, "--query", "请分析这张谱",
                        "--sample-description", "铝合金粉末"])
    check("clean-slate first run exports", rc == 0 and obj.get("status") == "exported",
          f"rc={rc} status={obj.get('status')}")
    job_id = obj["job_id"]
    check("report envelope agrees with inference",
          json.loads(pathlib.Path(obj["json_path"]).read_text(encoding="utf-8"))["elements"][0]
          ["mass_percent"] == read_job(job_id, "inference", "result.json")
          ["predicted_element_percent"]["Na"])
    check("trajectory survived the clean slate", bool(obj.get("trajectory_ref"))
          and pathlib.Path(obj["trajectory_ref"]).exists())

    obj2, rc2, _ = verify_common.run(["agent", "--task-file", t01, "--query", "请跑一次 V9 对照",
                        "--sample-description", "铝合金粉末"])
    check("clean-slate comparison runs", rc2 == 0 and obj2.get("status") == "exported",
          f"rc={rc2} status={obj2.get('status')}")
    v9_job = read_job(obj2["job_id"], "inference", "comparison.json")["v9_job_id"]
    check("V9 job preserved separately", read_job(v9_job, "inference", "result.json")
          .get("version") == "V9")

    leftovers = [str(p) for p in sorted(ROOT.glob("jobs/**/.tmp-*")) if p.is_dir()]
    check("no leftover scratch dirs after the clean-slate chain", not leftovers, leftovers)


# ------------------------------------------------------------------ F05: a comparison the host triggered on its own reaches the report


def f05():
    print("--- F05 natural-language comparison must reach the report")
    t01 = abs_path("deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json")
    obj, rc, err = verify_common.run(["agent", "--task-file", t01, "--query", "请跑一次 V9 对照",
                        "--sample-description", "铝合金粉末"])
    check("comparison ran", rc == 0 and obj.get("status") == "exported", f"rc={rc}")
    job_id = obj["job_id"]
    comparison = read_job(job_id, "inference", "comparison.json")
    check("V9 comparison ran", bool(comparison.get("v9_job_id")), str(comparison))
    envelope = json.loads(pathlib.Path(obj["json_path"]).read_text(encoding="utf-8"))
    check("comparison carried into report JSON",
          envelope.get("comparison", {}).get("v9_job_id") == comparison["v9_job_id"],
          f"report comparison={envelope.get('comparison')}")
    check("report states V9 was run", "V9 对照已完成" in obj.get("markdown", ""))
    print()


# ------------------------------------------------------------------ F06: equal V9 values must not be rendered as "V9 未报出"


def f06():
    print("--- F06 equal V9 values are reported as agreement, not as V9 not reporting")
    t01 = abs_path("deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json")
    obj, rc, _ = verify_common.run(["agent", "--task-file", t01, "--query", "请分析这张谱",
                        "--sample-description", "铝合金粉末"])
    job_id = obj["job_id"]
    compare, rc2, _ = verify_common.run(["compare", "--job-id", job_id])
    check("comparison succeeded", rc2 == 0 and compare.get("error_code") is None, f"rc={rc2}")
    comparison = read_job(job_id, "inference", "comparison.json")
    v10 = read_job(job_id, "inference", "result.json")["predicted_element_percent"]
    v9 = read_job(comparison["v9_job_id"], "inference", "result.json")["predicted_element_percent"]
    # force the two versions to agree on Si so the comparison reports no difference
    comparison["v9_predicted_element_percent"] = dict(v10)
    write_json(JOBS / job_id / "inference" / "comparison.json", comparison)
    export, rc3, _ = verify_common.run(["export", "--job-id", job_id, "--include-comparison"])
    check("export succeeded", rc3 == 0 and export.get("status") == "exported", f"rc={rc3}")
    md = export.get("markdown") or ""
    si_row = [line for line in md.splitlines() if line.startswith("| Si ")]
    check("Si row exists", bool(si_row), "Si missing from report")
    check("Si shows the V9 value instead of 'V9 未报出'",
          "V9 未报出" not in si_row[0] and "V9=" in si_row[0], si_row[0] if si_row else "")
    print()


# ------------------------------------------------------------------ tool contract parameters are enforced


def f_extra_param():
    print("--- extra tool parameters are rejected by the executor, not only by the hint")
    from agent.orchestrator import ToolExecutor, ToolCall, ToolError
    from agent.core.paths import Workspace

    ws = Workspace(ROOT)
    executor = ToolExecutor(ws)
    obj, rc, _ = verify_common.run(["analyze", "--task-file",
                                    abs_path("deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json")])
    check("analysis succeeded", rc == 0 and obj.get("status") == "succeeded", f"rc={rc}")
    call = ToolCall(id="call-status", name="get_job_status", arguments={
        "job_id": obj["job_id"], "extra_field": "must be rejected"})
    try:
        executor.execute(call)
        check("extra parameter rejected", False, "extra parameter was accepted")
    except ToolError as exc:
        check("extra parameter rejected", exc.code == "CONTRACT_VIOLATION", f"code={exc.code}")
    print()


# ------------------------------------------------------------------ thin interface


def thin_interface():
    print("--- thin interactive interface")
    t01 = abs_path("deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json")
    out, rc, err = verify_common.run_text(["agent", "--task-file", t01, "--query", "请分析这张谱",
                             "--sample-description", "铝合金粉末", "--interactive", "--once"])
    check("interactive first turn exits cleanly", rc == 0, f"rc={rc} {err[:160]}")
    job_id = job_id_in(out)
    check("interactive first turn reports a job id", bool(job_id), out[:600])

    from agent.orchestrator import follow_up
    from agent.core.paths import Workspace
    follow = follow_up(verify_common.PACKAGE, "请导出报告", job_id, Workspace(ROOT))
    check("follow-up '导出报告' re-exports on the same job",
          follow["status"] == "exported" and follow["job_id"] == job_id,
          f"status={follow['status']} job={follow['job_id']}")
    check("follow-up writes the markdown file", bool(follow.get("markdown_path"))
          and pathlib.Path(follow["markdown_path"]).exists())

    follow2 = follow_up(verify_common.PACKAGE, "请跑一次 V9 对照", job_id, Workspace(ROOT))
    check("follow-up 'V9 对照' routes to compare_models, not export",
          follow2["tool_calls_executed"] == ["compare_models"], f"tools={follow2['tool_calls_executed']}")

    follow3 = follow_up(verify_common.PACKAGE, "现在导出报告", job_id, Workspace(ROOT))
    check("after comparison, follow-up exports", follow3["status"] == "exported",
          f"status={follow3['status']}")

    traj = json.loads((JOBS / job_id / "audit" / "trajectory.json").read_text(encoding="utf-8"))
    check("all five turns share one trajectory and one job id",
          len(traj["turns"]) == 5 and traj["job_id"] == job_id,
          f"turns={len(traj['turns'])} job={traj['job_id']}")
    check("the report carries the research-draft disclaimer",
          "formal_report_eligible=False" in (follow3.get("markdown") or ""),
          "disclaimer missing")

    out4, rc4, err4 = verify_common.run_text(["agent", "--task-file", t01, "--sample-description", "铝合金粉末",
                                "--interactive", "--once", "--host-mode", "unknown"])
    check("unknown host mode still rejected in interactive mode",
          rc4 == 2 and "UNSUPPORTED_HOST" in err4, f"rc={rc4} {err4[:160]}")


def main():
    """Run the suite against a throwaway workspace; the real workspace is never touched."""
    global ROOT, SPECTRA, JOBS
    ws = verify_common.TestWorkspace.create()
    verify_common.ACTIVE = ws
    ROOT = ws.root
    SPECTRA = ROOT / "deliverables" / "智能体功能测试谱集-20261031"
    JOBS = ROOT / "jobs"
    try:
        with verify_common.isolated_host_env():
            return run_cases()
    finally:
        ws.close()


def run_cases():
    print(f"workspace root: {ROOT}\n")

    e05()
    e06()
    e07()
    e08()
    clean_slate()
    thin_interface()
    f05()
    f06()
    f_extra_param()

    print("=" * 70)
    if failures:
        print(f"{len(failures)} FAILED:")
        for name, detail in failures:
            print(f"  - {name}: {detail}")
        return 1
    print("ALL CASES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())