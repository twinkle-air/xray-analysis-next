# 通用 X 射线谱分析智能体

面向 2048 道合成 X 射线能谱的证据驱动分析智能体：输入一张谱加一段样品描述，由 V10 主模型给出候选元素与质量百分比，按登记规则触发 V9 对照，最后输出 Markdown 研究草稿与结构化证据包。全流程只允许调用四个登记工具，每一步产物落盘可追溯。

## 目录

| 路径 | 内容 |
|---|---|
| `agent/` | 可运行代码：四工具入口、编排与宿主、注册表（`agent/registry/`） |
| `agent-workspace/` | P0 基线测量结果与调试探针脚本 |
| `verify_p1.py` / `verify_p2.py` / `verify_p3.py` | 自动化校验套件 |
| `jobs/` | 每个任务的产物：输入、解析、推理、对照、审计轨迹、报告 |
| `智能体构建情况与使用指南.md` | 构建状态、工具契约、核验结果与已知限制 |

## 快速开始

依赖 Python 3.12、numpy 2.4.6、scipy 1.17.1、xraylib 4.3.0（见指南 §1）。

```bash
python -m agent.cli agent \
  --task-file deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json \
  --sample-description "铝合金粉末，未知仪器"
```

四工具也可单独驱动：`analyze_spectrum`、`get_job_status`、`compare_models`、`export_report`，参数与返回值见 `agent/registry/tool_contracts.json` 与指南 §3。

多轮追问用 `--interactive`：会话记录当前谱、主任务与对照任务（`audit/session.json`），追问直接读取已有结果，不再重新推理；轨迹中每轮标注 `answer_source`（`model` / `program_fallback`）。真实宿主用 `--host-mode api` 加 `XRF_AGENT_LLM_*` 环境变量；请求/响应中可核验的模型标识是 `Sage-A1.5`。

## 边界

- `formal_report_eligible=false`、`hardware_validated=false`：报告是研究草稿，不构成定量验收结论，两版模型均未达到相对误差 ≤5% 目标。
- V9 不是真值，两版一致也可能共同偏误，不做平均或逐元素择优。
- 只接受 2048 道、`synthetic: true` 的计数 JSON；实测谱接入需单独验收。
- 其余限制见 [智能体构建情况与使用指南.md](智能体构建情况与使用指南.md) §8。
