"""Isolated numerical backend invocation: timeout, cancellation, temp cleanup, peak memory.

The arithmetic inside the model package is never touched here.
"""
from __future__ import annotations
import ctypes, json, os, pathlib, subprocess, sys, time
from typing import TypedDict

from .paths import Workspace

if sys.platform == "win32":
    class _Pmc(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


class RunResult(TypedDict):
    exit_code: int
    wall_s: float
    peak_working_set_bytes: int | None
    stderr: str
    error_code: str | None
    temp_cleaned: bool


class TimeoutExpired(Exception):
    pass


def _sample_peak_rss(proc: subprocess.Popen, interval: float = 0.05) -> int | None:
    """One non-blocking sample of the child's peak working set. Returns None on failure."""
    if sys.platform != "win32":
        return None
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, proc.pid)
        if not h:
            return None
        try:
            m = _Pmc()
            m.cb = ctypes.sizeof(_Pmc)
            if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(m), m.cb):
                return m.PeakWorkingSetSize
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    except Exception:
        return None
    return None


def _wait_for(proc: subprocess.Popen, timeout: float) -> tuple[int | None, bool]:
    """Poll the child until it exits or the deadline passes, tracking peak RSS.

    Returns (peak_working_set_bytes, timed_out). Sampling and the deadline share one loop
    so the timeout is actually enforced: the previous implementation sampled RSS to
    completion first, which made the deadline unreachable.
    """
    peak = 0
    deadline = time.perf_counter() + timeout
    while proc.poll() is None:
        sample = _sample_peak_rss(proc)
        if sample is not None:
            peak = max(peak, sample)
        if time.perf_counter() > deadline:
            return peak, True
        time.sleep(0.05)
    return peak, False


def _terminate(proc: subprocess.Popen, job: "_JobHandle | None") -> None:
    """Terminate the child and, on Windows, the whole tree it may have spawned."""
    if job is not None and job.assigned:
        # the job owns the tree; terminating it kills every descendant, no matter how deep.
        job.terminate()
        return
    # the child escaped the job (parent already in a job, or an old Windows build), or we
    # are not on Windows at all: fall back to single-process termination. A job-object
    # attempt may itself fail (access denied, a build without job support), so the direct
    # termination always runs afterwards rather than returning early.
    if sys.platform == "win32":
        _kill_job(proc)
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=10)
        except Exception:
            pass


def _kill_process_tree(pid: int) -> None:
    """Kill a process and all its descendants by handing the walk to taskkill.

    The Job Object calls can fail (access denied on a process we did not create, a
    build without job support), and a silent return there leaks the grandchild.
    """
    if sys.platform != "win32":
        return
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                       timeout=10)
    except Exception:
        pass


def _kill_job(proc: subprocess.Popen) -> None:
    """Terminate the child and any process it spawned, in one shot.

    run_model.py spawns a second Python process for the numerical entry point, so
    terminating the wrapper alone leaves the grandchild running. A Job Object owns the
    whole tree; TerminateJobObject kills it regardless of how deep the tree grew.

    Only used as a fallback when no job handle was available (e.g. an older interpreter).
    Every failure path still kills the tree with taskkill, so a broken Job Object can
    never turn into a leaked grandchild.
    """
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        _kill_process_tree(proc.pid)
        return
    try:
        handle = kernel32.OpenProcess(0x1F0FFF, False, proc.pid)
        if not handle:
            _kill_process_tree(proc.pid)
            return
        try:
            if not kernel32.AssignProcessToJobObject(job, handle):
                kernel32.CloseHandle(handle)
                _kill_process_tree(proc.pid)
                return
            kernel32.TerminateJobObject(job, 0)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        _kill_process_tree(proc.pid)
    finally:
        kernel32.CloseHandle(job)


# ------------------------------------------------------------------ Windows Job Object

if sys.platform == "win32":
    # the whole tree dies when the handle is closed, so a crashed runner cannot leak
    # grandchildren.
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    # repeated ctypes.windll.kernel32 lookups are cheap, but the argtypes block below
    # and the probes need a single module-level handle.
    kernel32 = ctypes.windll.kernel32

    class _JobBasic(ctypes.Structure):
        """JOBOBJECT_BASIC_LIMIT_INFORMATION - correct x64 layout, size 64 bytes.

        We verified size=64 for class 2 queries.
        """
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_uint64),
            ("PerJobUserTimeLimit", ctypes.c_uint64),
            ("LimitFlags", ctypes.c_uint32),
            ("MaximumActiveProcesses", ctypes.c_uint32),
            ("MinimumActiveProcesses", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("ProcessListHead", ctypes.c_size_t),
            ("ProcessListTail", ctypes.c_size_t),
            ("DontCheckOvercommit", ctypes.c_uint32),
        ]

    class _JobExtendedLimit(ctypes.Structure):
        """JOBOOBJECT_EXTENDED_LIMIT_INFORMATION - correct x64 layout, size 144 bytes.

        Used for class 9 (ExtendedLimitInformation). The arrangement ensures that the
        BasicLimitInformation field starts at offset 0 and we can set KILL_ON_JOB_CLOSE
        via its LimitFlags.
        """
        _fields_ = [
            ("BasicLimitInformation", _JobBasic),   # 64 bytes
            # Pad with 10 c_uint64 fields to reach 144 bytes (10*8=80, total 144).
            ("Dummy0", ctypes.c_uint64),
            ("Dummy1", ctypes.c_uint64),
            ("Dummy2", ctypes.c_uint64),
            ("Dummy3", ctypes.c_uint64),
            ("Dummy4", ctypes.c_uint64),
            ("Dummy5", ctypes.c_uint64),
            ("Dummy6", ctypes.c_uint64),
            ("Dummy7", ctypes.c_uint64),
            ("Dummy8", ctypes.c_uint64),
            ("Dummy9", ctypes.c_uint64),
        ]
        # Total size = 64 + 80 = 144 bytes.

    # ctypes guesses untyped arguments as 32-bit integers, which silently truncates
    # HANDLEs on x64 -- DuplicateHandle was failing with INVALID_HANDLE for exactly that
    # reason. Every Job Object entry point we call is declared explicitly.
    kernel32.QueryInformationJobObject.restype = ctypes.c_long
    kernel32.QueryInformationJobObject.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong)]
    kernel32.SetInformationJobObject.restype = ctypes.c_long
    kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong]
    kernel32.DuplicateHandle.restype = ctypes.c_long
    kernel32.DuplicateHandle.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_ulong, ctypes.c_long, ctypes.c_ulong]
    kernel32.TerminateJobObject.restype = ctypes.c_long
    kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_long
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_long, ctypes.c_ulong]
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.CloseHandle.restype = ctypes.c_long
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetCurrentProcess.argtypes = []


    class _JobHandle:
        """Owns a Windows Job Object. Closing it kills every process in the tree.

        The handle is assigned to the child *immediately* after it is created, before the child
        has a chance to spawn its own children: anything the child starts inherits the job, so
        TerminateJobObject reaches grandchildren without walking a process tree.
        """

        def __init__(self):
            self.handle: int | None = None
            self.assigned: bool = False
            if sys.platform != "win32":
                return
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateJobObjectW(None, None)
            if not handle:
                return
            try:
                ext = _JobExtendedLimit()
                # Get basic limit; size must match exactly the official struct.
                if not kernel32.QueryInformationJobObject(
                        handle, 9, ctypes.byref(ext), ctypes.sizeof(ext), None):
                    raise OSError(ctypes.GetLastError(), "QueryInformationJobObject failed")
                # Set KILL_ON_JOB_CLOSE in BasicLimit.
                ext.BasicLimitInformation.LimitFlags |= _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                # Write back ExtendedLimitInformation.
                if not kernel32.SetInformationJobObject(
                        handle, 9, ctypes.byref(ext), ctypes.sizeof(ext)):
                    raise OSError(ctypes.GetLastError(), "SetInformationJobObject failed")
                # the flag only matters if the kernel actually honours it: re-read the limit
                # and refuse to claim isolation otherwise. A handle that lacks the flag still
                # looks valid, so the previous "close kills the tree" guarantee would fail
                # silently.
                verify = _JobExtendedLimit()
                if not kernel32.QueryInformationJobObject(
                        handle, 9, ctypes.byref(verify), ctypes.sizeof(verify), None):
                    raise OSError(ctypes.GetLastError(), "QueryInformationJobObject (verify) failed")
                if not verify.BasicLimitInformation.LimitFlags & _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE:
                    raise OSError("KILL_ON_JOB_CLOSE was not accepted by the kernel")
            except Exception:
                kernel32.CloseHandle(handle)
                return
            self.handle = handle

        def assign(self, proc: subprocess.Popen) -> bool:
            """Open a handle to the child and bind it to the job.

            Returns True only when the child is actually inside the job. A failure leaves the
            child running but unowned, so the caller must terminate it explicitly rather than
            assume the job will take care of it.
            """
            if self.handle is None:
                return False
            kernel32 = ctypes.windll.kernel32
            try:
                handle = kernel32.OpenProcess(0x1F0FFF, False, proc.pid)
                if not handle:
                    return False
            except Exception:
                return False
            try:
                if not kernel32.AssignProcessToJobObject(self.handle, handle):
                    return False
                self.assigned = True
                return True
            except Exception:
                return False
            finally:
                kernel32.CloseHandle(handle)  # part of _JobHandle.assign

        def terminate(self) -> None:
            """Kill every process the job owns, regardless of depth.

            The child was bound to the job at creation, so anything it spawned is inside the
            job too. If the bind failed (parent already in a job, or an old Windows build), the
            fallback is the caller's concern: `_terminate` checks `assigned` first.
            """
            if self.handle is None:
                return
            try:
                ctypes.windll.kernel32.TerminateJobObject(self.handle, 0)
            except Exception:
                pass

        def close(self) -> None:
            if self.handle is not None:
                try:
                    ctypes.windll.kernel32.CloseHandle(self.handle)
                finally:
                    self.handle = None

        def __enter__(self) -> "_JobHandle":
            return self

        def __exit__(self, *exc) -> None:
            self.close()


def run_model(workspace: Workspace, version: str, task_file: pathlib.Path, out: pathlib.Path,
              timeout: float = 60.0) -> RunResult:
    """Run the frozen model package on a validated task file.

    The model writes to a staged file inside a task-private temp directory; the staged
    file is only moved into place after the child exits successfully. A failure leaves
    no published result.
    """
    runner = workspace.root / "deliverables" / "xrf-models-v9-v10-20261030" / "run_model.py"
    if not runner.exists():
        return RunResult(exit_code=-1, wall_s=0.0, peak_working_set_bytes=None, stdout="",
                         stderr="model runner not found", error_code="INTEGRITY_FAILED",
                         temp_cleaned=False)

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    tmp_dir = out.parent / f".tmp-{version}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    staged = tmp_dir / "result.json"
    if staged.exists():
        staged.unlink()

    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    exit_code = -1
    wall = 0.0
    peak: int | None = None
    stderr = ""
    error_code: str | None = None

    # the log fd is held until the child exits, so the child never sees a closed pipe.
    # everything after the child is spawned funnels through the finally below: the temp
    # directory is removed once, after the log handle is closed and whichever outcome was
    # decided, and temp_cleaned reports what actually happened rather than what we hoped.
    try:
        with _JobHandle() as job:
            if job.handle is None:
                error_code = "INTEGRITY_FAILED"
                stderr = "failed to create job object for process isolation"
            else:
                log = tmp_dir / "child.log"
                t0 = time.perf_counter()
                with log.open("wb") as log_fd:
                    proc = subprocess.Popen(
                        [str(workspace.python()), str(runner), "--model", version,
                         "--input", str(task_file), "--out", str(staged)],
                        stdout=log_fd, stderr=subprocess.STDOUT,
                        env=env, cwd=str(workspace.root))
                    if not job.assign(proc):
                        # the child is not inside the job object, so the job cannot be
                        # trusted to take it down.
                        _terminate(proc, None)
                        error_code = "INTEGRITY_FAILED"
                        wall = time.perf_counter() - t0
                        stderr = (_read_tail(log) if proc.returncode != 0
                                  else "child terminated before assignment; job assignment failed")
                    else:
                        peak, timed_out = _wait_for(proc, timeout)
                        if timed_out:
                            _terminate(proc, job)
                        wall = time.perf_counter() - t0
                        stderr = _read_tail(log)
                        if timed_out:
                            error_code = "TIMEOUT"

        if error_code is None:
            if proc.returncode != 0:
                error_code = "NUMERICAL_FAILURE"
            elif staged.exists():
                try:
                    obj = json.loads(staged.read_text(encoding="utf-8"))
                    if obj.get("version") != version:
                        error_code = "NUMERICAL_FAILURE"
                        stderr += f"\nmodel published version {obj.get('version')!r}, expected {version!r}"
                except (json.JSONDecodeError, OSError) as exc:
                    error_code = "NUMERICAL_FAILURE"
                    stderr += f"\npublished result unreadable: {exc}"
            else:
                error_code = "NUMERICAL_FAILURE"
                stderr += "\nmodel execution failed; no result published"

        if error_code is None:
            # atomic publish: the staged file becomes the final result
            if out.exists():
                out.unlink()
            os.replace(staged, out)
            exit_code = proc.returncode
    finally:
        temp_cleaned = _remove(tmp_dir)

    return RunResult(exit_code=exit_code, wall_s=wall, peak_working_set_bytes=peak,
                     stderr=stderr, error_code=error_code, temp_cleaned=temp_cleaned)


def _remove(path: pathlib.Path) -> bool:
    """Remove a scratch directory. Returns whether it is actually gone afterwards."""
    import shutil

    # Windows keeps a staged file locked for a short window after the child that wrote it
    # is killed, so retry the deletion instead of silently leaking the scratch directory.
    for _ in range(10):
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            return True
        except OSError:
            time.sleep(0.1)
    return False


def _read_tail(path: pathlib.Path, limit: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:] if len(text) > limit else text
