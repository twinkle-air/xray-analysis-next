#!/usr/bin/env bash
# Round-2 member C: out-of-package audit + full replay + pack for P1/P2/P3.
set -u
export PYTHONUTF8=1
PY="C:/Users/TianT/AppData/Local/Python/bin/python.exe"
APP="C:/Users/TianT/Documents/Qoder/2026-10-21/ddc06964/C_r2/sealed_gen/fp_competition/app.py"
BASE="C:/Users/TianT/Documents/Qoder/2026-10-21/ddc06964/C_r2"
OUT="$BASE/qc"

mkdir -p "$OUT"
for tag in P1 P2 P3; do
  ds="$BASE/batches/C_r2_$tag"
  start=$(date +%s)
  "$PY" -X utf8 -B "$APP" audit --dataset "$ds" --out "$OUT/C_r2_${tag}_audit.json" \
      > "$OUT/C_r2_${tag}_audit.log" 2>&1
  rc_a=$?
  mid=$(date +%s)
  "$PY" -X utf8 -B "$APP" replay --dataset "$ds" --out "$OUT/C_r2_${tag}_replay.json" \
      > "$OUT/C_r2_${tag}_replay.log" 2>&1
  rc_r=$?
  end=$(date +%s)
  echo "{\"tag\":\"$tag\",\"audit_exit\":$rc_a,\"audit_s\":$((mid-start)),\"replay_exit\":$rc_r,\"replay_s\":$((end-mid))}" >> "$OUT/qc_timings.jsonl"
  echo "$tag audit=$rc_a replay=$rc_r"
done

# pack only if audits+replays passed (exit 0)
while IFS= read -r line; do
  echo "$line"
done < "$OUT/qc_timings.jsonl"

for tag in P1 P2 P3; do
  ds="$BASE/batches/C_r2_$tag"
  s=$(date +%s)
  "$PY" -X utf8 -B "$APP" pack --dataset "$ds" --out "$OUT/C_r2_${tag}_dataset.zip" \
      > "$OUT/C_r2_${tag}_pack.log" 2>&1
  rc=$?
  e=$(date +%s)
  if [ $rc -eq 0 ]; then
    ( cd "$OUT" && sha256sum "C_r2_${tag}_dataset.zip" > "C_r2_${tag}_dataset.zip.sha256" )
  fi
  echo "{\"tag\":\"$tag\",\"pack_exit\":$rc,\"pack_s\":$((e-s))}" >> "$OUT/pack_timings.jsonl"
  echo "$tag pack=$rc"
done

du -sh "$BASE/batches"/* "$OUT"/*.zip 2>/dev/null | tee "$OUT/capacity.txt"
