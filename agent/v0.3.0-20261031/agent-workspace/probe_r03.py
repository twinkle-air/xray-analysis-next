"""R03 probe: report publication transactionality, run_model faults, real temp cleanup,
and process isolation.

Cases A-E drive `run_model` with a ctypes shim injected into a *fresh* interpreter, so the
fault belongs to the Windows API, not to the frozen model. Cases D and R1 exercise the
publication transaction: a failed commit must leave the previously published triset
byte-identical, and a failed commit *plus* a failed restore must leave the backup and a
machine-readable recovery note on disk, which blocks the next export until the operator
restores it by hand. Cases F-G exercise the Job Object directly: closing the handle, and
killing the owning process, must both take the whole tree down. Every check reads the
files on disk; nothing is trusted from a self-reported flag.

Layout: the probe lives at `agent/<version>/agent-workspace/` in the repository. That
directory is the Python source root -- `agent/` sits under it -- but it is *not* the
runtime workspace root, which is the directory Workspace points at: the one holding
`agent-workspace/agent`, `jobs/` and `deliverables/`, i.e. the parent of this file in the
repository. In the flat development layout both roles coincide. The probe therefore keeps
the two concepts apart: the source root only ever feeds sys.path/PYTHONPATH, while the
workspace root is discovered by asking Workspace where its registry would land, so the
probe works under whichever layout actually surrounds it. Every child script inserts the
source root on `sys.path` itself instead of relying on the current directory. The probe
creates every job it consumes, so it never reads or mutates another run's tasks.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import time

SOURCE_DIR = pathlib.Path(__file__).resolve().parent   # holds agent/, feeds sys.path


def _find_workspace_root() -> pathlib.Path:
    """The directory Workspace must be pointed at, discovered instead of assumed.

    Workspace resolves ``agent/``, ``jobs/`` and ``deliverables/`` against its root, and
    which directory that is depends on the layout: the checked-out repository nests the
    package under ``<version>/agent-workspace/agent`` (workspace root = this file's
    parent's parent), the flat development layout keeps it at ``agent/`` directly
    (workspace root = this file's directory). Rather than hard-coding a depth, ask
    Workspace itself where its model registry would live and keep the first candidate
    that actually has it on disk. A wrong guess fails loudly here instead of as a
    FileNotFoundError inside the first analysis.
    """
    from agent.core.paths import Workspace

    for base in (SOURCE_DIR, SOURCE_DIR.parent):
        if Workspace(base).model_registry().is_file():
            return base
    raise SystemExit(
        f"R03 probe: no runtime workspace root found around {SOURCE_DIR} "
        f"(looked for agent-workspace/agent or agent under {SOURCE_DIR} and "
        f"{SOURCE_DIR.parent})")


ROOT = _find_workspace_root()             # Workspace root: model, jobs and reports hang off it
SPECTRA_REL = "deliverables" / pathlib.Path("智能体功能测试谱集-20261031") / "01_正常输入" / "T01.json"
WORK = SOURCE_DIR / "probe_r03_workspace"  # probe private scratch, removed at the end
OUT = WORK / "out.json"
MARKER = WORK / "survivor.txt"
TMP_DIR = WORK / ".tmp-V10"
SHIM_DIR = WORK / "shim"

FAIL = []
TRIO = ("results.json", "report.md", "evidence_manifest.json")
CREATED = []                                  # job ids this probe run owns, for the audit


def _find_spectra() -> pathlib.Path:
    """Locate the spectrum input without a hard-coded absolute path.

    The deliverables hang off the runtime workspace root, whichever level that turned out
    to be; the source directory is tried too, so a layout that keeps everything under the
    probe's own directory still works. Anything else is a loud failure, never a silent
    skip.
    """
    for base in (ROOT, SOURCE_DIR):
        candidate = base / SPECTRA_REL
        if candidate.is_file():
            return candidate
    raise SystemExit(
        f"R03 probe: spectrum input not found relative to {SOURCE_DIR} "
        f"(looked for {SPECTRA_REL} under {ROOT} and {SOURCE_DIR})")


SPECTRA = _find_spectra()


def fail(label, detail=""):
    FAIL.append((label, detail))
    print(f"   FAIL {label}: {detail}")


def check(label, cond, detail=""):
    if cond:
        print(f"   PASS {label}")
    else:
        fail(label, detail)


def sha(p: pathlib.Path) -> str:
    return hashlib.file_digest(open(p, "rb"), "sha256").hexdigest()


def try_sha(p: pathlib.Path):
    return sha(p) if p.is_file() else None


def report_dir(job_id: str) -> pathlib.Path:
    return ROOT / "jobs" / job_id / "report"


def job_state(job_id: str) -> dict:
    return json.loads((ROOT / "jobs" / job_id / "audit" / "state.json")
                      .read_text(encoding="utf-8"))


# ------------------------------------------------------------------ probe-owned job

def write_task() -> pathlib.Path:
    """One off-copy of the spectrum, mutated so dedup never hands back another run's job.

    Each call mutates a different channel, so every case generates its own task and the
    workspace's dedup index can never couple two probe cases to the same job.
    """
    CREATED.append(None)  # reserve a slot; the job id fills it in analyze_probe_job
    task = WORK / f"T01_R03_MUTATED_{len(CREATED)}.json"
    if task.exists():
        task.unlink()
    src = json.loads(SPECTRA.read_text(encoding="utf-8"))
    src["counts"][0] += len(CREATED)
    task.write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
    return task


def analyze_probe_job() -> str:
    from agent.core.paths import Workspace
    from agent.core.tools import analyze_spectrum
    res = analyze_spectrum(Workspace(ROOT), write_task(), "r03 probe")
    if res.get("status") != "succeeded":
        fail("probe job analysis", str(res)[:300])
        raise SystemExit(1)
    CREATED[-1] = res["job_id"]
    return res["job_id"]


def drop_job(job_id: str) -> None:
    rmtree_readonly(ROOT / "jobs" / job_id)


def rmtree_readonly(path: pathlib.Path) -> None:
    """Remove a tree even when the agent marked its staged input read-only.

    Windows refuses to delete read-only files, and `Job.create` deliberately leaves the
    staged input read-only, so `shutil.rmtree(ignore_errors=True)` silently leaves the
    whole job directory behind. The failing entry is unlocked and retried instead.
    """
    target = pathlib.Path(path)
    if not target.exists():
        return

    def unlock(_func, bad_path, _exc) -> None:
        p = pathlib.Path(bad_path)
        try:
            os.chmod(p, stat.S_IWRITE)
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        except OSError:
            pass

    try:
        shutil.rmtree(target, onexc=unlock)
    except TypeError:
        # onexc is Python 3.12+; the deprecated `onerror` spelled the same contract.
        shutil.rmtree(target, onerror=unlock)


def audit_leftovers() -> None:
    """Report residue instead of deleting it: hidden leftovers would hide real bugs.

    Every job this run created must already be gone (each case drops its own), and no
    ``.tmp-*`` scratch may remain under ``jobs/``. Anything left is a failure first and
    only then cleaned up, so the operator sees it in the report.
    """
    leftovers = []
    for job_id in CREATED:
        if job_id and (ROOT / "jobs" / job_id).exists():
            leftovers.append(f"job {job_id} was not removed")
    for tmp in sorted((ROOT / "jobs").glob(".tmp-*")) if (ROOT / "jobs").exists() else []:
        leftovers.append(f"scratch {tmp.name} remains under jobs/")
    if leftovers:
        for item in leftovers:
            fail("leftover audit", item)
        for job_id in CREATED:
            if job_id:
                drop_job(job_id)
    check("leftover audit: the probe removed every job it created", not leftovers,
          "; ".join(leftovers))
    leftover_scratch = sorted(p.name for p in (ROOT / "jobs").glob(".tmp-*")) \
        if (ROOT / "jobs").exists() else []
    check("leftover audit: no .tmp-* scratch under jobs/", not leftover_scratch,
          "; ".join(leftover_scratch))


# ---------------------------------------------------------------- R1: publication

def install_replace_fault(rd: pathlib.Path, nth: int):
    """Raise OSError on the nth os.replace that publishes one of the triset files."""
    # the counter only counts the three commit replaces: the draft envelope, the scratch
    # manifest and the job state are all written elsewhere, so a global counter would trip
    # long before the commit block.
    real = os.replace
    counter = [0]

    def counted(a, b):
        dst = pathlib.Path(b)
        if dst.parent != rd or dst.name not in TRIO:
            return real(a, b)
        counter[0] += 1
        if counter[0] == nth:
            raise OSError(13, "simulated publish failure", str(b))
        return real(a, b)

    os.replace = counted
    return real


def install_restore_fault(rd: pathlib.Path):
    """Raise PermissionError only on the rollback copy that results.json performs."""
    # the fault is scoped to `dst.parent == rd`, so the snapshot copy that backs the triset
    # up before the commit is never disturbed -- only the restore path can trip it.
    real = shutil.copy2
    hit = [False]

    def guarded(src, dst, *a, **k):
        if not hit[0] and pathlib.Path(dst).parent == rd and pathlib.Path(dst).name == "results.json":
            hit[0] = True
            raise PermissionError(13, "simulated restore failure", str(dst))
        return real(src, dst, *a, **k)

    shutil.copy2 = guarded
    return real


def install_manifest_fault():
    import agent.core.reporting as R
    real = R._write_manifest

    def broken(path, manifest):
        raise OSError(9, "simulated manifest write failure", str(path))

    R._write_manifest = broken
    return real


def restore_os_replace(real):
    os.replace = real


def restore_copy2(real):
    shutil.copy2 = real


def restore_manifest(real):
    import agent.core.reporting as R
    R._write_manifest = real


def export_for(job_id: str) -> dict:
    from agent.core.paths import Workspace
    from agent.core.tools import export_report
    return export_report(Workspace(ROOT), job_id)


def case_baseline(label: str, job_id: str) -> dict:
    """Clean export: the triset hashes returned here are the "before" for the fault cases."""
    rd = report_dir(job_id)
    res = export_for(job_id)
    out = {
        "status": res["status"],
        "baseline": {n: try_sha(rd / n) for n in TRIO},
        "manifest_ok": manifest_matches_disk(job_id),
    }
    check(f"{label}: export succeeded", out["status"] == "exported", f"status={res['status']}")
    check(f"{label}: all three files exist", all((rd / n).is_file() for n in TRIO))
    check(f"{label}: manifest hashes match disk", out["manifest_ok"] is True, "hash mismatch")
    check(f"{label}: no scratch left behind", not (rd / ".tmp").exists(), ".tmp remains")
    check(f"{label}: no leftover backup", not (rd / ".backup_old").exists(), ".backup_old remains")
    return out


def manifest_matches_disk(job_id: str) -> bool:
    rd = report_dir(job_id)
    try:
        manifest = json.loads((rd / "evidence_manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    for entry in manifest:
        p = pathlib.Path(entry["artifact"])
        if not p.is_absolute():
            p = ROOT / p
        if try_sha(p) != entry.get("sha256"):
            return False
    return True


def case_published_failure(label: str, job_id: str, fault: str) -> dict:
    """Re-export the published triset; the failure must not change a published byte."""
    rd = report_dir(job_id)
    before = {n: try_sha(rd / n) for n in TRIO}
    undo = None
    if fault == "manifest":
        real = install_manifest_fault()
        undo = lambda: restore_manifest(real)
    elif fault in ("replace_1", "replace_2", "replace_3"):
        real = install_replace_fault(rd, int(fault.rsplit("_", 1)[1]))
        undo = lambda: restore_os_replace(real)
    else:
        raise ValueError(fault)
    try:
        res = export_for(job_id)
    finally:
        undo()
    published = {n: try_sha(rd / n) for n in TRIO}
    check(f"{label}: export reported failure", res["status"] == "failed",
          f"status={res['status']}")
    check(f"{label}: warning carries the failure",
          "; ".join(res.get("warnings") or []), "warning empty")
    check(f"{label}: previous triset byte-identical", published == before, str(published))
    check(f"{label}: job state machine is failed",
          job_state(job_id).get("report_state") == "failed", "unexpected report_state")
    return res


def case_combined_failure(label: str, job_id: str) -> None:
    """A publish failure whose own restore also fails: the backup must survive on disk."""
    rd = report_dir(job_id)
    before = {n: try_sha(rd / n) for n in TRIO}
    real_replace = install_replace_fault(rd, 2)
    real_copy2 = install_restore_fault(rd)
    try:
        res = export_for(job_id)
    finally:
        restore_os_replace(real_replace)
        restore_copy2(real_copy2)

    backup = rd / ".backup_old"
    recovery = backup / "RECOVERY_NEEDED.json"
    check(f"{label}: export reported failure", res["status"] == "failed",
          f"status={res['status']}")
    check(f"{label}: raised a rollback error naming the backup",
          str(backup) in "; ".join(res.get("warnings") or []), "no backup path in warning")
    check(f"{label}: backup directory kept on disk", backup.is_dir(), ".backup_old gone")
    check(f"{label}: old results.json kept in the backup",
          (backup / "results.json").is_file() and
          sha(backup / "results.json") == before["results.json"],
          "backup differs from the published version")
    check(f"{label}: recovery note written", recovery.is_file(), "RECOVERY_NEEDED.json missing")
    if recovery.is_file():
        payload = json.loads(recovery.read_text(encoding="utf-8"))
        check(f"{label}: recovery records publish_error", bool(payload.get("publish_error")))
        check(f"{label}: recovery records failed_restores",
              "results.json" in payload.get("failed_restores", {}),
              str(payload.get("failed_restores")))
        check(f"{label}: recovery records backup hashes",
              "results.json" in payload.get("files", {}), str(payload.get("files")))
    # results.json could not be rolled back, so the candidate is still on disk while the
    # previous version only lives in the backup.
    check(f"{label}: the unrestored file keeps its new content",
          try_sha(rd / "report.md") == before["report.md"] and
          try_sha(rd / "evidence_manifest.json") == before["evidence_manifest.json"])


def case_leftover_recovery(label: str, job_id: str) -> None:
    """The leftover recovery backup blocks the next export instead of being overwritten."""
    from agent.core.reporting import ReportError
    rd = report_dir(job_id)
    backup = rd / ".backup_old"
    recovery = backup / "RECOVERY_NEEDED.json"
    if not recovery.is_file():
        fail(f"{label}: recovery note present to guard", str(recovery))
        return
    guard_hash = try_sha(backup / "results.json")
    before = {n: try_sha(rd / n) for n in TRIO}
    try:
        res = export_for(job_id)
        raised = None
    except ReportError as exc:
        res, raised = None, exc
    check(f"{label}: export refused instead of publishing",
          res is None or res["status"] == "failed", f"raised={raised!r}")
    check(f"{label}: failure names the leftover backup",
          (raised is not None and str(backup) in str(raised)) or
          (res is not None and str(backup) in "; ".join(res.get("warnings") or [])),
          "no backup path in the failure")
    check(f"{label}: backup untouched", try_sha(backup / "results.json") == guard_hash,
          "backup hash changed")
    check(f"{label}: formal files untouched", {n: try_sha(rd / n) for n in TRIO} == before,
          "triset changed")
    check(f"{label}: recovery note still readable", recovery.is_file(), "note gone")


def case_recovery_after_leftover(label: str, job_id: str) -> None:
    """Operator-side recovery: restore the backup by hand, then the export works again."""
    rd = report_dir(job_id)
    backup = rd / ".backup_old"
    if not backup.is_dir():
        fail(f"{label}: backup present to recover from", str(backup))
        return
    for n in TRIO:
        if (backup / n).is_file():
            shutil.copy2(backup / n, rd / n)
    shutil.rmtree(backup, ignore_errors=True)
    check(f"{label}: backup restored and cleared", not backup.exists(), ".backup_old remains")
    res = export_for(job_id)
    check(f"{label}: export succeeds after recovery", res["status"] == "exported",
          f"status={res['status']}")
    check(f"{label}: manifest hashes match disk again", manifest_matches_disk(job_id) is True)
    check(f"{label}: scratch cleaned after recovery", not (rd / ".tmp").exists())


def run_r1_cases() -> None:
    """The full transaction matrix: single failures, combined failure, guard, recovery."""
    print("\n-- R1: report export is transactional")
    single = [
        ("manifest write fails", "manifest"),
        ("first atomic replace fails", "replace_1"),
        ("second atomic replace fails", "replace_2"),
        ("third atomic replace fails", "replace_3"),
    ]
    for label, fault in single:
        print(f"\n-- {label}")
        job = analyze_probe_job()
        case_baseline(label, job)
        case_published_failure(label, job, fault)
        drop_job(job)

    print("\n-- publish failure plus restore failure keeps the recovery backup")
    job = analyze_probe_job()
    case_baseline("publish+restore", job)
    case_combined_failure("publish+restore", job)
    case_leftover_recovery("leftover recovery guard", job)
    case_recovery_after_leftover("hand recovery unblocks the export", job)
    drop_job(job)

    print("\n-- first export: a failure before any publication leaves no triset at all")
    for label, fault in single:
        print(f"\n-- {label} (first export)")
        job = analyze_probe_job()
        case_published_failure(label, job, fault)
        rd = report_dir(job)
        check(f"{label}: no published file remains", not any((rd / n).exists() for n in TRIO))
        check(f"{label}: no scratch left behind", not (rd / ".tmp").exists(), ".tmp remains")
        check(f"{label}: no leftover backup", not (rd / ".backup_old").exists(),
              ".backup_old remains")
        drop_job(job)


# ---------------------------------------------------------- A-E + D: run_model shims

# each shim replaces a Job Object API entry point before agent.core.runner imports it.
SHIMS = {
    "query_fails": (
        "import ctypes\n"
        "k = ctypes.windll.kernel32\n"
        "def fake(*a):\n"
        "    k.SetLastError(87)\n"
        "    return 0\n"
        "k.QueryInformationJobObject = fake\n"
    ),
    "open_fails": (
        "import ctypes\n"
        "k = ctypes.windll.kernel32\n"
        "def fake(*a):\n"
        "    return 0\n"
        "k.OpenProcess = fake\n"
    ),
    "assign_fails": (
        "import ctypes\n"
        "k = ctypes.windll.kernel32\n"
        "def fake(*a):\n"
        "    k.SetLastError(87)\n"
        "    return 0\n"
        "k.AssignProcessToJobObject = fake\n"
    ),
    "create_fails": (
        "import ctypes\n"
        "k = ctypes.windll.kernel32\n"
        "def fake(*a):\n"
        "    k.SetLastError(87)\n"
        "    return 0\n"
        "k.CreateJobObjectW = fake\n"
    ),
}

RUNNER_TEMPLATE = (
    "import json, pathlib, sys, time\n"
    "sys.path.insert(0, " + repr(str(SOURCE_DIR)) + ")\n"
    "from agent.core.paths import Workspace\n"
    "from agent.core.runner import run_model\n"
    "MARKER = pathlib.Path(" + repr(str(MARKER)) + ")\n"
    "if MARKER.exists():\n"
    "    MARKER.unlink()\n"
    "res = run_model(Workspace(" + repr(str(ROOT)) + "), 'V10',\n"
    "                pathlib.Path(" + repr(str(SPECTRA)) + "),\n"
    "                pathlib.Path(" + repr(str(OUT)) + "), timeout={timeout})\n"
    "# give a child that escaped binding a moment to finish and release the temp dir\n"
    "time.sleep(2.5)\n"
    "print(json.dumps({{\n"
    "    'error_code': res['error_code'],\n"
    "    'temp_cleaned': res['temp_cleaned'],\n"
    "    'wall_s': res['wall_s'],\n"
    "    'tmp_exists': pathlib.Path(" + repr(str(TMP_DIR)) + ").exists(),\n"
    "    'survivor': MARKER.exists(),\n"
    "}}))\n"
)


def run_shim_case(name, patch, timeout=10.0):
    shim_dir = SHIM_DIR
    shim_dir.mkdir(parents=True, exist_ok=True)
    (shim_dir / "sitecustomize.py").write_text(patch, encoding="utf-8")
    script = WORK / f"case_runner_{name}.py"
    script.write_text(RUNNER_TEMPLATE.format(timeout=timeout), encoding="utf-8")
    # the shim directory is only reachable through PYTHONPATH; the source root must stay on
    # it too, or the generated script cannot import the package its sitecustomize patches,
    # while the workspace root passed to run_model is threaded through the script itself.
    env = dict(os.environ,
               PYTHONPATH=str(shim_dir) + os.pathsep + str(SOURCE_DIR),
               PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run([sys.executable, str(script)], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env,
                              cwd=str(SOURCE_DIR), timeout=240)
        if proc.returncode != 0 or not proc.stdout.strip():
            # an early crash has to surface its stderr, or the real cause gets buried under
            # an IndexError from splitlines() instead of the fault it belongs to.
            tail = proc.stderr.strip().splitlines()[-1][:400] if proc.stderr.strip() else ""
            fail(f"{name}: child did not produce usable output", f"rc={proc.returncode} {tail}")
            return ({"error_code": "PROBE_CRASH", "temp_cleaned": False,
                     "wall_s": 0.0, "tmp_exists": TMP_DIR.exists(), "survivor": False},
                    proc.returncode, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1]), proc.returncode, proc.stderr
    finally:
        shutil.rmtree(shim_dir, ignore_errors=True)
        if script.exists():
            script.unlink()


def run_shim_cases() -> None:
    print("\n-- shimmed run_model cases (A-E), each asserting the real scratch dir is gone")
    for name, patch in SHIMS.items():
        print(f"\n-- {name}")
        if TMP_DIR.exists():
            shutil.rmtree(TMP_DIR, ignore_errors=True)
        if OUT.exists():
            OUT.unlink()
        res, rc, err = run_shim_case(name, patch)
        print(f"   error_code={res['error_code']} temp_cleaned={res['temp_cleaned']} "
              f"wall={res['wall_s']:.3f}s tmp_exists={res['tmp_exists']} survivor={res['survivor']}")
        check(f"{name}: fails rather than succeeds",
              res["error_code"] in ("TIMEOUT", "INTEGRITY_FAILED"),
              f"error_code={res['error_code']}")
        check(f"{name}: self-reported temp_cleaned", res["temp_cleaned"] is True,
              f"temp_cleaned={res['temp_cleaned']}")
        check(f"{name}: real scratch directory removed", not res["tmp_exists"],
              f"{TMP_DIR} still exists")
        check(f"{name}: clean interpreter exit", rc == 0, f"rc={rc} err={err[:200]}")

    print("\n-- D control: unshimmed run_model must time out and leave nothing")
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR, ignore_errors=True)
    if OUT.exists():
        OUT.unlink()
    res, rc, err = run_shim_case("control", "", timeout=1.0)
    check("control: returns TIMEOUT", res["error_code"] == "TIMEOUT",
          f"error_code={res['error_code']}")
    check("control: real scratch directory removed", not res["tmp_exists"],
          f"{TMP_DIR} still exists")
    check("control: no result published", not OUT.exists(), "result file appeared")


# ---------------------------------------------------------------- F-G: isolation

CHILD_SCRIPT = WORK / "probe_child.py"
GRANDCHILD_SCRIPT = WORK / "probe_grandchild.py"
WRAPPER_SCRIPT = WORK / "probe_wrapper.py"


def _path_arg(path: pathlib.Path) -> str:
    """Embed an absolute path in a generated script without quoting or escape trouble."""
    return repr(str(path))


def write_probe_scripts() -> None:
    CHILD_SCRIPT.write_text(
        "import pathlib, subprocess, sys, time\n"
        "MARKER = pathlib.Path(" + _path_arg(MARKER) + ")\n"
        "if MARKER.exists():\n"
        "    MARKER.unlink()\n"
        "grand = subprocess.Popen([sys.executable, str(" + _path_arg(GRANDCHILD_SCRIPT) + ")])\n"
        "time.sleep(10)\n"
        "grand.wait()\n",
        encoding="utf-8",
    )
    GRANDCHILD_SCRIPT.write_text(
        "import pathlib, time\n"
        "MARKER = pathlib.Path(" + _path_arg(MARKER) + ")\n"
        "time.sleep(5)\n"
        "MARKER.write_text('survived')\n",
        encoding="utf-8",
    )
    WRAPPER_SCRIPT.write_text(
        "import pathlib, subprocess, sys, time\n"
        "sys.path.insert(0, " + _path_arg(SOURCE_DIR) + ")\n"
        "from agent.core.runner import _JobHandle\n"
        "child = subprocess.Popen([sys.executable, str(" + _path_arg(CHILD_SCRIPT) + ")],\n"
        "                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "job = _JobHandle()\n"
        "job.assign(child)\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )


def kill(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_for_marker(timeout: float) -> bool:
    """Poll for the marker the grandchild writes, up to the deadline."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if MARKER.exists():
            return True
        time.sleep(0.1)
    return False


def _close_handle_scenario(job, label: str) -> bool:
    """Bind a child to a job, close the handle, report whether the grandchild survived."""
    import ctypes
    if MARKER.exists():
        MARKER.unlink()
    proc = subprocess.Popen([sys.executable, str(CHILD_SCRIPT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not job.assign(proc):
        # the child is not inside the job, so this scenario cannot prove anything; report
        # it rather than abort the whole probe and leave the scratch dir behind.
        check(f"close_handle: {label}: binding the probe child", False, "assign failed")
        return False
    time.sleep(0.3)
    # this is the call whose guarantee KILL_ON_JOB_CLOSE delivers; without the flag the
    # child and its grandchild outlive the job object.
    ctypes.windll.kernel32.CloseHandle(job.handle)
    job.handle = None
    survived = _wait_for_marker(8.0)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        kill(proc.pid)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    return survived


def _job_without_flag():
    """A Job Object that binds and closes cleanly but was never given KILL_ON_JOB_CLOSE."""
    import ctypes
    from agent.core.runner import _JobHandle
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise OSError("CreateJobObjectW failed in the negative control")
    job = _JobHandle()
    job.handle = handle
    return job


def _job_handle():
    from agent.core.runner import _JobHandle
    return _JobHandle()


def case_close_handle() -> None:
    """F: closing the job handle must kill the whole tree, and the flag is what makes it so.

    KILL_ON_JOB_CLOSE is what makes that happen: _JobHandle sets the flag and re-queries it
    before it keeps the handle, so a handle without the flag is discarded rather than
    trusted. Closing the handle is the exact event a crashing runner triggers.

    The negative control first proves that a plain Job Object -- one that binds and closes
    just as cleanly -- does not take the tree down, so the later pass is not vacuous.
    """
    control = _close_handle_scenario(_job_without_flag(), "negative control (flag unset)")
    check("close_handle: negative control -- a flagless job leaks the grandchild", control,
          "grandchild did not survive; the control is not exercising the leak")
    survived = _close_handle_scenario(_job_handle(), "KILL_ON_JOB_CLOSE set")
    check("close_handle: closing the handle kills the whole tree", not survived,
          "grandchild survived the handle close")


def case_parent_abnormal_exit() -> None:
    """G: a runner that crashes (or is killed) must not leak its descendants."""
    if MARKER.exists():
        MARKER.unlink()
    wrapper = subprocess.Popen([sys.executable, str(WRAPPER_SCRIPT)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    time.sleep(1.0)
    kill(wrapper.pid)
    try:
        wrapper.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    time.sleep(2.5)
    survived = MARKER.exists()
    # any grandchild still breathing would write the marker later; give it one more chance
    time.sleep(3.0)
    survived = survived or MARKER.exists()
    check("parent_abnormal_exit: no descendant survives a crashed runner", not survived,
          "survivor.txt written after the wrapper was killed")


def check_workspace() -> None:
    """Fail loudly up front when the frozen model package the first analysis needs is absent.

    The probe cannot exercise publication without an analysis to publish, and a missing
    package is a setup problem -- say so here instead of letting it surface as a
    FileNotFoundError several cases in.
    """
    from agent.core.paths import Workspace
    from agent.core.registry import ModelRegistry

    registry = ModelRegistry(Workspace(ROOT))
    for version in sorted(registry.models()):
        integrity = ROOT / registry.model(version)["integrity_file"]
        check(f"model package for {version} is present on disk", integrity.is_file(),
              f"{integrity} is missing")


# ------------------------------------------------------------------------------ main

def main() -> int:
    print("R03 probe: report publication transactionality, run_model faults, process isolation")
    if not SPECTRA.is_file():
        fail("spectrum input present", f"cannot locate {SPECTRA}")
        print("\n" + "=" * 70)
        if FAIL:
            print(f"{len(FAIL)} FAILED:")
            for label, detail in FAIL:
                print(f"  - {label}: {detail}")
        return 1
    check("spectrum input present", SPECTRA.is_file())
    print(f"   source root {SOURCE_DIR}")
    print(f"   workspace root {ROOT}")
    check_workspace()
    WORK.mkdir(parents=True, exist_ok=True)

    run_r1_cases()
    run_shim_cases()

    write_probe_scripts()
    print("\n-- F: closing the job handle kills the whole tree (with negative control)")
    case_close_handle()
    print("\n-- G: killing the owning process kills the whole tree")
    case_parent_abnormal_exit()

    audit_leftovers()
    shutil.rmtree(WORK, ignore_errors=True)
    print("\n" + "=" * 70)
    if FAIL:
        print(f"{len(FAIL)} FAILED:")
        for label, detail in FAIL:
            print(f"  - {label}: {detail}")
        return 1
    print("R03 PROBE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
