# XRF 分析研究草稿

> 本文档由固定模板填入数值结果，程序已核对表格与结构化结果一致。`formal_report_eligible=false`，`hardware_validated=false`；本报告不构成定量验收结论，也不代表 ≤5% 误差目标已通过。

## 1. 任务与输入

| 项 | 值 |
|---|---|
| 任务编号 | {job_id} |
| 生成时间 | {created_at} |
| 输入 SHA-256 | {input_sha256} |
| 数值模型 | {model_version}（{model_revision}） |
| 模型包 SHA-256 | {model_package_sha256} |
| 输入适配器 | {adapter_name} v{adapter_version} |
| 状态 | {status} |
| 样品描述 | {sample_description} |

## 2. 候选元素与估计含量

含量来自 {model_version} 原始输出，单位为质量百分含量（mass_percent）。ppm 值由程序换算（1% = 10000 ppm），**不回写数值结果**。

| 元素 | 模型报出状态 | 估计含量 (%) | 估计含量 (ppm) | 复核信息 |
|---|---|---|---|---|
{elements_table}

> 报出状态说明："报出"指模型在该元素的分类概率 ≥ 0.9 且给出非零含量；"未报出"指本模型未报出，**不等于含量为零，也不等于该元素不存在**。

## 3. 诊断与限制

{diagnostics}

### 3.1 必须说明的限制

{limitations}

### 3.2 建议补充的信息

{supplementary_info_needed}

## 4. 解释与复核建议

{analyst_note}

## 5. 技术附件

| 项 | 值 |
|---|---|
| 原始谱文件 | {input_ref} |
| 解析与校验结果 | {parsed_ref} |
| 数值输出 | {inference_ref} |
| 刻度诊断 | {axis_diagnostics} |
| 模型对照 | {comparison_note} |
| 计算耗时 | {elapsed_s} |
| 错误码 | {error_code} |

## 6. 证据索引

{evidence_index}

---
*报告由 {tool_name} v{tool_version} 生成。报告表格与结构化 JSON 的一致性检查结果：{consistency_check}。*