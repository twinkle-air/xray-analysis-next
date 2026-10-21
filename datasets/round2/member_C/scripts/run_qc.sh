#!/usr/bin/env bash
# Round-2 member C: out-of-package audit + full replay + gated pack.
# A batch is packed only when BOTH audit and replay exit 0 and the reports pass
# the frozen gate (status/errors/full coverage/tolerances/same environment).
# Any failure skips that batch's pack and makes the whole script exit non-zero.
set -u
export PYTHONUTF8=1
PY="${PY:-C:/Users/TianT/AppData/Local/Python/bin/python.exe}"
APP="${APP:-C:/Users/TianT/Documents/Qoder/2026-10-21/ddc06964/C_r2/sealed_gen/fp_competition/app.py}"
BASE="${BASE:-C:/Users/TianT/Documents/Qoder/2026-10-21/ddc06964/C_r2/v2}"
OUT="${OUT:-$BASE/qc}"
GATE="${GATE:-$(dirname "$0")/qc_gate.py}"
TAGS="${TAGS:-P1 P2 P3}"
EXPECTED="${EXPECTED:-500}"

mkdir -p "$OUT" "$BASE/batches"
overall=0
for tag in $TAGS; do
  ds="$BASE/batches/C_r2_$tag"
  audit="$OUT/C_r2_${tag}_audit.json"
  replay="$OUT/C_r2_${tag}_replay.json"
  start=$(date +%s)
  "$PY" -X utf8 -B "$APP" audit --dataset "$ds" --out "$audit" \
      > "$OUT/C_r2_${tag}_audit.log" 2>&1
  rc_a=$?
  mid=$(date +%s)
  "$PY" -X utf8 -B "$APP" replay --dataset "$ds" --out "$replay" \
      > "$OUT/C_r2_${tag}_replay.log" 2>&1
  rc_r=$?
  end=$(date +%s)
  echo "{\"tag\":\"$tag\",\"audit_exit\":$rc_a,\"audit_s\":$((mid-start)),\"replay_exit\":$rc_r,\"replay_s\":$((end-mid))}" >> "$OUT/qc_timings.jsonl"
  echo "$tag audit=$rc_a replay=$rc_r"

  if [ "$rc_a" -ne 0 ] || [ "$rc_r" -ne 0 ]; then
    echo "$tag GATE FAILED: audit/replay exit $rc_a/$rc_r; pack skipped" >&2
    overall=1
    continue
  fi
  "$PY" -X utf8 -B "$GATE" --tag "$tag" --audit "$audit" --replay "$replay" \
      --expected "$EXPECTED" > "$OUT/C_r2_${tag}_gate.json" 2>&1
  rc_g=$?
  if [ "$rc_g" -ne 0 ]; then
    echo "$tag GATE FAILED: report check exit $rc_g; pack skipped" >&2
    cat "$OUT/C_r2_${tag}_gate.json" >&2
    overall=1
    continue
  fi

  s=$(date +%s)
  "$PY" -X utf8 -B "$APP" pack --dataset "$ds" --out "$OUT/C_r2_${tag}_dataset.zip" \
      > "$OUT/C_r2_${tag}_pack.log" 2>&1
  rc=$?
  e=$(date +%s)
  if [ "$rc" -eq 0 ]; then
    ( cd "$OUT" && sha256sum "C_r2_${tag}_dataset.zip" > "C_r2_${tag}_dataset.zip.sha256" )
  else
    overall=1
  fi
  echo "{\"tag\":\"$tag\",\"pack_exit\":$rc,\"pack_s\":$((e-s))}" >> "$OUT/pack_timings.jsonl"
  echo "$tag pack=$rc"
done

du -sh "$BASE/batches"/* "$OUT"/*.zip 2>/dev/null | tee "$OUT/capacity.txt"
exit "$overall"
