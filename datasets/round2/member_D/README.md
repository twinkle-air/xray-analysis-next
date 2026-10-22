# 成员 D 第二轮交付

生成器 0.2.1；物理模型 0.2.0。
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
python fp_competition/app.py batch --samples <shard> --profile <P1|P2|P3>   --out <batch-dir> --seed <seed> --replicates 2 --closure strict   --legacy-al reject --targets <32 elements> --split-seed 20261022   --design-ranges <design_ranges.json>
```

未使用 `--jitter`；未对 audit/replay 使用 `--limit`；未改物理核心。
每条谱的 `manifest.json`、`truth.jsonl`、`blind_inputs/`、`full_results/`、
`integrity.json` 和生成器源码快照都在对应 ZIP 内。

## 自检结果

- audit：30/30 通过，1,500/1,500 谱检查。
- replay：30/30 全量通过，1,500/1,500 谱重算；`scope=all_records`，无 `--limit`。
- 生产耗时：61.0 分钟（2026-10-22T07:53:32.405912+00:00 → 2026-10-22T08:54:35.153142+00:00，6 workers）；
  30 个 ZIP 合计 355.5 MB。
- 最大数组绝对差：0.0；同环境计数逐道一致。
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
