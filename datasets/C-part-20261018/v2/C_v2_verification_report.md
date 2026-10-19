# C 部分 v2 修复验证报告（PR #2 第二轮评审后修订）

批次：`C-part-20261018`（分支 `c-part-20261018`；数据提交 `cdc4f739…`，候选标注提交 `5c9439f…`；
PR #2 两轮均为 requested changes，未合并）
定位：**候选试产 pilot-only**（按已确认的处置选择），失败批次身份与密封数据保留、不重写。

本报告只包含**代码改动 + 只读复算 + 计划预检**。三处配方问题的"已消除"一律指
**v2 主表按同一断言复算的结果**，已归档的 2000 条谱仍来自 v1 主表，其数据在本批内没有改变；
按第二轮评审意见，本批只作失败批次归档，交付以修正后的说明与可复现代码为准。
生成日期：2026-10-19（第二轮修订同日）。

---

## 1. 评审五条的独立复算（用我自己的数据，逐条对账）

复算脚本：`scripts/check_review_findings.py`、`scripts/design_c_alloy_formulas_v2.py::v1_baseline`
（只读 `master_samples.json` 与已密封 `P5_dataset/manifest.json`、`truth.jsonl`）。
机器可读结果已随批次提交：`v2/review_findings_check.json`（同一脚本在本目录布局下
以 `C_samples.json` + `C_authoritative_index.csv` 复跑即可再生成）。

| 评审结论 | 评审数字 | 我的复算 | 是否一致 |
| --- | --- | --- | --- |
| 1000 行配方仅有独立组成 | 944 | **944**（重复组 34） | 一致 |
| 常规配方越出自身声明范围 | 548/600 | **548** 行（越界项 1334） | 一致 |
| 稀疏/边界同样越界（评审未逐条列出） | — | 稀疏 **200/200** 行、干扰 **143/200** 行越界（全表合计 891 行 / 1750 项） | 比评审更严重 |
| P5 索引把留出批次标成可训练划分 | train 1402 / validation 302 / test 296 | **train 1402 / validation 302 / test 296** | 一致 |
| 干扰对照被写死 Ni=8、Fe 参与对照 | 举例 C0813/C0818 | **C0813 = {Co 2.0, Ni 8.0, Fe 90.0}、C0818 = {Co 10.0, Ni 8.0, Fe 82.0}**；20 对里有 3 对含 Fe（Mn/Fe、Fe/Co、W/Fe） | 一致 |
| 9 组相同组成跨集合 | 9 | 相同采用组成跨 v1 benchmark_split 的组 **9**（v1 主表内部重复组 34） | 一致 |

结论：评审全部成立，且稀疏/边界与干扰情景的越界面比评审举出的常规情景更大。
归档侧的哈希与源码编译检查通过，与上述数据逻辑问题相互独立——这一点评审的说法也成立。

---

## 2. 代码改动（新脚本随批次提交，旧脚本与密封数据未动）

| 脚本 | 作用 | 修的是哪条 |
| --- | --- | --- |
| `scripts/design_c_alloy_formulas_v2.py` | 重做 1000 条主配方设计，输出 `v2/master_samples_v2.json` | P2-1 / P2-2 / P2-3 |
| `scripts/build_p5_index_v2.py` | 重做权威索引与全局划分（并查集 leak_group + 统一 heldout） | P1-1 / P1-2 |
| `scripts/c_pilot_guard.py` | 训练/调参入口守卫（拒绝而非静默放行）+ 自检 | 评审"从所有入口隔离"要求 |
| `scripts/pregenerate_dryrun_v2.py` | 生成前可行性预检（只跑 `make_plan`，不落盘） | 启动生成前的闸门 |
| `scripts/reproduce_v2_check.py` | 在临时目录复刻仓库布局重跑三件事，并与仓库内产物逐字节对账 | 第二轮：让"已修复"可验证 |
| `scripts/v2_generation_status.py` | 只读汇报 v2 批次真实进度/一致性/是否密封，杜绝口头声明 | 第二轮：说明与事实对齐 |
| `scripts/generate_v2_batch.py` | v2 批次续跑生成（新目录，不触碰 `P5_dataset`） | 后续批次的生成入口 |
| `scripts/annotate_candidate_batch.py` | 把旧批次标注为 review_failed/pilot_only，修正 README 泄漏说法 | P1-1 的交付物侧 |

第二轮评审后追加的可移植性改动（否则评审在仓库里跑不动，也无法验证）：

- 三个脚本的路径都可在仓库布局下直接解析：主表缺省按 `master_samples.json` → `C_samples.json`
  顺序取，输出目录可用位置参数或环境变量 `C_V2_OUT_DIR` 指定；生成器根目录可用
  `FP_COMPETITION` 覆盖。
- 报告不再写绝对路径，只写**文件名 + SHA-256**（`design_selfcheck_v2.json` 的 `master_file`、
  `index_policy_check_v2.json` 的 `master_file/master_sha256/dataset_manifest_sha256`、
  `pilot_guard_selftest.json` 的 `index/index_sha256`），因此换机器/换布局产出逐字节相同。
- 入口守卫的拒绝文案删掉了"改用 A/B 批次"的推荐，改为要求核对目标批次自身的
  `usage_policy` 与评审状态（见第 6 节）。

设计层面的三个根因 fix（对应 v1 的具体缺陷）：

1. **P2-1 独立组成**：v1 稀疏情景用 `fe = 95.0 - 0.1*k` 制造差异，但 `close_percent` 把 Fe 归一化补到 100%，k 循环被抹平；且采用组成只存非零元素，"某元素=0" 不留痕，不同目标的零配方塌成同一组成。
   v2 改为：低含量档 = 元素自身上限 × (0.0005, 0.002, 0.01, 0.05, 0.35)（20 个适用目标 × 5 档）；零配方 = 目标缺席 + 按 (目标序号, 序号) 编码的**唯一微量共存签名**（水平步长 1e-4，100 个零配方互不相同）；再加全局去重补足与"1000 行 1000 种"的硬断言。
2. **P2-2 干扰对照**：v1 每行写死 `{**vals, 'Ni': 8.0, 'Fe': fe}`。v2 把 3 个含 Fe 的对替换为等效非 Fe 对（Mn/Cu、Co/Ti、W/Nb），背景母配方从不含 a/b/Fe 的元素里采、同族两档共用，浓度档 `u = min(hi_a, hi_b)/6`（5:1 变体峰值 5/6·上限，永不撞声明上限）；每个 variant 逐条断言存在性、背景值不被改写、equal/1:5/5:1 的实际比值。
3. **P2-3 范围自洽**：v1 常规采样只校验 Fe，从不校验声明的每元素区间。v2 先验按每元素冻结区间采样，闭合后再按**该行自己的 `provenance.ranges_percent`** 逐字段断言。同时把 Fe 的声明区间按场景拆开（常规/干扰 55–90%，超纯稀疏 90–99.99999%），消除 v1"高纯痕量配方却声明 Fe≤90%"的自我矛盾。

划分层面的两个 fix：

4. **P1-1 留出语义**：v2 索引 2000 行全部 `holdout_status=condition_heldout`、`benchmark_split=heldout`、`usage_policy=pilot_only_isolated_from_training_and_tuning`；原 train/validation/test 语义降级为**描述性**字段 `recipe_family_split`，并注明不得作基准划分；README 里"下游只按 `benchmark_split` 读取训练数据"一句已作废改写。
5. **P1-2 泄漏**：划分粒度改为并查集分量 `leak_group` = 实际采用组成 ∪ `parent_family` ∪ 生成器族（manifest 里的 family）∪ 同配方噪声重复；所有划分只在 leak_group 上进行，并断言"相同组成不跨集合 / parent_family 不跨集合 / 重复不跨集合"。

---

## 3. 自检结果（针对 v2 主表与新策略；全部通过）

`v2/design_selfcheck_v2.json` / `.md`：

- 行数 1000，情景配额 `{regular 600, sparse 200, interference 200}` ✅
- **独立采用组成 1000/1000，重复组 0**（v1：944/34）✅
- **越出自身声明范围的行 0，越界项 0**（v1：891 行 / 1750 项）✅
- 闭合非 100% 的行 0；Fe 区间 [55.0, 99.99999]，全部行铁基体 ✅
- 干扰族 40 组 × 5 变体 ✅；含 Fe 的干扰对：无 ✅；背景覆盖目标：无 ✅
- 稀疏：20 个目标元素，每元素低含量 ≥5、零配方 ≥5，零配方目标元素确实缺席 ✅
- 从未出现的元素：无 ✅ → `passed: true`

`v2/index_policy_check_v2.json`（对现有 v1 批次跑新策略，验证策略本身）：

- 2000 行 `benchmark_split` 唯一取值 `heldout` ✅
- leak_group 801 个（组大小分布 1:754、2:18、5:28、70:1 —— 那个 70 的巨型组正是 v1 稀疏塌缩被并查集抓出来的证据）
- 相同组成跨集合 0、parent_family 跨集合 0、噪声重复跨集合 0 ✅ → `passed: true`

`v2/pilot_guard_selftest.json`：train / validation / test 三个入口**全部抛 `PilotIsolationError`**（2000/2000 行被拦），不会静默返回可训练行 → `passed: true`

`v2/pregenerate_dryrun.json`（用生成器 0.2.1 的 `make_plan`，closure=strict、legacy_al=reject）：

| 主表 | 配方数 | 精确采用组成族数 | 计划谱数 | 接受 |
| --- | --- | --- | --- | --- |
| `v2/master_samples_v2.json` | 1000 | **1000** ✅ | 2000 | 是 |
| `master_samples.json`（v1） | 1000 | **944** ← P2-1 的直接证据 | 2000 | 是 |

目标元素 26 个，批次种子 2026110205、划分种子 20261102（新批次，不改旧批次）。

---

## 4. 归档批次的标注与随包提交（已推到分支）

- `cdc4f739…`：v1 数据交付（2000 谱 + 分卷 ZIP + 原始索引/验收）
- `5c9439f…`：候选标注（12 文件：10 新增 + `README.md`/`C_delivery_hashes.json` 修改），
  远端逐字节复核见 `v2/annotation_push_verification.json`
  （12 个改动文件远端 blob 与本地载荷字节一致；29 个密封/基线文件在两个提交里 blob id 相同；
  无删除项、无目标目录外改动）
- 本次（第二轮修正）新增：`scripts/` 下随包提交 14 个脚本（12 个新增 + 2 个修订：
  `build_github_payload.py` 取键修正、`c_pilot_guard.py` 删去 A/B 推荐），涵盖 v2 设计/索引/守卫/
  预检/生成/进度快照/复现对账/评审复算/文档引用自检/登记表修正/远端复核/两轮标注，
  `v2/` 下主表与全部自检与对账产物（`review_findings_check.json`、
  `reproduction_check_v2.*`、`annotation_push_verification.json`、
  `registry_scenario_fix_check.json`、`doc_reference_check.json` 等），
  根级重写件 `C_samples_v2.json`/`C_authoritative_index_v2.csv`/`C_global_split_v2.csv`/
  `C_coverage_v2.json`/`C_index_policy_check_v2.*`/`C_pilot_guard_selftest.json`/
  `C_formula_registry_v2.csv`，并改写下列两处说明：

| 第二轮意见 | 原表述的问题 | 现在的表述 |
| --- | --- | --- |
| 三项配方问题标成"已修复"但引用的新脚本、主表未提交 | 说明里指向 `scripts/design_c_alloy_formulas_v2.py`、`v2/master_samples_v2.json`，仓库里并不存在 | 两个脚本与主表、自检产物已随批次提交；发现状态改为 `fixed_in_v2_code_archived_batch_unchanged`，并写明"已消除"只针对 v2 主表，归档批次数据未变 |
| 把 A/B 试产数据推荐为可训练数据 | README 与 `C_batch_status.md` 写"请改用已通过评审的 A/B 批次" | 删除该推荐；改为"任何批次都要先核对自己的 `usage_policy` 与评审状态，本交付不为其他批次的可训练性作背书" |

密封数据依旧 0 处改动：`truth.jsonl`、`manifest.json`、`P5_pack.zip.part01–08`、
ZIP SHA-256 `9178746d…f3f2` 全部不变；`C_authoritative_index.csv` 等旧文件保留供审计，不删除。
引用完整性由 `scripts/check_doc_references.py` 机器校验（结果
`v2/doc_reference_check.json`：本目录文档里出现的每个 `scripts/*.py`、`v2/*`、`C_*`
引用都必须在该目录内真实存在，缺失项为 0）。

---

## 5. 复现方式（评审可在本地逐条验证）

```
python -B scripts/design_c_alloy_formulas_v2.py              # 只写 v2/，不碰密封批次
python -B scripts/build_p5_index_v2.py <解包后的数据集目录>   # 只读数据集，重建索引与划分断言
python -B scripts/c_pilot_guard.py                           # 三入口拒绝自检
python -B scripts/check_review_findings.py                   # 评审五条逐条复算
python -B scripts/fix_registry_scenario.py                   # 登记表 scenario 列对账（见第 7 节）
python -B scripts/reproduce_v2_check.py [数据集目录]          # 复刻仓库布局并与仓库产物逐字节对账
python -B scripts/check_doc_references.py [本目录]            # 文档引用是否都随包存在
```

已实测的复现性（`v2/reproduction_check_v2.json`）：

- 仓库布局（`C_samples.json` + `scripts/`）与本地布局分别跑设计脚本，
  `master_samples_v2.json` 三次都是 SHA-256
  `78ca94780021c17915565d152cffb234976e2d007d796126d84cbf4ce3d1a9b3`（2,963,316 B），
  断言字段完全一致；
- v1 主表在仓库里的副本 `C_samples.json` 与本地 `master_samples.json` 逐字节相同
  （SHA-256 `ff783d84c6a0cbe426ad777fec8700201e097ccf15bf9261274a348242435b05`），
  所以 944/34、891 行/1750 项这组基线数字在两种布局下复算一致；
- 索引侧 `index_v2.csv`、`global_split_v2.csv`、`coverage_v2.json` 两种布局逐字节相同；
  `index_policy_check_v2.*` 仅"主表文件名"一栏不同（`master_samples.json` vs `C_samples.json`），
  其 SHA-256 相同。

---

## 6. v2 批次数据的状态（不在本批交付内）

`scripts/generate_v2_batch.py` 在新目录 `fp_competition/P5_dataset_v2` 生成 1000 配方 × 2 重复，
旧批次目录与分卷不触碰。**是否完成、进度与一致性以随包提交的
`v2/generation_status_v2.json`（由 `scripts/v2_generation_status.py` 只读磁盘生成）为准**；
该批次未做 audit/replay/打包/推送，因此**不构成任何可交付数据集**，也不随本批提交谱数据。
按第二轮评审意见，本批只作失败批次归档，不阻塞评审。

写本报告时的最新快照（同日更新）：`qc_stage = sealed_complete_batch`、
`2000/2000` 谱、`blind_inputs / full_results / truth / manifest.records` 四者一致
（`consistent: true`）、manifest `status=complete`、主表
`master_samples_v2.json` SHA-256 `78ca9478…d1a9b3`、批次种子 2026110205 / 划分种子 20261102。
**仍缺**：全量 audit、全量物理 replay、交付打包与推送
（`qc_artifacts_present` 里 `audit.json`、`replay.json` 均为 false）。

同一套 v2 索引策略已经跑在这个新批次上（结果随包提交：
`v2/index_policy_check_v2_on_v2_data.json`，重建命令
`python -B scripts/build_p5_index_v2.py <P5_dataset_v2> v2/master_samples_v2.json C-recipes-v2 "C-recipes-v2(candidate)" <输出目录>`）：

| 指标 | 归档批次（v1 主表 + v1 谱） | 新批次（v2 主表 + v2 谱） |
| --- | --- | --- |
| 行数 / `benchmark_split` 唯一取值 | 2000 / `heldout` | 2000 / `heldout` |
| 配方的独立采用组成 | 944 / 1000 | **1000 / 1000** |
| 重复组成组 | 34 | **0** |
| leak_group 数与尺寸分布 | 801；`{1: 754, 2: 18, 5: 28, 70: 1}` | 680；`{1: 600, 5: 80}` |
| 相同组成 / parent_family / 噪声重复跨集合 | 0 / 0 / 0 | 0 / 0 / 0 |
| passed | true | true |

那个 70 成员的巨型 leak_group 正是 v1 稀疏情景塌缩的证据（多个目标元素的零配方被
归一化抹平后组成相同），在 v2 主表上不复存在；`{1: 600, 5: 80}` 与设计逐一对应：
600 条常规配方各自成组，40 个干扰族 × 5 变体 + 20 个痕量目标的 5 档低含量 +
20 个零配方档 = 80 个 5 成员族。这说明 P2-1 的修复在**新生成的数据**上而不是只在设计上成立。

评审第一轮提出的"正式 P5 需统一 5000 主表 + 全局划分 + 开发冻结"仍需 A/B/C 三方主表合并，
不在本批范围内（预算量级：≈5 倍时间与 ≈10 GiB 磁盘）。

---

## 7. 自查披露 SD-1：登记表 `C_formula_registry.csv` 的 scenario 列全空

复核载荷时发现（非评审提出，主动披露）：已推送的 `C_formula_registry.csv` 第 2 列
`scenario` 在 1000 行里全为空字符串。

- 根因：`scripts/build_github_payload.py` 取的是 `provenance['scenario']`，
  主表里的键名是 `provenance['design_scenario']`（`dict.get` 缺省返回 `''`，
  所以静默产生空列）。其余 10 列不受影响。
- 证据：`v2/review_findings_check.json` 的 `scenario_counts_in_registry = {"": 1000}`，
  同一时刻主表 `scenario_counts_in_master = {regular_variation 600, sparse_boundary 200,
  interference_control 200}`。
- 处置（不改归档字节）：`scripts/fix_registry_scenario.py` 从本目录 `C_samples.json`
  按 `formula_id` 逐行对齐补齐，产出纯新增的 `C_formula_registry_v2.csv`；
  对账文件 `v2/registry_scenario_fix_check.json` 断言：
  行序一致、`columns_that_differ == ['scenario']`、其他列 0 处值差异、
  补齐后 600/200/200、且把原文件按同格式（UTF-8 BOM + CRLF）重新序列化能得到与原
  字节完全相同的结果（`reserializer_roundtrip_bytes_identical: true`），
  证明差异只来自这一列。
- `scripts/build_github_payload.py` 的取键同步修正，未来批次不再产生空列。
- 影响评估：不涉及谱数据、真值、索引、划分与密封身份，不改变"本批次禁止训练/调参"的结论。
