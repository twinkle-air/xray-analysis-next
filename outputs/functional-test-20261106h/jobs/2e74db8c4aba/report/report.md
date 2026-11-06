# XRF 分析研究草稿

> 本文档由固定模板填入数值结果，程序已核对表格与结构化结果一致。`formal_report_eligible=false`，`hardware_validated=false`；本报告不构成定量验收结论，也不代表 ≤5% 误差目标已通过。

## 1. 任务与输入

| 项 | 值 |
|---|---|
| 任务编号 | 2e74db8c4aba |
| 生成时间 | 2026-11-06T03:47:33Z |
| 输入 SHA-256 | 44e12591244085bebe1791635becc2692773e120fcb0a3fc1ff4e6851cbd5716 |
| 数值模型 | V10（full-classification-and-quantification-incremental） |
| 模型包 SHA-256 | b5428ee3ee53afea8989877493a83d9e2f5c02d388a218c93da51d463c5bd93a |
| 复用来源 | 本次独立运行数值模型，未复用旧任务。 |
| 输入适配器 | synthetic_2048_channel_counts v1.0 |
| 状态 | 已完成 |
| 样品描述 | 功能测试用的合成原始计数谱，无样品描述 |

## 2. 候选元素与估计含量

含量来自 V10 原始输出，单位为质量百分含量（mass_percent）。ppm 值由程序换算（1% = 10000 ppm），**不回写数值结果**。

| 元素 | 模型报出状态 | 估计含量 (%) | 估计含量 (ppm) | 复核信息 |
|---|---|---|---|---|
| Na | 报出 | 1.639997 | 16399.9727 | 未运行 V9 对照 |
| Mg | 报出 | 2.278588 | 22785.8822 | 未运行 V9 对照 |
| Al | 报出 | 4.092100 | 40920.9968 | 未运行 V9 对照 |
| Si | 报出 | 21.555563 | 215555.6306 | 未运行 V9 对照 |
| P | 报出 | 0.479054 | 4790.5366 | 未运行 V9 对照 |
| S | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Cl | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| K | 报出 | 2.190495 | 21904.9490 | 未运行 V9 对照 |
| Ca | 报出 | 10.862650 | 108626.5019 | 未运行 V9 对照 |
| Ti | 报出 | 2.171812 | 21718.1241 | 未运行 V9 对照 |
| V | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Cr | 报出 | 0.843120 | 8431.1997 | 未运行 V9 对照 |
| Mn | 报出 | 0.181854 | 1818.5425 | 未运行 V9 对照 |
| Fe | 报出 | 6.257600 | 62576.0029 | 未运行 V9 对照 |
| Co | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Ni | 报出 | 1.109939 | 11099.3907 | 未运行 V9 对照 |
| Cu | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Zn | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| As | 报出 | 0.043966 | 439.6638 | 未运行 V9 对照 |
| Se | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Rb | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Sr | 报出 | 0.013453 | 134.5297 | 未运行 V9 对照 |
| Y | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Zr | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Nb | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
| Mo | 未报出 | 本模型未报出 | 本模型未报出 | 未运行 V9 对照 |
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
  "gain": 0.013999819234416339,
  "zero": 0.5500802444254324,
  "old_gain": 0.013999819234416339,
  "old_zero": 0.5500802444254324,
  "chosen": 0,
  "candidate_count": 3,
  "old_deviance": 1046.7965141658879,
  "deviance": 1046.7965141658879,
  "cost_gap_per_count": 0.0026500609941936103
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
| 原始谱文件 | C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261106h/ws/jobs/2e74db8c4aba/input/T02.json |
| 解析与校验结果 | C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261106h/ws/jobs/2e74db8c4aba/parsed/validated.json |
| 数值输出 | C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261106h/ws/jobs/2e74db8c4aba/inference/result.json |
| 刻度诊断 | {
  "gain": 0.013999819234416339,
  "zero": 0.5500802444254324,
  "old_gain": 0.013999819234416339,
  "old_zero": 0.5500802444254324,
  "chosen": 0,
  "candidate_count": 3,
  "old_deviance": 1046.7965141658879,
  "deviance": 1046.7965141658879,
  "cost_gap_per_count": 0.0026500609941936103
} |
| 模型对照 | 未运行 V9 对照。用户请求或登记规则触发时才会调用 V9，V9 不是真值。 |
| 计算耗时 | 22.712604600000304 |
| 错误码 | 无 |

## 6. 证据索引

- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261106h/ws/jobs/2e74db8c4aba/input/T02.json` — 不可变原始输入，SHA-256 `44e12591244085bebe1791635becc2692773e120fcb0a3fc1ff4e6851cbd5716`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261106h/ws/jobs/2e74db8c4aba/parsed/validated.json` — 校验与解析结果，SHA-256 `ddc0c65ef9ed0c3868e93a9d99a87f63c3d5b92287ed8aa24bda3648dce32e5f`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261106h/ws/jobs/2e74db8c4aba/inference/result.json` — 数值输出，SHA-256 `7a6265e018956d9052838d76ac21ed975ae7cbc99a4e33eb0b1cbd32038065a6`
- `C:/Users/Twinkle/AppData/Local/Temp/xrf-func-test-20261106h/ws/jobs/2e74db8c4aba/report/results.json` — 结构化结果，SHA-256 `14a7bfdfb3ad09af8278aaba72632ce3dcaa585dae41d14ee93479cf9a2d2ea7`

---
*报告由 xrf-agent v1.0.0-p1 生成。报告表格与结构化 JSON 的一致性检查结果：通过。*