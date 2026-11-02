"""R03 probe: when Job Object binding fails, run_model must NOT report success.

The Win32 calls live in the runner process, so failures are injected with a
sitecustomize.py on PYTHONPATH (auto-imported by `site` at startup). The probe runs
run_model in a child interpreter so the shim is actually active in the process that
spawns and kills the model.

The model entry is a stand-in that spawns a grandchild and then sleeps, so the probe can
assert that no grandchild survives the failure path. Case D repeats the run with no shim:
it proves the stand-in really runs and really gets killed, which is what keeps A-C from
passing for the wrong reason.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
# repo layout: this file sits in agent-workspace/, so the workspace root is its parent;
# local layout: it sits at the workspace root itself.
ROOT = HERE.parent if (HERE.parent / "deliverables").exists() else HERE

# kept out of jobs/ on purpose: a scratch dir left there is picked up by the suites'
# leftover-scratch checks and by the report job scan.
PROBE = pathlib.Path(tempfile.mkdtemp(prefix="xrf-r03-probe-"))
FAKE_WS = PROBE / "ws"
SLOW_ENTRY = FAKE_WS / "deliverables" / "xrf-models-v9-v10-20261030" / "run_model.py"
OUT = PROBE / "out.json"
SPAWNED = PROBE / "spawned.txt"
SURVIVOR = PROBE / "survivor.txt"
TASK = ROOT / "deliverables" / "智能体功能测试谱集-20261031" / "01_正常输入" / "T01.json"

CHILD_TIMEOUT = 1.0
GRANDCHILD_DELAY = 3.0
LEAK_WAIT = GRANDCHILD_DELAY + 0.5

CHILD = r'''
import json, pathlib, sys
from agent.core.paths import Workspace
from agent.core.runner import run_model

ws = Workspace(sys.argv[1])
res = run_model(ws, "V10", pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]),
                timeout=float(sys.argv[4]))
print(json.dumps({"error_code": res["error_code"], "temp_cleaned": res["temp_cleaned"],
                  "wall_s": res["wall_s"], "stderr": res["stderr"][-600:]}))
'''

GRANDCHILD = (
    "import time, pathlib\n"
    "time.sleep(%r)\n"
    "pathlib.Path(r'%s').write_text('grandchild survived')\n" % (GRANDCHILD_DELAY, SURVIVOR)
)

SLOW_SOURCE = (
    "import pathlib, subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, '-c', %r], stdout=subprocess.DEVNULL,\n"
    "                 stderr=subprocess.DEVNULL)\n"
    "pathlib.Path(r'%s').write_text(str(time.time()))\n"
    "time.sleep(60)\n" % (GRANDCHILD, SPAWNED)
)

SHIMS = {
    "query_fails": "k.QueryInformationJobObject = fake",
    "open_fails": "k.OpenProcess = fake",
    "assign_fails": "k.AssignProcessToJobObject = fake",
}


def prepare():
    if PROBE.exists():
        shutil.rmtree(PROBE, ignore_errors=True)
    SLOW_ENTRY.parent.mkdir(parents=True, exist_ok=True)
    SLOW_ENTRY.write_text(SLOW_SOURCE, encoding="utf-8")


def write_shim(shim_dir, patch):
    shim_dir.mkdir(parents=True, exist_ok=True)
    (shim_dir / "sitecustomize.py").write_text(
        "import ctypes\n"
        "k = ctypes.windll.kernel32\n"
        "def fake(*a):\n"
        "    try:\n"
        "        k.SetLastError(87)\n"
        "    except Exception:\n"
        "        pass\n"
        "    return 0\n"
        + SHIMS[patch] + "\n",
        encoding="utf-8")


def run_case(patch):
    """Run run_model with one broken Win32 call, or with none (patch is None)."""
    for path in (OUT, SPAWNED, SURVIVOR):
        if path.exists():
            path.unlink()
    shim_dir = PROBE / "shim"
    shutil.rmtree(shim_dir, ignore_errors=True)
    parts = [str(HERE)]
    if patch is not None:
        write_shim(shim_dir, patch)
        parts.append(str(shim_dir))
    if os.environ.get("PYTHONPATH"):
        parts.append(os.environ["PYTHONPATH"])

    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=os.pathsep.join(parts))
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, str(FAKE_WS), str(TASK), str(OUT), str(CHILD_TIMEOUT)],
        env=env, cwd=str(ROOT), capture_output=True, timeout=120)
    time.sleep(LEAK_WAIT)

    stdout = proc.stdout.decode("utf-8", "replace").strip()
    stderr = proc.stderr.decode("utf-8", "replace").strip()
    lines = [line for line in stdout.splitlines() if line.strip()]
    if proc.returncode != 0 or not lines:
        raise SystemExit("run_model subprocess failed (rc=%s)\nstdout=%s\nstderr=%s"
                         % (proc.returncode, stdout[-800:], stderr[-1500:]))
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise SystemExit("run_model output is not JSON: %r\nstderr=%s"
                         % (lines[-1], stderr[-1500:])) from exc


def check(label, res, allowed, spawned_expected=None):
    print("   error_code=%s temp_cleaned=%s wall=%.2fs spawned=%s survivor=%s"
          % (res["error_code"], res["temp_cleaned"], res["wall_s"],
             SPAWNED.exists(), SURVIVOR.exists()))
    assert res["error_code"] in allowed, (
        "%s: got %r, expected one of %s" % (label, res["error_code"], sorted(allowed)))
    assert res["temp_cleaned"] is True, "%s: temp dir must be cleaned" % label
    if spawned_expected is not None:
        assert SPAWNED.exists() is spawned_expected, (
            "%s: stand-in entry did%s run" % (label, "" if spawned_expected else " not"))
    assert not SURVIVOR.exists(), "%s: grandchild must not survive" % label
    print("   PASS %s" % label)


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("R03 only applies to Windows Job Objects")
    if not TASK.exists():
        raise SystemExit("task file missing: %s" % TASK)

    print("R03 probe: broken Job Object query / open / assign")
    prepare()
    try:
        print("\n-- A: QueryInformationJobObject fails (KILL_ON_JOB_CLOSE never set)")
        check("A", run_case("query_fails"), {"TIMEOUT", "INTEGRITY_FAILED"}, True)

        print("\n-- B: OpenProcess fails (child cannot be opened for binding)")
        check("B", run_case("open_fails"), {"INTEGRITY_FAILED"})

        print("\n-- C: AssignProcessToJobObject returns 0 (binding failure)")
        check("C", run_case("assign_fails"), {"INTEGRITY_FAILED"})

        print("\n-- D: control, no shim (stand-in must run, time out and leave no survivor)")
        res = run_case(None)
        check("D", res, {"TIMEOUT"}, True)
        assert res["wall_s"] >= CHILD_TIMEOUT - 0.3, (
            "D: wall=%.2fs is shorter than the %.1fs timeout" % (res["wall_s"], CHILD_TIMEOUT))
    finally:
        shutil.rmtree(PROBE, ignore_errors=True)

    print("\nR03 PROBE PASSED")
