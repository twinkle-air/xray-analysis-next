# XRF 分析研究草稿

> 本文档由固定模板填入数值结果，程序已核对表格与结构化结果一致。`formal_report_eligible=false`，`hardware_validated=false`；本报告不构成定量验收结论，也不代表 ≤5% 误差目标已通过。

## 1. 任务与输入

| 项 | 值 |
|---|---|
| 任务编号 | e8a2807e9a6c |
| 生成时间 | 2026-11-06T03:09:19Z |
| 输入 SHA-256 | 2949603511bf8e09332f8a55fa733b94214c251eee81e2b7da53117c367c1c70 |
| 数值模型 | V10（full-classification-and-quantification-incremental） |
| 模型包 SHA-256 | b5428ee3ee53afea8989877493a83d9e2f5c02d388a218c93da51d463c5bd93a |
| 复用来源 | 本次独立运行数值模型，未复用旧任务。 |
| 输入适配器 | synthetic_2048_channel_counts v1.0 |
| 状态 | 已完成 |
| 样品描述 | 用户提交的功能测试用合成原始计数谱（无额外样品描述） |

## 2. 候选元素与估计含量

含量来自 V10 原始输出，单位为质量百分含量（mass_percent）。ppm 值由程序换算（1% = 10000 ppm），**不回写数值结果**。

| 元素 | 模型报出状态 | 估计含量 (%) | 估计含量 (ppm) | 复核信息 |
|---|---|---|---|---|
| Na | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Mg | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Al | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Si | 报出 | 0.902653 | 9026.5337 | V9=1.158298%，差 2556.45 ppm |
| P | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| S | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Cl | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| K | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Ca | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Ti | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| V | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Cr | 报出 | 0.198073 | 1980.7298 | V9=0.167876%，差 301.97 ppm |
| Mn | 报出 | 0.440091 | 4400.9071 | V9=0.334640%，差 1054.50 ppm |
| Fe | 报出 | 95.295405 | 952954.0477 | V9=54.479219%，差 408161.86 ppm |
| Co | 报出 | 0.131702 | 1317.0215 | V9=0.019984%，差 1117.18 ppm |
| Ni | 报出 | 0.246977 | 2469.7727 | V9=0.137378%，差 1095.99 ppm |
| Cu | 报出 | 0.685587 | 6855.8675 | V9=0.141481%，差 5441.06 ppm |
| Zn | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| As | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Se | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Rb | 报出 | 0.012618 | 126.1774 | V9=0.008157%，差 44.61 ppm |
| Sr | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Y | 报出 | 0.083384 | 833.8410 | V9=0.054834%，差 285.50 ppm |
| Zr | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Nb | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Mo | 报出 | 0.044854 | 448.5387 | V9=0.018003%，差 268.51 ppm |
| Cd | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Sn | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Sb | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Ba | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| W | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |
| Pb | 未报出 | 本模型未报出 | 本模型未报出 | V9=本模型未报出%，差 0.00 ppm |

> 报出状态说明："报出"指模型在该元素的分类概率 ≥ 0.9 且给出非零含量；"未报出"指本模型未报出，**不等于含量为零，也不等于该元素不存在**。

## 3. 诊断与限制

```
{
  "gain": 0.013999917738977866,
  "zero": 0.5501444009915506,
  "old_gain": 0.013999917738977866,
  "old_zero": 0.5501444009915506,
  "chosen": 0,
  "candidate_count": 3,
  "old_deviance": 1105.1803200465497,
  "deviance": 1105.1803200465497,
  "cost_gap_per_count": 0.0028800641829520948
}
```

### 3.1 必须说明的限制

- 32 个元素含量之和**不归一化为 100%**，差额不自动填成氧。
- 分类概率是分类器原始输出，未经独立校准，不能写成“该含量有 90% 准确率”。
- 模型未报出**不等于含量为零，也不等于该元素不存在**。
- This model is not validated for measured spectra, unknown instrument gain/zero, or non-2048-channel inputs.

### 3.2 建议补充的信息

- 真实仪器的能量刻度（gain / zero）与响应函数
- 样品基体与几何条件（粉末 / 块状、测量距离、气氛、测量时间）
- 可追溯成分标样，用于区分合成研究结果与实测准确度

## 4. 解释与复核建议

本报告为**研究分析草稿**（formal_report_eligible=False，hardware_validated=False），不构成定量验收结论，不代表任何误差目标已经通过。V9 对照已完成，关联主任务 `e8a2807e9a6c`，对照任务 `9f994d29e427`。V10 报出 10 个元素，V9 报出 10 个元素；10 个元素两版含量不同。

## 5. 技术附件

| 项 | 值 |
|---|---|
| 原始谱文件 | C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105g/ws/jobs/e8a2807e9a6c/input/T01.json |
| 解析与校验结果 | C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105g/ws/jobs/e8a2807e9a6c/parsed/validated.json |
| 数值输出 | C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105g/ws/jobs/e8a2807e9a6c/inference/result.json |
| 刻度诊断 | {
  "gain": 0.013999917738977866,
  "zero": 0.5501444009915506,
  "old_gain": 0.013999917738977866,
  "old_zero": 0.5501444009915506,
  "chosen": 0,
  "candidate_count": 3,
  "old_deviance": 1105.1803200465497,
  "deviance": 1105.1803200465497,
  "cost_gap_per_count": 0.0028800641829520948
} |
| 模型对照 | V9 对照已完成，关联主任务 `e8a2807e9a6c`，对照任务 `9f994d29e427`。V10 报出 10 个元素，V9 报出 10 个元素；10 个元素两版含量不同。 |
| 计算耗时 | 7.687585799999852 |
| 错误码 | 无 |

## 6. 证据索引

- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105g/ws/jobs/e8a2807e9a6c/input/T01.json` — 不可变原始输入，SHA-256 `2949603511bf8e09332f8a55fa733b94214c251eee81e2b7da53117c367c1c70`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105g/ws/jobs/e8a2807e9a6c/parsed/validated.json` — 校验与解析结果，SHA-256 `cde0e23f5a792ae0df90b82f3d7e53d31a0b310fea10694f40ce380944041181`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105g/ws/jobs/e8a2807e9a6c/inference/result.json` — 数值输出，SHA-256 `43383972bfcf264480c30efbcce502fc156ffe959f92a193c16d086f940ede5b`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105g/ws/jobs/e8a2807e9a6c/inference/comparison.json` — V9 对照输出，SHA-256 `6830cee00a27ada3f3dce8645508eab2207ccafb78ef114a6be9567bf6415630`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105g/ws/jobs/e8a2807e9a6c/report/results.json` — 结构化结果，SHA-256 `593970b869c0f4f84af02eb3deceb661f983e48fd5a343c363c10ae5e14aa0f1`

---
*报告由 xrf-agent v1.0.0-p1 生成。报告表格与结构化 JSON 的一致性检查结果：通过。*