"""Assemble the audited D delivery tree under datasets/round2/member_D."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
PKG = WORK.parent / "fp-spectrum-generator-competition-v0.2.1"
DELIVERY = WORK / "delivery" / "datasets" / "round2" / "member_D"
CONFIG = WORK / "D_run_config.json"
SUMMARY = WORK / "production" / "run_summary_D.json"
TESTS = WORK / "reports" / "generator_tests_D.log"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
                    encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def parse_tests() -> dict:
    if not TESTS.is_file():
        return {"status": "pending", "reason": "test log missing"}
    text = TESTS.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"Ran (\d+) tests? in ([\d.]+)s", text)
    if "FAILED" in text:
        status = "failed"
    elif re.search(r"\nOK\b", text):
        status = "passed"
    else:
        status = "pending"
    return {"status": status,
            "tests_run": int(match.group(1)) if match else None,
            "seconds": float(match.group(2)) if match else None,
            "log": "reports/generator_tests_D.log",
            "utf8_mode_note": ("Run with PYTHONUTF8=1. The default cp936 locale mis-decodes the "
                               "UTF-8 temp path containing the non-ASCII user name; without UTF-8 "
                               "mode one robustness test reports a false JSON escape error.")}


def compile_check(paths: list[Path]) -> dict:
    result = {}
    for path in paths:
        completed = subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                                   capture_output=True, text=True)
        try:
            label = str(path.relative_to(WORK))
        except ValueError:
            label = str(path.relative_to(WORK.parent))
        result[label] = {
            "status": "passed" if completed.returncode == 0 else "failed",
            "stderr": completed.stderr.strip() or None,
        }
    return result


def main() -> int:
    if DELIVERY.exists():
        print(f"Refusing to overwrite existing delivery: {DELIVERY}", file=sys.stderr)
        return 2
    if not SUMMARY.is_file():
        print("Run summary is missing; finish the batch run first", file=sys.stderr)
        return 2

    config = read_json(CONFIG)
    summary = read_json(SUMMARY)
    batch_config = config["batches"]
    errors: list[str] = []
    rows: list[dict] = []

    summary_batches = summary.get("batches", {})
    if summary.get("finished_at_utc") is None:
        errors.append("Run summary is not finished")
    if set(summary_batches) != set(batch_config):
        errors.append("Run summary does not cover exactly the configured batches")
    else:
        for batch_id, row in summary_batches.items():
            for phase in ("generate", "audit", "replay", "pack"):
                if row.get(phase, {}).get("status") not in ("passed", "existing_passed",
                                                            "existing_complete"):
                    errors.append(f"{batch_id}: summary phase {phase} is not passed")

    for batch_id, batch in batch_config.items():
        dataset = WORK / "production" / "batches" / batch_id
        audit_path = WORK / "production" / "qc" / f"{batch_id}.audit.json"
        replay_path = WORK / "production" / "qc" / f"{batch_id}.replay.json"
        zip_path = WORK / "production" / "zips" / f"{batch_id}.zip"
        sidecar = zip_path.with_suffix(zip_path.suffix + ".sha256")
        manifest_path = dataset / "manifest.json"
        for path, label in ((manifest_path, "manifest"), (audit_path, "audit"),
                            (replay_path, "replay"), (zip_path, "zip"), (sidecar, "sidecar")):
            if not path.is_file():
                errors.append(f"{batch_id}: missing {label}")
        if errors and errors[-1].startswith(batch_id):
            continue
        manifest = read_json(manifest_path)
        audit = read_json(audit_path)
        replay = read_json(replay_path)
        digest = sidecar.read_text(encoding="ascii").split()[0]
        if manifest.get("status") != "complete" or manifest.get("spectrum_count") != batch["spectra"]:
            errors.append(f"{batch_id}: sealed manifest is not complete/50")
        if audit.get("status") != "passed" or audit.get("errors"):
            errors.append(f"{batch_id}: audit is not a clean pass")
        if (replay.get("status") not in ("passed", "passed_with_environment_differences")
                or replay.get("scope") != "all_records"
                or replay.get("spectra_recalculated") != batch["spectra"]
                or replay.get("errors")):
            errors.append(f"{batch_id}: replay is not a clean full replay")
        if digest != sha256(zip_path):
            errors.append(f"{batch_id}: ZIP hash does not match sidecar")
        if len(list((dataset / "blind_inputs").glob("*.json"))) != batch["spectra"]:
            errors.append(f"{batch_id}: blind input count mismatch")
        if len(list((dataset / "full_results").glob("*.json"))) != batch["spectra"]:
            errors.append(f"{batch_id}: full result count mismatch")
        rows.append({
            "batch_id": batch_id,
            "profile": batch["profile_id"],
            "family": batch["family"],
            "shard": Path(batch["samples"]).stem,
            "seed": batch["seed"],
            "recipes": batch["recipes"],
            "replicates": batch["replicates"],
            "spectra": batch["spectra"],
            "sealed_dataset": f"spectra/{batch['profile_id']}/{batch_id}.zip",
            "zip_sha256": digest,
            "zip_bytes": zip_path.stat().st_size,
            "audit": f"qc/{batch_id}.audit.json",
            "audit_status": audit["status"],
            "audit_spectra": audit["spectra_checked"],
            "replay": f"qc/{batch_id}.replay.json",
            "replay_status": replay["status"],
            "replay_scope": replay["scope"],
            "replay_spectra": replay["spectra_recalculated"],
            "replay_max_abs_array_difference": replay.get("maximum_absolute_array_difference"),
            "batch_manifest_sha256": sha256(manifest_path),
        })

    if errors:
        print("Delivery preconditions failed:", file=sys.stderr)
        for error in errors:
            print(" -", error, file=sys.stderr)
        return 2
    if len(rows) != 30 or sum(row["spectra"] for row in rows) != 1500:
        print("Batch coverage is not 30 batches / 1500 spectra", file=sys.stderr)
        return 2

    DELIVERY.mkdir(parents=True)
    copy_tree(WORK / "design", DELIVERY / "design")
    copy_tree(WORK / "frozen_inputs", DELIVERY / "frozen_inputs")
    copy_tree(WORK / "reports", DELIVERY / "reports")
    copy_tree(WORK / "scripts", DELIVERY / "scripts")
    copy_tree(WORK / "production" / "qc", DELIVERY / "qc")
    shutil.copy2(WORK / "D_run_config.json", DELIVERY / "D_run_config.json")
    shutil.copy2(WORK / "D_seed_manifest.json", DELIVERY / "D_seed_manifest.json")
    scope = read_json(WORK / "design" / "D_design_scope.json")
    scope["design_time_no_spectra_generated"] = scope.pop("no_spectra_generated", True)
    scope["no_spectra_generated"] = False
    scope["spectra_generated"] = 1500
    scope["batches_generated"] = 30
    scope["spectra_generation_finished_at_utc"] = summary.get("finished_at_utc")
    write_json(DELIVERY / "D_design_scope.json", scope)
    write_json(DELIVERY / "design" / "D_design_scope.json", scope)

    for row in rows:
        source = WORK / "production" / "zips" / f"{row['batch_id']}.zip"
        target = DELIVERY / "spectra" / row["profile"] / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        shutil.copy2(source.with_suffix(source.suffix + ".sha256"),
                     target.with_suffix(target.suffix + ".sha256"))

    environment = read_json(WORK / "reports" / "environment_D.json")
    freeze = read_json(WORK / "reports" / "freeze_verification_D.json")
    tests = parse_tests()
    script_paths = sorted((WORK / "scripts").glob("*.py"))
    package_paths = [PKG / "fp_competition" / name for name in
                     ("core.py", "dataset.py", "app.py", "minerals.py", "version.py")]
    code_verification = {
        "schema": "D-code-verification/v1",
        "generated_at_utc": now(),
        "software_version": config["software_version"],
        "physical_model_version": config["physics_version"],
        "python": environment.get("python"),
        "compile": compile_check(script_paths + package_paths),
        "unit_tests": tests,
        "source_sha256": {str(path.relative_to(WORK.parent)): sha256(path)
                          for path in script_paths + package_paths},
        "freeze_verification": {
            "report": "reports/freeze_verification_D.json",
            "total": freeze.get("total"),
            "matched": freeze.get("matched"),
            "mismatch": freeze.get("mismatch"),
            "physics_baseline_matched": freeze.get("physics_baseline_matched"),
        },
        "pending": [],
        "limitations": [
            "Synthetic data; no real-device calibration or concentration-accuracy proof.",
            "A cross-member dedup was waived by the coordinator before spectra generation.",
        ],
    }
    write_json(DELIVERY / "code_verification.json", code_verification)

    max_diff = max(float(row["replay_max_abs_array_difference"] or 0.0) for row in rows)
    duration_seconds = (datetime.fromisoformat(summary["finished_at_utc"])
                        - datetime.fromisoformat(summary["started_at_utc"])).total_seconds()
    production = {
        "schema": "D-production-report/v1",
        "generated_at_utc": now(),
        "run_summary": "reports/run_summary_D.json",
        "run_started_at_utc": summary.get("started_at_utc"),
        "run_finished_at_utc": summary.get("finished_at_utc"),
        "duration_seconds": round(duration_seconds, 3),
        "duration_minutes": round(duration_seconds / 60, 2),
        "workers": summary.get("workers"),
        "batch_count": len(rows),
        "spectra": sum(row["spectra"] for row in rows),
        "profiles": sorted({row["profile"] for row in rows}),
        "shards": sorted({row["shard"] for row in rows}),
        "audit_passed": sum(row["audit_status"] == "passed" for row in rows),
        "replay_passed": sum(row["replay_status"] in ("passed", "passed_with_environment_differences")
                             for row in rows),
        "full_replay_spectra": sum(row["replay_spectra"] for row in rows),
        "replay_max_abs_array_difference": max_diff,
        "zip_bytes": sum(row["zip_bytes"] for row in rows),
        "sealed_source_bytes": tree_bytes(WORK / "production" / "batches"),
        "qc_bytes": tree_bytes(WORK / "production" / "qc"),
        "commands": {
            "runner": "python scripts/run_batches_D.py --phase all --workers 6",
            "batch_template": ("python fp_competition/app.py batch --samples <shard> "
                               "--profile <P1|P2|P3> --out <batch-dir> --seed <seed> "
                               "--replicates 2 --closure strict --legacy-al reject "
                               "--targets <32 elements> --split-seed 20261022 "
                               "--design-ranges <design_ranges.json>"),
            "audit": "python fp_competition/app.py audit --dataset <batch-dir> --out <audit.json>",
            "replay": "python fp_competition/app.py replay --dataset <batch-dir> --out <replay.json>",
            "pack": "python fp_competition/app.py pack --dataset <batch-dir> --out <batch.zip>",
        },
        "environment": environment,
        "capacity": {
            "cpu_count": os.cpu_count(),
            "total_delivery_bytes_before_hashes": None,
        },
    }
    write_json(DELIVERY / "reports" / "production_D.json", production)
    shutil.copy2(SUMMARY, DELIVERY / "reports" / "run_summary_D.json")

    index = {
        "schema": "D-delivery-index/v1",
        "owner": "D",
        "round_id": config["round_id"],
        "generated_at_utc": now(),
        "software_version": config["software_version"],
        "physical_model_version": config["physics_version"],
        "counts": {
            "recipes": 250,
            "backups": 30,
            "batches": 30,
            "spectra": 1500,
            "profiles": 3,
            "shards": 10,
            "target_elements": 32,
        },
        "files": {
            "recipes": "design/candidate_samples_D.json",
            "recipe_registry": "design/formula_registry_D.csv",
            "backup_registry": "design/backup_registry_D.csv",
            "coverage": "design/coverage_D.json",
            "design_checks": "design/design_checks_D.json",
            "parent_families": "design/parent_families_D.json",
            "shards": "design/shards",
            "run_config": "D_run_config.json",
            "seed_manifest": "D_seed_manifest.json",
            "environment": "reports/environment_D.json",
            "production_report": "reports/production_D.json",
            "code_verification": "code_verification.json",
            "sha256_index": "SHA256SUMS",
        },
        "acceptance": {
            "status": "coordinator_direct_confirmation_no_A_dedup",
            "cross_member_dedup": "waived_by_coordinator",
            "note": ("The coordinator confirmed the D candidate set and authorized immediate "
                     "spectra generation on 2026-10-22; the A cross-member dedup response was waived."),
        },
        "verification": {
            "audit_passed": 30,
            "replay_passed": 30,
            "full_replay_spectra": 1500,
            "audit_errors": 0,
            "replay_errors": 0,
            "replay_max_abs_array_difference": max_diff,
            "target_elements_per_batch": 32,
            "no_replay_limit": True,
        },
        "batches": rows,
        "limitations": [
            "Synthetic only; no real-device calibration, detection-limit validation, or 95%/5% blind accuracy proof.",
            "Cross-member dedup with A was waived by the coordinator; it is not an A acceptance.",
            "The A freeze manifest is A-only; D does not claim a global freeze.",
        ],
    }
    write_json(DELIVERY / "index_D.json", index)

    decision = {
        "schema": "D-coordinator-decision/v1",
        "decision": "waive_A_cross_member_dedup_and_proceed_to_spectra",
        "decided_by": "coordinator",
        "decided_at_utc": "2026-10-22T00:00:00+00:00",
        "scope": "D candidate set 250 + 30 backups",
        "effect": "D spectra were generated without an A cross-member dedup response.",
        "source": "Coordinator selected '你直接确认，立即出谱' in the build session.",
    }
    write_json(DELIVERY / "reports" / "coordinator_decision_D.json", decision)

    readme = f"""# 成员 D 第二轮交付

生成器 {config['software_version']}；物理模型 {config['physics_version']}。
本包包含 250 个配方（150 硅酸盐/氧化物 + 100 富铁氧化物）和 1,500 条合成谱：
10 个分片 × 3 个冻结条件 P1/P2/P3 × 2 次独立重复；每批 25 配方 × 2 = 50 谱。

## 目录

- `design/`：配方、母族、范围/闭合/去重/覆盖检查、分片文件。
- `frozen_inputs/`：P1/P2/P3、design_ranges、A_run_config、A 冻结清单。
- `scripts/`：配方构建、批次运行、交付装配脚本。
- `spectra/P1|P2|P3/`：30 个密封批次 ZIP，每批 50 谱；同名 `.sha256` 为 ZIP 哈希。
- `qc/`：30 份包外 audit 和 30 份全量 replay 报告。
- `reports/`：环境、冻结校验、生成器测试、运行汇总、生产报告、协调人决定。
- `index_D.json`：批次、种子、ZIP 哈希、audit/replay 状态的总索引。
- `SHA256SUMS`：本交付树逐文件哈希。

## 复现

```bash
python scripts/build_candidates_D.py
python scripts/run_batches_D.py --phase all --workers 6
python scripts/assemble_delivery_D.py
```

每批实际命令为：

```bash
python fp_competition/app.py batch --samples <shard> --profile <P1|P2|P3> \
  --out <batch-dir> --seed <seed> --replicates 2 --closure strict \
  --legacy-al reject --targets <32 elements> --split-seed 20261022 \
  --design-ranges <design_ranges.json>
```

未使用 `--jitter`；未对 audit/replay 使用 `--limit`；未改物理核心。
每条谱的 `manifest.json`、`truth.jsonl`、`blind_inputs/`、`full_results/`、
`integrity.json` 和生成器源码快照都在对应 ZIP 内。

## 自检结果

- audit：30/30 通过，1,500/1,500 谱检查。
- replay：30/30 全量通过，1,500/1,500 谱重算；`scope=all_records`，无 `--limit`。
- 生产耗时：{duration_seconds / 60:.1f} 分钟（{summary.get('started_at_utc')} → {summary.get('finished_at_utc')}，6 workers）；
  30 个 ZIP 合计 {sum(row['zip_bytes'] for row in rows) / 1e6:.1f} MB。
- 最大数组绝对差：{max_diff}；同环境计数逐道一致。
- 配方自检：250 条，严格闭合最大偏差 1.42e-14%；范围违规 0；重复组 0；
  分片/干扰组检查全部通过。
- 覆盖判据：routine/sparse 痕量元素使用 log10 跨度 ≥0.5 且非零率 ≥0.5；
  化合物/平衡使用线性跨度 ≥0.5；干扰组使用受控组检查。

## 重要边界

- 全部为合成数据；未验证真实设备校准、检出限或真实盲测 95%/5% 准确度。
- 协调人于 2026-10-22 直接确认 D 候选并授权立即出谱，**A 的跨成员去重回复被豁免**；
  这不等于 A 的验收，也不能写成已通过跨成员去重。决定记录见
  `reports/coordinator_decision_D.json`。
- A 冻结清单仅覆盖 A；D 不声称全局冻结。
- 零值是模型输入，不代表真实世界“未检出”。
"""
    (DELIVERY / "README.md").write_text(readme, encoding="utf-8")

    production["capacity"]["total_delivery_bytes_before_hashes"] = tree_bytes(DELIVERY)
    write_json(DELIVERY / "reports" / "production_D.json", production)

    lines = []
    for path in sorted(DELIVERY.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{sha256(path)}  {path.relative_to(DELIVERY).as_posix()}")
    (DELIVERY / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                         newline="\n")
    delivery_bytes = tree_bytes(DELIVERY)

    print(json.dumps({
        "delivery": str(DELIVERY),
        "batches": len(rows),
        "spectra": sum(row["spectra"] for row in rows),
        "zip_bytes": sum(row["zip_bytes"] for row in rows),
        "delivery_bytes": delivery_bytes,
        "audit_passed": 30,
        "replay_passed": 30,
        "max_abs_array_difference": max_diff,
        "tests": tests,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
