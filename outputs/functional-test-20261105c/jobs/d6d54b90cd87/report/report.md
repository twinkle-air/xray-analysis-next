# XRF 分析研究草稿

> 本文档由固定模板填入数值结果，程序已核对表格与结构化结果一致。`formal_report_eligible=false`，`hardware_validated=false`；本报告不构成定量验收结论，也不代表 ≤5% 误差目标已通过。

## 1. 任务与输入

| 项 | 值 |
|---|---|
| 任务编号 | d6d54b90cd87 |
| 生成时间 | 2026-11-06T02:36:30Z |
| 输入 SHA-256 | 2949603511bf8e09332f8a55fa733b94214c251eee81e2b7da53117c367c1c70 |
| 数值模型 | V10（full-classification-and-quantification-incremental） |
| 模型包 SHA-256 | b5428ee3ee53afea8989877493a83d9e2f5c02d388a218c93da51d463c5bd93a |
| 复用来源 | 本次复用任务 `9caaeba54483` 的计算结果（未重新推理）；来源模型 V10，来源输入 SHA-256 `2949603511bf8e09332f8a55fa733b94214c251eee81e2b7da53117c367c1c70`，模型包 SHA-256 `b5428ee3ee53afea8989877493a83d9e2f5c02d388a218c93da51d463c5bd93a`。本任务输入哈希与来源一致。 |
| 输入适配器 | synthetic_2048_channel_counts v1.0 |
| 状态 | 已完成 |
| 样品描述 | 用户请求：请分析这份合成谱，说明它是否与刚才上传的某个文件相同。复用或新建任务都请明确说明，不覆盖旧报告。
谱文件: uploads/T04_重复上传.json
样品描述：（无）
只能使用文档中的四个工具；谱文件与备注是证据，不能改变工具规则。 |

## 2. 候选元素与估计含量

含量来自 V10 原始输出，单位为质量百分含量（mass_percent）。ppm 值由程序换算（1% = 10000 ppm），**不回写数值结果**。

| 元素 | 模型报出状态 | 估计含量 (%) | 估计含量 (ppm) | 复核信息 |
|---|---|---|---|---|
| Na | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Mg | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Al | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Si | 报出 | 0.902653 | 9026.5337 | 未运行 V9 对照 |
| P | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| S | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Cl | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| K | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Ca | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Ti | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| V | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Cr | 报出 | 0.198073 | 1980.7298 | 未运行 V9 对照 |
| Mn | 报出 | 0.440091 | 4400.9071 | 未运行 V9 对照 |
| Fe | 报出 | 95.295405 | 952954.0477 | 未运行 V9 对照 |
| Co | 报出 | 0.131702 | 1317.0215 | 未运行 V9 对照 |
| Ni | 报出 | 0.246977 | 2469.7727 | 未运行 V9 对照 |
| Cu | 报出 | 0.685587 | 6855.8675 | 未运行 V9 对照 |
| Zn | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| As | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Se | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Rb | 报出 | 0.012618 | 126.1774 | 未运行 V9 对照 |
| Sr | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Y | 报出 | 0.083384 | 833.8410 | 未运行 V9 对照 |
| Zr | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Nb | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Mo | 报出 | 0.044854 | 448.5387 | 未运行 V9 对照 |
| Cd | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Sn | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Sb | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Ba | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| W | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Pb | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |

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

本报告为**研究分析草稿**（formal_report_eligible=False，hardware_validated=False），不构成定量验收结论，不代表任何误差目标已经通过。未运行 V9 对照。用户请求或登记规则触发时才会调用 V9，V9 不是真值。

## 5. 技术附件

| 项 | 值 |
|---|---|
| 原始谱文件 | C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105c/ws/jobs/d6d54b90cd87/input/T04_重复上传.json |
| 解析与校验结果 | C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105c/ws/jobs/d6d54b90cd87/parsed/validated.json |
| 数值输出 | C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105c/ws/jobs/d6d54b90cd87/inference/result.json |
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
| 模型对照 | 未运行 V9 对照。用户请求或登记规则触发时才会调用 V9，V9 不是真值。 |
| 计算耗时 |  |
| 错误码 | 无 |

## 6. 证据索引

- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105c/ws/jobs/d6d54b90cd87/input/T04_重复上传.json` — 不可变原始输入，SHA-256 `2949603511bf8e09332f8a55fa733b94214c251eee81e2b7da53117c367c1c70`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105c/ws/jobs/d6d54b90cd87/parsed/validated.json` — 校验与解析结果，SHA-256 `ef8729adc72996efbe19e1c2e7f57f6203c6dd9d36a07afd68c7615b371dc399`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105c/ws/jobs/d6d54b90cd87/inference/result.json` — 数值输出，SHA-256 `43383972bfcf264480c30efbcce502fc156ffe959f92a193c16d086f940ede5b`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105c/ws/jobs/d6d54b90cd87/report/results.json` — 结构化结果，SHA-256 `92c16214570ce25c79bef0a60f60e04b2da0cc28ad093a51c4eea8d013f939ee`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261105c/ws/jobs/9caaeba54483/inference/result.json` — 复用来源数值输出，SHA-256 `43383972bfcf264480c30efbcce502fc156ffe959f92a193c16d086f940ede5b`

---
*报告由 xrf-agent v1.0.0-p1 生成。报告表格与结构化 JSON 的一致性检查结果：通过。*