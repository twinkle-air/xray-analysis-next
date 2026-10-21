# -*- coding: utf-8 -*-
"""Mock generator used only by qc_gate_regression.sh.

It exercises the shell control flow of run_qc.sh: audit/replay can fail by
exit code and/or by report contents, while pack records that it was called.
"""
import json
import os
import sys
from pathlib import Path

cmd = sys.argv[1]
out = Path(sys.argv[sys.argv.index("--out") + 1])
mode = os.environ.get("MOCK_MODE", "pass")

audit_fail = mode in ("fail_audit", "all_fail")
replay_fail = mode in ("fail_replay", "all_fail")
report_fail = mode == "bad_status"
short = mode == "short_coverage"

if cmd == "audit":
    status = "failed" if (audit_fail or report_fail) else "passed"
    data = {
        "status": status,
        "check_type": "mock",
        "spectra_checked": 499 if short else 500,
        "errors": [] if status == "passed" else ["mock audit failure"],
        "complete_physics_recalculation": False,
        "physical_calibration_verified": False,
        "concentration_accuracy_verified": False,
    }
    out.write_text(json.dumps(data), encoding="utf-8")
    sys.exit(1 if audit_fail else 0)

if cmd == "replay":
    status = "failed" if (replay_fail or report_fail) else "passed"
    data = {
        "status": status,
        "scope": "all_records",
        "spectra_recalculated": 499 if short else 500,
        "complete_physics_recalculation": True,
        "same_environment": True,
        "maximum_absolute_array_difference": 0.0,
        "errors": [] if status == "passed" else ["mock replay failure"],
        "rtol": 1e-12,
        "atol_counts": 1e-8,
        "file_byte_identity_tested": False,
        "physical_calibration_verified": False,
        "concentration_accuracy_verified": False,
    }
    out.write_text(json.dumps(data), encoding="utf-8")
    sys.exit(1 if replay_fail else 0)

if cmd == "pack":
    marker = os.environ.get("MOCK_PACK_MARKER")
    if marker:
        Path(marker).write_text("pack called\n", encoding="utf-8")
    out.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    sys.exit(0)

sys.exit(2)
