# C 部分配方设计 v2 自检报告

设计脚本：`scripts/design_c_alloy_formulas_v2.py`；输出：`v2/master_samples_v2.json`（SHA-256 见 `design_selfcheck_v2.json` 的 `master_file.sha256`）。
已密封的 P5 批次与 v1 脚本未被修改；本报告只读地对 v1 主表复算了问题数字。

> 本表比较的是 **v1 主表** 与 **v2 主表**。已归档的 P5 批次（2000 谱）仍由 v1 主表生成，其数据本身的问题没有在本批内改变；“已消除”只指 v2 主表按同一断言复算后的结果。

## 逐条对账（评审结论 → v2 状态）

| 评审发现 | v1 实测（本脚本复算） | v2 实测 | 结论 |
| --- | --- | --- | --- |
| P2-1 独立组成不足 | 944/1000，重复组 34 | **1000/1000，重复组 0** | 已消除 |
| P2-3 越出自身声明范围 | 891 行 / 1750 项（{'regular_variation': 548, 'sparse_boundary': 200, 'interference_control': 143}） | **0 行 / 0 项** | 已消除 |
| P2-2 干扰对照写死 Ni=8、Fe 参与对照 | 40 族均受影响 | 含 Fe 的干扰对：无；背景覆盖目标：无；逐变体存在性/背景/比值断言通过 | 已消除 |
| 场景配额 600/200/200 | 600/200/200 | {'regular_variation': 600, 'sparse_boundary': 200, 'interference_control': 200} | 达标 |
| Fe 基体与 100% 闭合 | — | Fe 区间 [55.0, 99.99999]，闭合非 100 的行 0 | 达标 |
| 元素覆盖 | — | 从未出现的元素：无 | 达标 |

## 断言明细

```json
{
  "rows": 1000,
  "scenario_counts": {
    "regular_variation": 600,
    "sparse_boundary": 200,
    "interference_control": 200
  },
  "quota_met": true,
  "distinct_compositions": 1000,
  "distinct_equals_rows": true,
  "duplicate_groups": 0,
  "rows_with_range_violations": 0,
  "range_violation_items": 0,
  "examples_of_violations": {},
  "closure_not_100": [],
  "fe_min_max": [
    55.0,
    99.99999
  ],
  "all_rows_have_iron_matrix": true,
  "interference_rows": 200,
  "interference_families": 40,
  "interference_family_has_5_variants": true,
  "interference_pairs": [
    "As/Pb",
    "Co/Cu",
    "Co/Ni",
    "Co/Ti",
    "Cr/Mn",
    "Cr/Mo",
    "Cr/Ni",
    "Cu/Ni",
    "Mn/Cu",
    "Mo/W",
    "Ni/Mn",
    "Pb/Sb",
    "Sb/Sn",
    "Se/Ba",
    "Sr/Rb",
    "Ti/Al",
    "V/Nb",
    "W/Nb",
    "Y/Zr",
    "Zn/Cd"
  ],
  "interference_pairs_containing_Fe": [],
  "interference_variant_counts": {
    "only_Cr": 6,
    "only_Mn": 6,
    "equal": 40,
    "ratio_1_5": 40,
    "ratio_5_1": 40,
    "only_Co": 6,
    "only_Ni": 8,
    "only_Cu": 6,
    "only_Ti": 4,
    "only_Mo": 4,
    "only_W": 4,
    "only_V": 2,
    "only_Nb": 4,
    "only_Al": 2,
    "only_As": 2,
    "only_Pb": 4,
    "only_Sb": 4,
    "only_Sn": 2,
    "only_Zn": 2,
    "only_Cd": 2,
    "only_Se": 2,
    "only_Ba": 2,
    "only_Y": 2,
    "only_Zr": 2,
    "only_Sr": 2,
    "only_Rb": 2
  },
  "interference_background_overlaps_target": [],
  "sparse_targets": 20,
  "low_recipes_per_target_min": 5,
  "zero_recipes_per_target_min": 5,
  "zero_recipe_target_actually_absent": true,
  "elements_never_present": [],
  "zero_element_mentions": 12908,
  "passed": true,
  "master_file": {
    "name": "master_samples_v2.json",
    "bytes": 2963316,
    "sha256": "78ca94780021c17915565d152cffb234976e2d007d796126d84cbf4ce3d1a9b3",
    "v1_master_used": {
      "name": "master_samples.json",
      "bytes": 2080020,
      "sha256": "ff783d84c6a0cbe426ad777fec8700201e097ccf15bf9261274a348242435b05"
    }
  }
}
```

## 元素出现次数（采用组成中出现即计数）

{"Fe": 1000, "Sb": 638, "Pb": 635, "Ba": 632, "Cd": 632, "Sn": 632, "As": 629, "Zn": 627, "Zr": 627, "Sr": 626, "Y": 625, "Rb": 623, "Se": 621, "Ni": 483, "Mn": 441, "Cr": 425, "Mo": 421, "Cu": 416, "Co": 401, "Al": 343, "Si": 297, "Ti": 273, "V": 272, "C": 262, "Nb": 258, "W": 253}

## 结论

**全部断言通过，可进入下一步（划分/索引重写后再启动生成）**
