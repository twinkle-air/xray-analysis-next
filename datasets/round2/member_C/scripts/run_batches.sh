#!/usr/bin/env bash
# Round-2 member C: generate three sealed condition batches (P1/P2/P3).
# Same 250 samples; 2 replicates per condition (fixed profiles, no jitter).
set -u
export PYTHONUTF8=1
PY="C:/Users/TianT/AppData/Local/Python/bin/python.exe"
GEN="C:/Users/TianT/Documents/Qoder/2026-10-21/ddc06964/C_r2/sealed_gen/fp_competition"
BASE="C:/Users/TianT/Documents/Qoder/2026-10-21/ddc06964/C_r2"
SAMPLES="$BASE/build/C_r2_samples.json"
TARGETS="Na Mg Al Si P S Cl K Ca Ti V Cr Mn Fe Co Ni Cu Zn As Se Rb Sr Y Zr Nb Mo Cd Sn Sb Ba W Pb"
SPLIT_SEED=20261103

run_one () {
  local tag=$1 seed=$2
  local start end
  start=$(date +%s)
  "$PY" -X utf8 -B "$GEN/app.py" batch \
    --samples "$SAMPLES" \
    --profile "$GEN/profiles/${tag}.json" \
    --replicates 2 \
    --seed "$seed" \
    --split-seed "$SPLIT_SEED" \
    --closure strict \
    --legacy-al reject \
    --targets $TARGETS \
    --out "$BASE/batches/C_r2_${tag}" \
    > "$BASE/batches/C_r2_${tag}.log" 2>&1
  local rc=$?
  end=$(date +%s)
  echo "{\"tag\": \"$tag\", \"seed\": $seed, \"exit\": $rc, \"seconds\": $((end-start))}" >> "$BASE/batches/timings.jsonl"
  echo "$tag exit=$rc seconds=$((end-start))"
}

mkdir -p "$BASE/batches"
run_one P1 2026110301
run_one P2 2026110302
run_one P3 2026110303
