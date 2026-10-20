# v2 修复的可复现校验

- 结论：**通过**；产物字节对账 全部一致
- v1 主表（仓库副本 C_samples.json）SHA-256：`ff783d84c6a0cbe426ad777fec8700201e097ccf15bf9261274a348242435b05`

## 复跑方式

```
python -B scripts/design_c_alloy_formulas_v2.py      # 只写 v2/，不碰密封批次
python -B scripts/build_p5_index_v2.py <解包后的数据集目录>   # 只读数据集
python -B scripts/c_pilot_guard.py                   # 三入口拒绝自检
python -B scripts/reproduce_v2_check.py [数据集目录]  # 本校验
```

## 与仓库产物逐字节比对

| 文件 | 状态 | SHA-256（复现 / 仓库） |
| --- | --- | --- |
| `v2/master_samples_v2.json` | identical | `78ca94780021` / `78ca94780021` |
| `v2/design_selfcheck_v2.json` | identical_except_master_name | `8be2a3524407` / `59fd35e72680` |
| `v2/design_selfcheck_v2.md` | identical_except_master_name | `c32633fd3093` / `ca08fda1a7fb` |
| `v2/index_v2.csv` | identical | `a23ebe61d5a7` / `a23ebe61d5a7` |
| `v2/global_split_v2.csv` | identical | `5ee2b6a56163` / `5ee2b6a56163` |
| `v2/coverage_v2.json` | identical | `afa8fcadacca` / `afa8fcadacca` |
| `v2/index_policy_check_v2.json` | identical_except_master_name | `30c010e1f7b7` / `f5df23d35e76` |
| `v2/index_policy_check_v2.md` | identical_except_master_name | `bb6659d76267` / `4c770eacfde7` |
| `v2/pilot_guard_selftest.json` | identical | `bb23f8191f00` / `bb23f8191f00` |

- 设计断言字段一致：True；差异字段 无
- v2 主表：{"rows": 1000, "distinct_compositions": 1000, "rows_with_range_violations": 0, "range_violation_items": 0, "passed": true}
- v1 主表复算：{"available": true, "rows": 1000, "distinct_compositions": 944, "duplicate_groups": 34, "rows_with_range_violations": 891, "range_violation_items": 1750, "violations_by_scenario": {"regular_variation": 548, "sparse_boundary": 200, "interference_control": 143}}

- 守卫自检字段一致：True；被拒入口 ['train_entry', 'validation_entry', 'test_entry']

- 索引步骤：C-part-20261018 True 801 34
- 说明：索引步骤需要解包后的密封数据集；未提供时该步 skipped 且不计入 passed。三处配方问题的结论只针对 v2 主表，已归档的 P5 批次数据未重生成。
