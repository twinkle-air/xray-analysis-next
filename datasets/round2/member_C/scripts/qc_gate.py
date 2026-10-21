# -*- coding: utf-8 -*-
"""Pre-pack gate for member C audit/replay reports.

The pack subcommand only checks package structure; it does not repeat the
physics replay.  This gate refuses to pack unless the actual audit and replay
reports are passed, cover every expected spectrum, report no errors, keep the
frozen tolerances and preserve the same-environment statement.
"""
import argparse
import json
import math
import sys
from pathlib import Path


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report as a gate failure
        return {"_load_error": f"{type(exc).__name__}: {exc}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--replay", required=True)
    ap.add_argument("--expected", type=int, required=True)
    ap.add_argument("--rtol", type=float, default=1e-12)
    ap.add_argument("--atol", type=float, default=1e-8)
    args = ap.parse_args()

    audit = load(args.audit)
    replay = load(args.replay)
    errs = []

    if "_load_error" in audit:
        errs.append(f"audit report unreadable: {audit['_load_error']}")
    if "_load_error" in replay:
        errs.append(f"replay report unreadable: {replay['_load_error']}")

    if audit.get("status") != "passed":
        errs.append(f"audit status={audit.get('status')!r}")
    if audit.get("errors") != []:
        errs.append(f"audit errors={audit.get('errors')!r}")
    if audit.get("spectra_checked") != args.expected:
        errs.append(f"audit spectra_checked={audit.get('spectra_checked')!r}, "
                    f"expected {args.expected}")
    if audit.get("complete_physics_recalculation") is not False:
        errs.append("audit must declare complete_physics_recalculation=false")

    if replay.get("status") != "passed":
        errs.append(f"replay status={replay.get('status')!r}")
    if replay.get("errors") != []:
        errs.append(f"replay errors={replay.get('errors')!r}")
    if replay.get("scope") != "all_records":
        errs.append(f"replay scope={replay.get('scope')!r}, expected all_records")
    if replay.get("spectra_recalculated") != args.expected:
        errs.append(f"replay spectra_recalculated="
                    f"{replay.get('spectra_recalculated')!r}, expected {args.expected}")
    if replay.get("complete_physics_recalculation") is not True:
        errs.append("replay must declare complete_physics_recalculation=true")
    for key, want in (("rtol", args.rtol), ("atol_counts", args.atol)):
        got = replay.get(key)
        if not isinstance(got, (int, float)) or got != want:
            errs.append(f"replay {key}={got!r}, expected {want!r}")
    diff = replay.get("maximum_absolute_array_difference")
    if not isinstance(diff, (int, float)) or not math.isfinite(diff) or diff < 0:
        errs.append(f"replay maximum_absolute_array_difference={diff!r}")
    if replay.get("same_environment") is not True:
        note = (replay.get("environment_differences")
                or replay.get("environment_differences_note"))
        if not note:
            errs.append("replay same_environment is not true and no difference "
                        "note is recorded")

    result = {
        "tag": args.tag,
        "status": "passed" if not errs else "failed",
        "expected_spectra": args.expected,
        "audit_status": audit.get("status"),
        "audit_spectra_checked": audit.get("spectra_checked"),
        "replay_status": replay.get("status"),
        "replay_scope": replay.get("scope"),
        "replay_spectra": replay.get("spectra_recalculated"),
        "replay_same_environment": replay.get("same_environment"),
        "maximum_absolute_array_difference": diff,
        "errors": errs,
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
