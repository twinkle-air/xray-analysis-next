"""Compatibility entry: forward to the maintained suite one directory up.

This path is the one the version README documents (its §9 quick-start), so it must keep
working. The suite copy that used to live here ran against this workspace and wiped its
jobs/ directory on every start, destroying real task data, and it reimplemented the suite,
so the two copies drifted apart. The maintained suites run against a throwaway workspace
instead; this entry only keeps the documented command working: arguments are forwarded
verbatim and the exit code is passed through unchanged, so a failure is never reported as
success.
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE.parent / "verify_p1.py"


def main() -> int:
    if not TARGET.is_file():
        print(f"the maintained suite is missing: {TARGET}", file=sys.stderr)
        return 2
    result = subprocess.run([sys.executable, str(TARGET), *sys.argv[1:]])
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
