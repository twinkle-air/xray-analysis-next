# 第二轮成员 B：本地暂定谱交付报告

**状态：B 本地暂定条件自检通过，待协调人决定是否纳入全局。** 用户在 2026-10-21 明确接受以 A 封存的三份 P1/P2/P3 和 B 独立种子先行生成。A 仓库原配置声明 `A production only; not global shared-input approval`；这里没有将 B 的结果冒称全局统一冻结、设备实测准确度或独立验收。

## 实际数量

- 配方 250：硅酸盐/氧化物 150（90/30/30），富铁氧化物 100（60/20/20）。候选内部唯一，10 个完整五联干扰母族，32 个目标均覆盖。候选检查见 `B2_candidate_selfcheck.json`。
- 30 个新密封批次，每批 25 配方 × 2 噪声谱 = 50；每个 P 条件 10 批、500 谱，合计 **1,500**。每个配方在每条件恰好出现两次。小片 `P1_S01` 计入总数。
- 全局复合谱 ID（`批次名/包内ID`）1,500 个不同，实际子种子 1,500 个不同。每片保留一个完整五联母族和 20 个单独母族。包内 `S000001` 等短 ID 按批次限定，不应脱离批次名使用。
- 每批 manifest 完整、无 jitter；三条件均严格闭合，`legacy-al=reject`，32 目标固定。

## 输入来源与版本

候选文件 SHA-256：`3792a372e194376614a003d6b92a2fa3861d85aa47259be681149d31f6becbd6`；范围文件 SHA-256：`35761426ebf31bda0eb03c63b0b2eb5481f72f37f6e4c28f06473ab043d2c194`。候选范围来自本地 0.2.1 矿物范围及第一轮 B 留存的富铁设计池，属于本地暂定范围。

三份 profile 与[仓库 A 封存目录](https://github.com/twinkle-air/xray-analysis-next/tree/main/datasets/round2/member_A/production_inputs_v2/profiles)的字节 SHA-256 相符；P1/P2 与本地第一轮 A 文件相同，P3 从仓库原样下载：

| 条件 | 完整 JSON 的 SHA-256 | 谱数 |
| --- | --- | ---: |
| P1 | `e50445c38014adb169d766202df1e84f48b9ea86d72659ca5029ea73bad1f221` | 500 |
| P2 | `a60fe0c574b7c9e03f0448632ed34b4f19e634aa0be04b59ab5e625430415e03` | 500 |
| P3 | `0e866901f7243eaeb51e323535198c17c52f7eb42abe18a4b4e0b0ad691cd351` | 500 |

本地生成器软件 0.2.1、物理核心 0.2.0。关键源码与 A 封存清单对应：

| 文件 | SHA-256 |
| --- | --- |
| app.py | `6f515db4d5f9d26af9ec261fdb60e62bf1c848b9e7b9ab3930961c8d393159c8` |
| core.py | `e820ecdb5ed5fbceb870f382c8c7c411ba85c65673bc19258fb935f562ed83b0` |
| dataset.py | `8a62ad4f291d63d7c9a7a555f519d617e143b13e58a9f41671f299d9c7bfa002` |
| minerals.py | `69fb768c041ef100721794628f46cb8b90c5acbf5f4c4a45c5e088bca6de1662` |
| requirements-lock.txt | `58dd77fc58fbcccfa311b84128624bf25c3f8d19379b2dd2beb224a90772fae0` |

每批保留 `inputs/`、`configs/`、`reproducibility/` 源码及依赖快照。实际 Python/依赖环境见 `B2_stage_preflight.json` 及各批 `reproducibility/environment.json`。线程环境为 `OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=MKL_NUM_THREADS=1`。本机解释器启动会显示旧 `D:\Python313\python.exe` 的位置警告，但 120 个实际生产/自检命令均以 0 退出，完整重算均报告同一环境。

B 批次 seed 采用 `20261021020101..10`（P1）、`20261021020201..10`（P2）、`20261021020301..10`（P3），split seed 为 `2026102102`。这 30 个批次 seed 与仓库 A 配置中的 `2026102101xx` 命名空间不同；没有 C/D 的冻结 seed 清单，因此不宣称全局冲突检查已完成。生成器内部分组只是完全相同组成的分组，不能作为合库权威划分。

## 实际检查

所有 30 批由**各自包内** `reproducibility/generator/fp_competition/app.py` 执行 audit 和不带 `--limit` 的全量 replay；各 1,500/1,500 谱覆盖，`status=passed`、`errors=[]`。重算最大数组绝对差异为 `0.0`，环境差异批次 `0`。每批 pack 后核对 ZIP 外部 SHA-256 和全 ZIP CRC；30/30 通过。跨片数量、样本重复、复合 ID、子种子、profile 与核心哈希检查见 `B2_provisional_summary.json`。

| 阶段 | 实际批次 | 非零退出码 | 各批耗时合计（秒） |
| --- | ---: | ---: | ---: |
| batch | 30 | 0 | 4347.2 |
| audit | 30 | 0 | 134.8 |
| replay | 30 | 0 | 5097.3 |
| pack | 30 | 0 | 188.7 |

逐批**准确命令、起止时间、退出码和时长**在 `reports/P*_S*.run.json`，标准输出在 `logs/`。代表小片先完成全套四阶段并通过，随后启动其余分片。所有密封谱在 `sealed/`，对应 ZIP、`.zip.sha256`、包外 audit/replay 在 `reports/`。外部汇总哈希见 `B2_provisional_zip_hashes.sha256`。

容量：密封目录合计 1.461 GiB（1569099562 字节）；30 个 ZIP 合计 0.315 GiB（338693901 字节）。完整工作区可用磁盘容量见 `B2_stage_preflight.json`。保留全部 blind、truth、full、输入、manifest、integrity 与源码；无选择性删谱。

## 合库边界与保留记录

协调人仍须按全局配方、母族及近邻建立外置权威索引并检查跨成员冲突。`B2_near_neighbor_summary.json` 和 `B2_nearest_neighbor_registry.csv` 提供 B 内部 L1 近邻诊断，不设权威阈值。任何训练/验证/内部测试划分都不应直接拼接各分片 generator split。

候选阶段曾有两份失败检查记录，保存在 `B2_candidate_failure*.json`；修正后最终候选自检通过。没有失败谱目录被删除。第一轮旧包与 GitHub 仓库均未修改。
