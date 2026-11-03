"""R03 probe: report publication transactionality, run_model faults, real temp cleanup,
and process isolation.

Cases A-E drive `run_model` with a ctypes shim injected into a *fresh* interpreter, so the
fault belongs to the Windows API, not to the frozen model. Cases R1 re-export an already
successful report while failing the manifest write and the final atomic replace: the
previously published triset must stay byte-identical. Cases F-G exercise the Job Object
directly: closing the handle, and killing the owning process, must both take the whole tree
down. Every case asserts on the actual files on disk, never on a self-reported flag.
"""
from __future__ import annotations

import json, os, pathlib, shutil, subprocess, sys, time

ROOT = pathlib.Path("C:/Users/Twinkle/Desktop/通用X射线谱分析")
SPECTRA = ROOT / "deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json"
PROBE = ROOT / "jobs/r03_probe"
OUT = PROBE / "out.json"
MARKER = PROBE / "survivor.txt"
TMP_DIR = PROBE / ".tmp-V10"

FAIL = []


def fail(label, detail=""):
    FAIL.append((label, detail))
    print(f"   FAIL {label}: {detail}")


def check(label, cond, detail=""):
    if cond:
        print(f"   PASS {label}")
    else:
        fail(label, detail)


# ---------------------------------------------------------------------- R1: publication

# the published triset must survive a failed re-export byte-identical. Every check reads the
# files on disk; nothing is trusted from a self-reported flag.
#
# the fault is spliced into the runner script itself rather than injected through
# sitecustomize: sitecustomize runs before the script puts '.' on sys.path, so it could not
# import agent.core. The baseline export runs before the fault is applied, so only the
# re-export is affected.
JOB = None

R1_TEMPLATE = (
    "import hashlib, json, os, pathlib, shutil, sys\n"
    "sys.path.insert(0, '.')\n"
    "import agent.core.reporting as R\n"
    "from agent.core.job import Job\n"
    "from agent.core.paths import Workspace\n"
    "from agent.core.tools import export_report\n"
    "ROOT = pathlib.Path(r'{root}')\n"
    "TRIO = ('results.json', 'report.md', 'evidence_manifest.json')\n"
    "def sha(p):\n"
    "    return hashlib.file_digest(open(p, 'rb'), 'sha256').hexdigest()\n"
    "def report_dir():\n"
    "    return ROOT / 'jobs' / JOB / 'report'\n"
    "def pick_job():\n"
    "    for d in sorted((ROOT / 'jobs').iterdir()):\n"
    "        st = d / 'audit' / 'state.json'\n"
    "        if not st.is_file():\n"
    "            continue\n"
    "        try:\n"
    "            state = json.loads(st.read_text(encoding='utf-8'))\n"
    "        except Exception:\n"
    "            continue\n"
    "        if state.get('stage') == 'succeeded':\n"
    "            return d.name\n"
    "    return None\n"
    "JOB = pick_job()\n"
    "if JOB is None:\n"
    "    print(json.dumps(['no_succeeded_job']))\n"
    "    sys.exit(0)\n"
    "def reset():\n"
    "    shutil.rmtree(report_dir(), ignore_errors=True)\n"
    "    job = Job.open(Workspace(ROOT), JOB)\n"
    "    job.set('sample_description', 'baseline')\n"
    "    job.set('report_state', None)\n"
    "    job.save()\n"
    "def hashes():\n"
    "    out = dict()\n"
    "    for n in TRIO:\n"
    "        p = report_dir() / n\n"
    "        try:\n"
    "            out[n] = sha(p)\n"
    "        except OSError:\n"
    "            out[n] = None\n"
    "    return out\n"
    "def files_present():\n"
    "    return all((report_dir() / n).exists() for n in TRIO)\n"
    "def manifest_ok():\n"
    "    try:\n"
    "        man = json.loads((report_dir() / 'evidence_manifest.json').read_text(encoding='utf-8'))\n"
    "    except Exception:\n"
    "        return False\n"
    "    for e in man:\n"
    "        p = pathlib.Path(e['artifact'])\n"
    "        if not p.is_absolute():\n"
    "            p = ROOT / p\n"
    "        try:\n"
    "            if hashlib.file_digest(open(p, 'rb'), 'sha256').hexdigest() != e['sha256']:\n"
    "                return False\n"
    "        except Exception:\n"
    "            return False\n"
    "    return True\n"
    "def scratch_gone():\n"
    "    rd = report_dir()\n"
    "    return not (rd / '.tmp').exists() and not (rd / '.backup_old').exists()\n"
    "reset()\n"
    "res = export_report(Workspace(ROOT), JOB)\n"
    "first = hashes()\n"
    "__POST_PATCH__\n"
    "job = Job.open(Workspace(ROOT), JOB)\n"
    "job.set('sample_description', 'candidate mutation')\n"
    "job.save()\n"
    "res2 = export_report(Workspace(ROOT), JOB)\n"
    "second = hashes()\n"
    "print(json.dumps([\n"
    "    res['status'],\n"
    "    res2['status'],\n"
    "    first == second,\n"
    "    files_present(),\n"
    "    manifest_ok(),\n"
    "    scratch_gone(),\n"
    "]))\n"
)


def render_r1(patch: str) -> str:
    return R1_TEMPLATE.format(root=ROOT).replace("__POST_PATCH__", patch)


def run_r1_case(label, patch):
    PROBE.mkdir(parents=True, exist_ok=True)
    script = PROBE / "r1_runner.py"
    script.write_text(render_r1(patch), encoding="utf-8")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run([sys.executable, str(script)], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env,
                              cwd=str(ROOT), timeout=180)
        lines = proc.stdout.strip().splitlines()
        if lines and lines[-1] == "['no_succeeded_job']":
            return (["no_succeeded_job"], 9,
                    proc.stderr or "no succeeded job present to export from")
        return json.loads(lines[-1]), proc.returncode, proc.stderr
    finally:
        if script.exists():
            script.unlink()


R1_NO_FAULT = ""
R1_MANIFEST_FAULT = (
    "import agent.core.reporting as R\n"
    "_wm = R._write_manifest\n"
    "def broken(path, manifest):\n"
    "    raise OSError(9, 'simulated manifest write failure', str(path))\n"
    "R._write_manifest = broken\n"
)
R1_REPLACE_FAULT = (
    "import os\n"
    "_real = os.replace\n"
    "n = [0]\n"
    "def counted(a, b):\n"
    "    dst = pathlib.Path(b)\n"
    "    # only the three replaces inside the publication commit block count; the draft\n"
    "    # writes land in .tmp/ and a job state save lands in audit/, so a global counter\n"
    "    # would trip on those before reaching the commit block.\n"
    "    if dst.parent != report_dir() or dst.name not in TRIO:\n"
    "        return _real(a, b)\n"
    "    n[0] += 1\n"
    "    # the commit block moves json, then report.md, then the manifest; report.md is the\n"
    "    # second, and the first that would otherwise commit new candidate content.\n"
    "    if n[0] == 2:\n"
    "        raise OSError(5, 'simulated replace failure', str(b))\n"
    "    return _real(a, b)\n"
    "os.replace = counted\n"
)

# A first export has nothing to roll back to, so a failure inside the commit block must
# not leave a half-published triset where a later run could mistake it for a real report.
R1_FIRST_TEMPLATE = (
    "import hashlib, json, os, pathlib, shutil, sys\n"
    "sys.path.insert(0, '.')\n"
    "import agent.core.reporting as R\n"
    "from agent.core.job import Job\n"
    "from agent.core.paths import Workspace\n"
    "from agent.core.tools import export_report\n"
    "ROOT = pathlib.Path(r'{root}')\n"
    "TRIO = ('results.json', 'report.md', 'evidence_manifest.json')\n"
    "def report_dir():\n"
    "    return ROOT / 'jobs' / JOB / 'report'\n"
    "def pick_job():\n"
    "    for d in sorted((ROOT / 'jobs').iterdir()):\n"
    "        st = d / 'audit' / 'state.json'\n"
    "        if not st.is_file():\n"
    "            continue\n"
    "        try:\n"
    "            state = json.loads(st.read_text(encoding='utf-8'))\n"
    "        except Exception:\n"
    "            continue\n"
    "        if state.get('stage') == 'succeeded':\n"
    "            return d.name\n"
    "    return None\n"
    "JOB = pick_job()\n"
    "if JOB is None:\n"
    "    print(json.dumps(['no_succeeded_job']))\n"
    "    sys.exit(0)\n"
    "# the report dir is empty, so nothing here predates this export\n"
    "shutil.rmtree(report_dir(), ignore_errors=True)\n"
    "__POST_FAULT__\n"
    "job = Job.open(Workspace(ROOT), JOB)\n"
    "job.set('sample_description', 'candidate mutation')\n"
    "job.save()\n"
    "res = export_report(Workspace(ROOT), JOB)\n"
    "left = [(report_dir() / n).exists() for n in TRIO]\n"
    "print(json.dumps([\n"
    "    res['status'],\n"
    "    any(left),\n"
    "    (report_dir() / '.tmp').exists(),\n"
    "    (report_dir() / '.backup_old').exists(),\n"
    "]))\n"
)


def render_r1_first(patch: str) -> str:
    return R1_FIRST_TEMPLATE.format(root=ROOT).replace("__POST_FAULT__", patch)


def run_r1_first_case(label, patch):
    PROBE.mkdir(parents=True, exist_ok=True)
    script = PROBE / "r1_first_runner.py"
    script.write_text(render_r1_first(patch), encoding="utf-8")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run([sys.executable, str(script)], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env,
                              cwd=str(ROOT), timeout=180)
        lines = proc.stdout.strip().splitlines()
        if lines and lines[-1] == "['no_succeeded_job']":
            return (["no_succeeded_job"], 9,
                    proc.stderr or "no succeeded job present to export from")
        return json.loads(lines[-1]), proc.returncode, proc.stderr
    finally:
        if script.exists():
            script.unlink()


def replace_fault_on(nth: int) -> str:
    """Fail the nth os.replace that targets a published file, letting the rest proceed.

    The counter is scoped to the three commit replaces rather than global, because the
    draft envelope and report are written to .tmp/ and the job state is saved to audit/;
    a global counter would trip on one of those before reaching the commit block.
    """
    return (
        "import os\n"
        "_real = os.replace\n"
        "n = [0]\n"
        "def counted(a, b):\n"
        "    dst = pathlib.Path(b)\n"
        "    if dst.parent != report_dir() or dst.name not in TRIO:\n"
        "        return _real(a, b)\n"
        "    n[0] += 1\n"
        f"    if n[0] == {nth}:\n"
        "        raise OSError(13, 'simulated first-export replace failure', str(b))\n"
        "    return _real(a, b)\n"
        "os.replace = counted\n"
    )


R1_MANIFEST_FAULT = (
    "import agent.core.reporting as R\n"
    "_wm = R._write_manifest\n"
    "def broken(path, manifest):\n"
    "    raise OSError(9, 'simulated manifest write failure', str(path))\n"
    "R._write_manifest = broken\n"
)

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
    "sys.path.insert(0, '.')\n"
    "from agent.core.paths import Workspace\n"
    "from agent.core.runner import run_model\n"
    "MARKER = pathlib.Path(r'{marker}')\n"
    "if MARKER.exists():\n"
    "    MARKER.unlink()\n"
    "res = run_model(Workspace(pathlib.Path(r'{root}')), 'V10',\n"
    "                pathlib.Path(r'{spectra}'), pathlib.Path(r'{out}'), timeout={timeout})\n"
    "# give a child that escaped binding a moment to finish and release the temp dir\n"
    "time.sleep(2.5)\n"
    "print(json.dumps({{\n"
    "    'error_code': res['error_code'],\n"
    "    'temp_cleaned': res['temp_cleaned'],\n"
    "    'wall_s': res['wall_s'],\n"
    "    'tmp_exists': pathlib.Path(r'{tmp}').exists(),\n"
    "    'survivor': MARKER.exists(),\n"
    "}}))\n"
)


def run_shim_case(name, patch, timeout=10.0):
    shim_dir = PROBE / "shim"
    shim_dir.mkdir(parents=True, exist_ok=True)
    (shim_dir / "sitecustomize.py").write_text(patch, encoding="utf-8")
    script = PROBE / "case_runner.py"
    script.write_text(RUNNER_TEMPLATE.format(root=ROOT, spectra=SPECTRA, out=OUT,
        marker=MARKER, tmp=TMP_DIR, timeout=timeout), encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(shim_dir), PYTHONUTF8="1",
               PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.run([sys.executable, str(script)], capture_output=True,
                              text=True, encoding="utf-8", env=env,
                              cwd=str(ROOT), timeout=180)
        body = proc.stdout.strip().splitlines()[-1]
        return json.loads(body), proc.returncode, proc.stderr
    finally:
        shutil.rmtree(shim_dir, ignore_errors=True)
        if script.exists():
            script.unlink()


# ------------------------------------------------------------------------ isolation F-G

CHILD_SCRIPT = PROBE / "probe_child.py"
GRANDCHILD_SCRIPT = PROBE / "probe_grandchild.py"
WRAPPER_SCRIPT = PROBE / "probe_wrapper.py"


def _path_arg(path: pathlib.Path) -> str:
    """Embed an absolute path in a generated script without quoting or escape trouble.

    A raw string literal around a Windows path breaks on a trailing backslash, and a
    normal one treats every backslash as the start of an escape, so ``repr()`` is used
    instead of either.
    """
    return repr(str(path))


def write_probe_scripts() -> None:
    GRANDCHILD_SCRIPT.write_text(
        "import pathlib, time\n"
        "MARKER = pathlib.Path(" + _path_arg(MARKER) + ")\n"
        "time.sleep(5)\n"
        "MARKER.write_text('survived')\n",
        encoding="utf-8",
    )
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
    WRAPPER_SCRIPT.write_text(
        "import pathlib, subprocess, sys, time\n"
        "sys.path.insert(0, '.')\n"
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
        # it rather than aborting the whole probe and leaving the scratch dir behind.
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


def case_close_handle() -> bool:
    """F: closing the job handle must kill the whole tree, and the flag is what makes it so.

    KILL_ON_JOB_CLOSE is what makes that happen: _JobHandle sets the flag and re-queries it
    before it keeps the handle, so a handle without the flag is discarded rather than
    trusted. Closing the handle is the exact event a crashing runner triggers.

    The negative control first proves that a plain Job Object -- one that binds and closes
    just as cleanly -- does not take the tree down, so the later pass is not vacuous.
    """
    import ctypes
    from agent.core.runner import _JobHandle

    control = _close_handle_scenario(_job_without_flag(), "negative control (flag unset)")
    check("close_handle: negative control -- a flagless job leaks the grandchild", control,
          "grandchild did not survive; the control is not exercising the leak")
    survived = _close_handle_scenario(_JobHandle(), "KILL_ON_JOB_CLOSE set")
    check("close_handle: closing the handle kills the whole tree", not survived,
          "grandchild survived the handle close")
    return survived

def case_parent_abnormal_exit():
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
    return survived


# ------------------------------------------------------------------------------ main

if __name__ == "__main__":
    print("R03 probe: Job Object faults, real temp cleanup, process isolation")

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
        # the frozen model entry point never writes survivor.txt, so a "no grandchild
        # survived" check here would be vacuously true; it is covered for real by cases F
        # and G, which spawn a two-level tree and assert on the actual file.
        check(f"{name}: clean interpreter exit", rc == 0, f"rc={rc} err={err[:200]}")

    print("\n-- D control: unshimmed run_model must time out and leave nothing")
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR, ignore_errors=True)
    if OUT.exists():
        OUT.unlink()
    res, rc, err = run_shim_case("control", "", timeout=1.0)
    check("control: returns TIMEOUT", res["error_code"] == "TIMEOUT", f"error_code={res['error_code']}")
    check("control: real scratch directory removed", not res["tmp_exists"], f"{TMP_DIR} still exists")
    check("control: no result published", not OUT.exists(), "result file appeared")

    print("\n-- R1: report export is transactional")
    for label, patch in (("first_export", R1_NO_FAULT),
                         ("manifest_write_fails", R1_MANIFEST_FAULT),
                         ("atomic_replace_fails", R1_REPLACE_FAULT)):
        print(f"\n-- {label}")
        res, rc, err = run_r1_case(label, patch)
        if res == ["no_succeeded_job"]:
            check(f"{label}: a succeeded job exists to export from", False, err)
            continue
        print(f"   first_status={res[0]} second_status={res[1]} triset_unchanged={res[2]} "
              f"manifest_ok={res[3]} scratch_gone={res[4]}")
        check(f"{label}: first export succeeds", res[0] == "exported", f"first_status={res[0]}")
        if label == "first_export":
            check(f"{label}: re-export succeeds", res[1] == "exported", f"second_status={res[1]}")
            check(f"{label}: manifest hashes match disk", res[3], "manifest hash mismatch")
        else:
            check(f"{label}: failed re-export raises rather than publishes", res[1] == "failed",
                  f"second_status={res[1]}")
            check(f"{label}: previous triset is byte-identical", res[2], "published files changed")
        check(f"{label}: no scratch left behind", res[4], ".tmp or .backup_old remains")
        check(f"{label}: clean interpreter exit", rc == 0, f"rc={rc} err={err[:200]}")

    print("\n-- R1 first export: a failure on the very first export must leave no triset")
    for label, patch in (
        ("second_replace_fails", replace_fault_on(2)),
        ("third_replace_fails", replace_fault_on(3)),
    ):
        print(f"\n-- {label}")
        res, rc, err = run_r1_first_case(label, patch)
        if res == ["no_succeeded_job"]:
            check(f"{label}: a succeeded job exists to export from", False, err)
            continue
        print(f"   status={res[0]} triset_present={res[1]} tmp_left={res[2]} "
              f"backup_old_left={res[3]}")
        check(f"{label}: export reports failure", res[0] == "failed", f"status={res[0]}")
        check(f"{label}: no published triset file remains", not res[1],
              "results.json, report.md or evidence_manifest.json present")
        check(f"{label}: scratch directory removed", not res[2], ".tmp remains")
        check(f"{label}: backup directory removed", not res[3], ".backup_old remains")
        check(f"{label}: clean interpreter exit", rc == 0, f"rc={rc} err={err[:200]}")

    write_probe_scripts()


    print("\n-- F: closing the job handle kills the whole tree (with negative control)")
    case_close_handle()

    print("\n-- G: killing the owning process kills the whole tree")
    case_parent_abnormal_exit()

    if PROBE.exists():
        shutil.rmtree(PROBE, ignore_errors=True)

    print("\n" + "=" * 70)
    if FAIL:
        print(f"{len(FAIL)} FAILED:")
        for label, detail in FAIL:
            print(f"  - {label}: {detail}")
        sys.exit(1)
    print("R03 PROBE PASSED")