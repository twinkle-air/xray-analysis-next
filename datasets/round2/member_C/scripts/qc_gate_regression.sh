#!/usr/bin/env bash
# Regression check for the QC gate: a failed/malformed audit or replay must
# skip pack and make run_qc.sh exit non-zero; a valid pair may pack.
set -u
export PYTHONUTF8=1
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-C:/Users/TianT/AppData/Local/Python/bin/python.exe}"
TEST="${TEST:-$(dirname "$HERE")/qc_gate_test}"
rm -rf "$TEST"
mkdir -p "$TEST/batches/C_r2_P1"
cp "$HERE/mock_app_for_gate_test.py" "$TEST/mock_app.py"

run_case () {
  local mode="$1" expect_pack="$2"
  local out="$TEST/out_$mode" marker="$TEST/pack_$mode.called"
  rm -rf "$out" "$marker"
  MOCK_MODE="$mode" MOCK_PACK_MARKER="$marker" \
  TAGS=P1 BASE="$TEST" OUT="$out" APP="$TEST/mock_app.py" \
  GATE="$HERE/qc_gate.py" EXPECTED=500 \
  bash "$HERE/run_qc.sh" > "$TEST/run_$mode.log" 2>&1
  local rc=$?
  if [ "$expect_pack" = yes ]; then
    if [ "$rc" -eq 0 ] && [ -f "$marker" ]; then
      echo "PASS $mode: rc=0, pack called"
      return 0
    fi
    echo "FAIL $mode: rc=$rc, marker=$([ -f "$marker" ] && echo yes || echo no)"
    return 1
  fi
  if [ "$rc" -ne 0 ] && [ ! -f "$marker" ]; then
    echo "PASS $mode: rc=$rc, pack skipped"
    return 0
  fi
  echo "FAIL $mode: rc=$rc, marker=$([ -f "$marker" ] && echo yes || echo no)"
  return 1
}

fail=0
run_case fail_audit no || fail=1
run_case fail_replay no || fail=1
run_case bad_status no || fail=1
run_case short_coverage no || fail=1
run_case pass yes || fail=1

if [ "$fail" -eq 0 ]; then
  echo "QC GATE REGRESSION: PASS"
  exit 0
fi
echo "QC GATE REGRESSION: FAIL"
exit 1
