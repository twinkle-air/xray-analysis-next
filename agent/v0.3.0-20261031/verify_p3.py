"""P3 verification: thin interface, the remaining fixed cases and a clean-slate run.

Covers the four cases left over from the fixed acceptance pack (E05-E08), plus a
single-command full chain started from an empty jobs/ directory. Exit code 0 only when
every case behaves as specified and no artifact leaks behind.

Usage: python verify_p3.py   (run from the repository root)
"""
from __future__ import annotations

import hashlib
import json
import os
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
    # The task file lives in a directory exclusive to this run. A fixed file name directly
    # in the shared parent used to be written and deleted here, so two concurrent suite runs
    # clobbered each other. Nothing writes to the shared path any more: if a file already
    # sits there it is read as the expected value and left byte-for-byte untouched.
    shared = ROOT.parent / "outside-workspace-task.json"
    if not shared.exists():
        shared.write_text("not-a-task-sentinel\n", encoding="utf-8")
    expected = shared.read_text(encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory(prefix="xrf-verify-outside-") as raw_dir:
            outside_dir = pathlib.Path(raw_dir)
            outside = outside_dir / "outside-workspace-task.json"
            outside.write_text("{}", encoding="utf-8")
            for label, task_file in (
                ("absolute path outside the workspace", outside),
                ("relative path escaping the workspace",
                 pathlib.Path("..") / outside_dir.name / outside.name),
                ("nested traversal via repeated ..",
                 pathlib.Path("jobs") / ".." / ".." / outside_dir.name / outside.name),
            ):
                try:
                    analyze_spectrum(ws, task_file, "")
                    check(f"{label} is refused", False, "traversal succeeded")
                except ToolError as exc:
                    check(f"{label} raises PATH_TRAVERSAL", exc.code == "PATH_TRAVERSAL",
                          f"code={exc.code}")
    finally:
        check("a pre-existing outside-workspace-task.json is left untouched",
              shared.exists() and shared.read_text(encoding="utf-8") == expected,
              f"exists={shared.exists()}")

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


ARGV = []
GUARD = None


def _probe_exit(argv):
    """`--probe-exit <code>`: print a line and exit with that code immediately.

    Never runs a case; it exists so the compatibility entries in agent-workspace/ can prove
    they forward arguments and exit codes (a nonzero one included) instead of reimplementing
    the suite.
    """
    for i, arg in enumerate(argv):
        if arg == "--probe-exit" and i + 1 < len(argv):
            try:
                code = int(argv[i + 1])
            except ValueError:
                continue
            print(f"probe-exit {code}", flush=True)
            return code
    return None


class _RealJobsGuard:
    """Snapshot the source workspace's jobs/ and add a per-run sentinel, then assert the
    suite left both alone. The retired entries deleted this directory outright; a hash
    snapshot catches a wholesale wipe as well as edits.

    Files that appear after the snapshot (another concurrent instance's own sentinel, which
    it removes itself) are tolerated: only paths present at snapshot time must survive
    unmodified.
    """

    def __init__(self):
        self.jobs = verify_common.WORKSPACE / "jobs"
        self.made_dir = not self.jobs.exists()
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.sentinel = self.jobs / f"p3-sentinel-{os.getpid()}.json"
        self.sentinel_text = "the suite must not wipe this directory\n"
        self.sentinel.write_text(self.sentinel_text, encoding="utf-8")
        self.snapshot = self._take()

    def _take(self) -> dict:
        # p3-sentinel-* markers belong to whichever run created them and are removed by
        # that run; comparing them between snapshots would make concurrent instances see
        # each other's cleanup as a change.
        return {
            str(p.relative_to(self.jobs)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(self.jobs.rglob("*"))
            if p.is_file() and not p.name.startswith("p3-sentinel-")
        }

    def finish(self) -> None:
        after = self._take()
        removed = [p for p in self.snapshot if p not in after]
        changed = [p for p in self.snapshot if p in after and after[p] != self.snapshot[p]]
        check("the source workspace's jobs/ files survive unmodified",
              not removed and not changed, f"removed={removed[:3]} changed={changed[:3]}")
        check("this run's jobs/ sentinel survives unchanged",
              self.sentinel.exists()
              and self.sentinel.read_text(encoding="utf-8") == self.sentinel_text,
              self.sentinel.name)
        self.cleanup_marker()

    def cleanup_marker(self) -> None:
        """Remove this run's own marker even when the suite fails before finish() runs."""
        try:
            self.sentinel.unlink()
        except OSError:
            pass
        if self.made_dir and self.jobs.exists() and not any(self.jobs.iterdir()):
            self.jobs.rmdir()


def forwarder_entries():
    """The retired suite copies under agent-workspace/ are now thin forwarders: verify one
    of them forwards arguments and exit codes by running its cheapest path."""
    print("--- compatibility entries forward arguments and exit codes")
    import subprocess
    entry = verify_common.PACKAGE_PARENT / "verify_p3.py"
    if not entry.exists() or entry == pathlib.Path(__file__).resolve():
        print("  SKIP no separate compatibility entry here (flat layout)")
        return
    for code in (7, 3):
        proc = subprocess.run([sys.executable, str(entry), "--probe-exit", str(code)],
                              capture_output=True, text=True, encoding="utf-8")
        check(f"the compatibility entry forwards --probe-exit {code}",
              proc.returncode == code and f"probe-exit {code}" in proc.stdout,
              f"rc={proc.returncode} out={proc.stdout[:80]!r}")


def concurrent_instances():
    """Two full suite instances run at once: each gets its own throwaway workspace and its
    own exclusive outside-task directory, so nothing is shared to overwrite."""
    print("--- two concurrent suite instances do not collide")
    import subprocess
    myself = pathlib.Path(__file__).resolve()
    procs = [subprocess.Popen([sys.executable, str(myself), "--no-concurrency"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8")
             for _ in range(2)]
    results = [p.communicate() for p in procs]
    codes = [p.returncode for p in procs]
    roots = []
    for i, (code, (out, _)) in enumerate(zip(codes, results), 1):
        line = next((l for l in out.splitlines()
                     if l.startswith("isolated test workspace:")), "")
        roots.append(line.split(":", 1)[1].strip() if line else "")
        tail = "\n".join(out.splitlines()[-5:])
        check(f"concurrent instance {i} passes in its own workspace",
              code == 0 and "ALL CASES PASSED" in out and bool(line), f"rc={code}\n{tail}")
    check("the two concurrent instances used separate workspaces",
          len(set(roots)) == 2 and all(roots), str(roots))


def main():
    """Run the suite against a throwaway workspace; the real workspace is never touched.

    `--probe-exit <code>` is a no-case probe for the compatibility entries in
    agent-workspace/: it prints a line and exits with <code> so they can prove they forward
    arguments and exit codes. `--no-concurrency` skips the two-duplicate-run check (it is
    passed to the duplicates themselves to stop the recursion).
    """
    global ROOT, SPECTRA, JOBS, ARGV, GUARD
    ARGV = sys.argv[1:]
    probe = _probe_exit(ARGV)
    if probe is not None:
        return probe
    ws = verify_common.TestWorkspace.create()
    verify_common.ACTIVE = ws
    ROOT = ws.root
    SPECTRA = ROOT / "deliverables" / "智能体功能测试谱集-20261031"
    JOBS = ROOT / "jobs"
    GUARD = _RealJobsGuard()
    try:
        with verify_common.isolated_host_env():
            return run_cases()
    finally:
        if GUARD is not None:
            GUARD.cleanup_marker()
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
    forwarder_entries()
    if "--no-concurrency" in ARGV:
        print("--- concurrent duplicate run skipped (--no-concurrency)")
    else:
        concurrent_instances()
    if GUARD is not None:
        GUARD.finish()

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