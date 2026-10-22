# D 任务阶段 1 报告：环境与冻结校验

- 任务：第二轮 D 数据集构建
- 负责人：D
- 日期：2026-10-22
- 状态：阶段 1 完成，等待确认进入候选配方设计

## 1. 已完成动作

1. 在 `round2-D-work/.venv` 创建 Python 3.12.10 虚拟环境。
2. 严格按 `requirements-lock.txt` 安装全部依赖；`xraylib` 4.3.0 可正常导入并计算谱线能量。
3. 对 A 的 `freeze_manifest.json` 做逐文件 SHA-256 复核。
4. 生成 D 专用 `D_seed_manifest.json` 与 `D_run_config.json`。
5. 生成本报告、环境快照和 A 确认请求草稿。

未生成任何候选配方或谱；未写仓库；未创建 Issue/PR。

## 2. 环境

| 项目 | 值 |
|---|---|
| Python | CPython 3.12.10 (Windows x64) |
| numpy | 2.4.6 |
| scipy | 1.17.1 |
| matplotlib | 3.11.2 |
| xraylib | 4.3.0 |
| openpyxl | 3.1.5 |
| 软件版本 | 0.2.1 |
| 物理模型 | 0.2.0 |
| 线程环境 | OMP/OPENBLAS/MKL = 1（批次运行时设置） |

A 的交付记录显示其复核环境为 **Python 3.12.14**（`datasets/round2/member_A/code_verification.json`），不是先前方案中写的 3.13.14。D 使用 3.12.10，同一 minor 版本，patch 级差异已记录。

## 3. 冻结校验

| 类别 | 结果 |
|---|---|
| D 实际使用的冻结文件 | **40/40 哈希匹配** |
| 生成器源码与配置 | 35/35 匹配 |
| P1/P2/P3、design_ranges、A_run_config | 5/5 匹配 |
| `physics_baseline.json` 保护模块 | 3/3 匹配 |
| 哈希不一致 | 0 |
| 本地缺失 | 11：`A_samples.json` + `shards/S01–S10.json` |
| 缺失项影响 | 均为 A 的数据文件，D 不使用；PR #14 补丁未包含其正文，无法本地复核 |

关键哈希：

| 文件 | SHA-256 |
|---|---|
| P1.json | `e50445c38014adb169d766202df1e84f48b9ea86d72659ca5029ea73bad1f221` |
| P2.json | `a60fe0c574b7c9e03f0448632ed34b4f19e634aa0be04b59ab5e625430415e03` |
| P3.json | `0e866901f7243eaeb51e323535198c17c52f7eb42abe18a4b4e0b0ad691cd351` |
| design_ranges.json | `5f347d179830f7e9c64e0d98fd02397582f263171e83c773513347d5090c9c6d` |
| A_run_config.json | `4ddfc93fa2c308cb565fabcc28b58c0f569fd3e48d81a064c515f16db56ffae3` |

A 的冻结清单 scope 仍为 `A-only production freeze; global use pending`，`cross_member_confirmation: pending`。因此本报告不声称这些输入已完成全局冻结。

## 4. D 配置

- 30 个批次：10 个 shard × P1/P2/P3。
- 每批 25 个配方 ×2 replicates = 50 谱。
- 总计 250 配方、1,500 谱；每个条件 500 谱。
- 32 个目标元素；无 jitter；`closure=strict`；`legacy_al=reject`。
- batch seed = batch root ×100 + shard 序号。
- design seed、batch root、split seed 见 `D_seed_manifest.json`；状态为 `proposed_pending_A_confirmation`。

## 5. 产物

| 文件 | 说明 |
|---|---|
| `reports/environment_D.json` | Python、平台、依赖、线程环境、A 环境对照 |
| `reports/freeze_verification_D.json` | 51 项逐文件校验结果 |
| `D_seed_manifest.json` | 设计 seed、30 个 batch seed、split seed、派生规则 |
| `D_run_config.json` | 批次结构、目标元素、冻结输入哈希、并发与闭合策略 |
| `scripts/verify_freeze_D.py` | 冻结校验脚本 |
| `scripts/make_D_configs.py` | seed/run 配置生成脚本 |
| `reports/A_confirmation_request_D.md` | 待发给 A 的确认请求草稿 |

## 6. 已知限制

- A 的冻结清单纯 A-only；在 A 书面确认前，D 的候选设计只能标记为 provisional。
- A 的 `A_samples.json` 与 10 个 shard 未在 PR 中提供正文；D 不复用 A 的数据，因此不影响 D 的生产输入。
- 本机与 A 的 Python patch 版本不同；A 独立复核必须使用 D 包内的锁定依赖和生成器快照。
- 尚未进行生成器单元测试；首次真实批次 S01 将作为生产冒烟门槛。

## 7. 下一步 gate

等待确认后进入候选配方设计：用封存生成器生成 250 个配方（150 硅酸盐 + 100 富铁），完成范围/闭合/覆盖/去重/母族检查，输出候选包并提交 A 去重。A 确认前不生成任何谱。
