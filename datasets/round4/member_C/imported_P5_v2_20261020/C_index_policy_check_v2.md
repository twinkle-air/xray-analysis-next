# P5 索引与划分策略 v2 自检

- 批次：C-recipes-v2 / C-recipes-v2(candidate)
- 数据集目录名：P5_dataset_v2（manifest.json SHA-256 `604cd6a07ca7857fd901073bc3a276210447fce4f41aa5a0af7b9ac6a4666f1f`）
- 主配方表：master_samples_v2.json（SHA-256 `78ca94780021c17915565d152cffb234976e2d007d796126d84cbf4ce3d1a9b3`）

## 断言

```json
{
  "rows": 2000,
  "uniform_holdout": true,
  "benchmark_split_values": {
    "heldout": 2000
  },
  "recipe_family_split_by_spectra": {
    "train": 1440,
    "validation": 260,
    "test": 300
  },
  "groups_crossing_recipe_split": [],
  "identical_compositions_crossing_split": [],
  "parent_families_crossing_split": [],
  "formula_replicates_split": [],
  "distinct_formula_compositions": 1000,
  "formulas": 1000,
  "duplicate_composition_groups": 0,
  "duplicate_groups_all_single_leak_group": true,
  "leak_groups": 680,
  "group_size_histogram": {
    "1": 600,
    "5": 80
  },
  "generator_split_untouched": {
    "test": 300,
    "train": 1400,
    "validation": 300
  },
  "sealed_manifest_split_seed": 20261102,
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
