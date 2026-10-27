# 第四轮 D 全量生产交付

D 分部配额 **20,000 谱**：1,000 条候选配方（320 个预合并设计族，候选阶段已由 PR #48 合并）× 10,000 条件 × 2 次噪声重复，分 **200 个原生密封批次**（每批 100 谱）。角色分布 **train 16,000 / validation 2,000 / sealed_test 2,000**，与放行文件一致。

生产在 `production_release_v1.json`（`status=approved_for_full_production`、`production_approved=true`、`pilot_spectra=0`）与 `production_release_v1_activation.json` 的负责人明确授权后开始，使用 `datasets/round4/shared/freeze_v1` 冻结输入（`freeze_manifest.json` SHA-256 `25deee3198281d033641ca45817a40727461269df11d653df5ca842b908fa519`）。冻结的 runner、生成器和输入文件全程未被修改。

## 质检状态

200/200 批通过：预注册窗外预算、完整 audit（`spectra_checked=100`）、完整物理 replay（`scope=all_records`、`spectra_recalculated=100`、无 errors）、pack、ZIP CRC 与 SHA-256。除 runner 自身结论外，`tools/verify_production_D.py` 独立重算了全部 200 个归档的 SHA-256、ZIP CRC、逐批 QC 文件哈希、audit/replay 覆盖，并逐条重算 20,000 条 `full_results` 与 `blind_inputs` 内容哈希、盲导出条目哈希与顶层键，结果为 200 通过 / 0 失败。

该复核脚本的退出码是契约的一部分：期望集合直接取自冻结 `batch_plan.json`（member D 的 200 批）与 `record_plan_D.csv`（20,000 条），任何缺批、多批、摘要状态非 `passed_all_records`、QC 文件哈希不符、audit/replay 覆盖不足、窗外超预算、索引行数或字段与冻结计划不符、`eligible_for_training` 不为 false、盲包条目数/哈希/命名或顶层键异常，都会写入机器可读报告 `reports/independent_verification_D_full.json`（`status`、`exit_code`、`failure_count`、`failed_check_names`）并以非零码退出；只有全部通过才返回 0。`tools/selftest_verify_D.py` 用合成语料对这些失败路径做负例自测（基线 + 缺批、多余批、归档被改、QC 哈希破坏、audit 少 1 条、摘要状态改坏、索引缺行、角色被改、资格被改、窗外超预算、盲包缺条、盲包混入标签、full_results 篡改，共 14 例），断言每种坏数据都让复核脚本非零退出并点名对应检查项。

盲样本包 `archives/D_round4_blind_inputs.zip` 含 20,000 个 opaque 命名条目，顶层键仅 `axis`、`counts`、`signal_unit`、`synthetic`、`x`，不含成员、元素、浓度、族、条件或种子标签；`actual_record_index.csv` 与 ZIP 条目一一对应，全局记录 ID 与 opaque ID 各 20,000 且唯一。

## 目录内容

- `actual_record_index.csv`：20,000 条记录索引，固定全局 ID、配方/设计族、用途、profile、计数子种子、盲/全结果哈希、所属 ZIP，以及 `eligible_for_training=false`。
- `archives/R4_D_*.zip`：200 个原生批次归档（每批 100 谱，含 blind_inputs、truth、full_results、输入/配置、环境与逐批命令记录），单包最大 25 MB。
- 仅盲样本导出 `D_round4_blind_inputs.zip`（160,410,944 B）以 4 个分片随仓库交付于 `blind/`：GitHub 对单文件设 100 MB 硬限且本仓库未启用 LFS。拼接与校验见 `blind/RESTORE.md`，整包 SHA-256 固定为 `cbd82cb4894fedc429a80e732c4fb7aa91abcacf8daea753d25a434b1fc612df`，分片哈希见 `blind/PARTS.sha256`；本次交付已在本地完成还原并通过 ZIP 内部 CRC 与 20,000 条目核对。
- `tools/`：本次实际使用的非冻结辅助脚本（回收并发包装器 `run_member_recycle.py`、独立复核 `verify_production_D.py`、复核负例自测 `selftest_verify_D.py`、组包 `package_D_round4.py` 与元数据 `finalize_D_round4.py`）。包装器只子类化 `concurrent.futures.ProcessPoolExecutor`，冻结 runner 与生成器未被改动，`reports/delivery_verification.json` 中记录了 runner 哈希与放行文件一致。包装器按真实仓库根解析冻结工具目录（依次尝试当前工作目录、脚本自身各级父目录，并可用 `XRAY_REPO_ROOT` 或 `XRAY_PRODUCTION_TOOLS` 显式覆盖），因此从仓库任意深度运行同一份交付脚本都能 `import run_member`；早期版本用 `parents[1]` 推导，只在该脚本位于 `work/` 时成立，从本目录运行会解析到 `production_v1/datasets/...` 并抛 `ModuleNotFoundError`，现已修正。
- `reports/D_all_batch_QC.zip`：逐批 audit/replay/window_budget/summary/commands/actual_record_index 证据。
- `archive_index.json` / `batch_metrics.json`：逐批哈希、字节数、窗外最大损失比例、生成+质检耗时与角色分布。
- `frozen_identity.json` / `reports/commands_and_environment.json`：冻结输入、放行、解释器与依赖、并发策略与命令记录。
- `selfcheck_summary.json`：runner 在 200 批全通过后写出的成员级自检（`status=passed_member_full_QC_pending_coordinator_acceptance`、`packaging_status=complete`）。
- `delivery_manifest.json`：本目录除自身外全部文件的 SHA-256 与字节数。

## 失败与中断证据

同一目录内的 `reports/failed_attempts/` 保留 6 次尝试的说明与 QC 证据（`attempt_notes.json` + 各批 `failure.json`/`window_budget.json`/`commands.json`），未删除、未放宽预算、未删谱：

1. `attempt1_workers4_*`：4 并发下 7 个 MemoryError 批次 + 4 个中断批次。
2. `attempt2_workers2_*`：按负责人要求切回 3 并发时保留的在途批次。
3. `attempt3_session_stopped_*`：宿主应用重启终止作业造成的 3 个在途批次。
4. `attempt4_oom_workers3_*`：3 并发下 22 个 MemoryError + 3 个中断（Windows 提交内存耗尽，事件 2004）。
5. `attempt5_session_logoff_*`：2026-10-26 18:42 用户注销登录终止 6 个在途批次。
6. `attempt6_worker_vanish_*`：2026-10-26 23:01 六个 worker 进程在生成 77–97 条时消失（无 MemoryError、无 failure.json、系统未重启，同刻出现 nvlddmkm 事件 153）。

上述失败/中断批次全部以相同冻结种子与条件**从头重跑**并完整通过后才纳入交付；其中间谱数据保留在本地 `outputs/round4-D-production/failed_attempts/`（`outputs/` 被 gitignore，不进入交付，因为它从未通过 QC）。最终一轮使用 6 workers + 每 2 批回收（`tools/run_member_recycle.py`，生产时同份脚本位于 `work/`；仅子类化进程池以限制单进程驻留内存，未改动冻结 runner），完成剩余 84 批，0 失败。

## 使用限制

sealed_test 的 2,000 谱（含 `R4_D_sealed_test_none_sealed_challenge_*`、`..._in_distribution_*` 批次）仅用于物理 QC 与生成校验，在最终模型与指标锁定前禁止进入训练、校正、响应字典或选参；全部 20,000 条记录 `eligible_for_training=false`，交付中 `training_inclusion_approved`、`scientific_accuracy_verified`、`external_independently_blinded` 均为 false。本轮未验证真实设备浓度准确度，也不是外部独立盲测；接受与否由协调人复核决定。

## 复现

仓库根目录、冻结依赖虚拟环境，输出必须是新目录（`--repository` 指向仓库根；脚本本身位于交付目录）：

```powershell
& 'C:\path\to\round2-D-work\.venv\Scripts\python.exe' -B datasets/round4/member_D/production_v1/tools/run_member_recycle.py --repository . --freeze datasets/round4/shared/freeze_v1 --release datasets/round4/shared/releases/production_release_v1.json --member D --out outputs/round4-D-production --workers 6 --minimum-free-gib 10 --include-sealed-qc
```

同一命令加 `--dry-run` 即无谱预检（只校验冻结身份、放行与计划，不计算任何谱）。独立复核与负例自测：

```powershell
& 'C:\path\to\round2-D-work\.venv\Scripts\python.exe' -B datasets/round4/member_D/production_v1/tools/verify_production_D.py --out outputs/round4-D-production --report outputs/round4-D-production.independent_verification.json
& 'C:\path\to\round2-D-work\.venv\Scripts\python.exe' -B datasets/round4/member_D/production_v1/tools/selftest_verify_D.py --report outputs/round4-D-verifier-selftest.json
```

复核脚本对 200 批/20,000 条的覆盖来自冻结计划本身，不接受“少几条也算过”：`--out` 目录缺批、证据哈希不符或索引行数/字段与冻结计划不符时 `status=fail` 且退出码为 1，负例自测同样以非零码失败。两份脚本的实际运行结果记录在 `reports/independent_verification_D_full.json`、`reports/verifier_selftest_D.json` 与 `reports/fresh_clone_entrypoint_check.json`。

入口可用性实测（2026-10-27，PR #55 复核意见第 2 项）：把 `datasets/round4/member_D/production_v1/tools/`、`datasets/round4/shared/production_tools/`、`datasets/round4/shared/freeze_v1/`、放行文件以及 `freeze_manifest.json` / `input_identity.json` 列出的全部冻结输入按仓库相对路径放入一个全新目录（模拟新 clone），在仓库外的工作目录下执行交付路径的 `run_member_recycle.py --help` 与 `--dry-run`：两者均退出 0，预检返回 `status=passed_no_spectrum_preflight`、200 批 / 20,000 条 / 10,000 条件、`pilot_spectra=0`、`spectra_generated=0`、`freeze_manifest_sha256=25deee3198281d033641ca45817a40727461269df11d653df5ca842b908fa519`。
