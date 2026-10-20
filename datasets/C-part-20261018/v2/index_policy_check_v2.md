# P5 索引与划分策略 v2 自检

- 批次：C-part-20261018 / C-recipes-v1(review_failed,pilot_only)
- 数据集目录名：P5_dataset（manifest.json SHA-256 `d68f2f4f28c64f21816d0d63fb7a237056dcc643de80eedea94437ede8ea396c`）
- 主配方表：master_samples.json（SHA-256 `ff783d84c6a0cbe426ad777fec8700201e097ccf15bf9261274a348242435b05`）

## 断言

```json
{
  "rows": 2000,
  "uniform_holdout": true,
  "benchmark_split_values": {
    "heldout": 2000
  },
  "recipe_family_split_by_spectra": {
    "train": 1450,
    "test": 258,
    "validation": 292
  },
  "groups_crossing_recipe_split": [],
  "identical_compositions_crossing_split": [],
  "parent_families_crossing_split": [],
  "formula_replicates_split": [],
  "distinct_formula_compositions": 944,
  "formulas": 1000,
  "duplicate_composition_groups": 34,
  "duplicate_groups_all_single_leak_group": true,
  "leak_groups": 801,
  "group_size_histogram": {
    "1": 754,
    "2": 18,
    "5": 28,
    "70": 1
  },
  "generator_split_untouched": {
    "train": 1400,
    "validation": 292,
    "test": 308
  },
  "sealed_manifest_split_seed": 20261018,
  "passed": true
}
```

## 字段语义

| 字段 | v1 | v2 |
| --- | --- | --- |
| benchmark_split | train/validation/test（可被当训练集读） | **全部 heldout** |
| holdout_status | 无 | condition_heldout |
| usage_policy | 无 | pilot_only_isolated_from_training_and_tuning |
| recipe_family_split | —（原语义降级到此描述性字段） | 仅描述配方来源，禁止作基准划分 |
| leak_group | —（仅按 parent_family 划分） | 精确组成 ∪ parent_family ∪ 生成器族 的并查集分量 |

结论：**全部断言通过**
