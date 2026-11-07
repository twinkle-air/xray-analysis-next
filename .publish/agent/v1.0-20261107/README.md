# 通用 X 射线谱分析智能体 V1.0

面向 2048 道合成 X 射线能谱的证据驱动分析智能体：输入一张谱加一段样品描述，由 V10 主模型给出候选元素与质量百分比，按登记规则触发 V9 对照，最后输出 Markdown 研究草稿与结构化证据包。全流程只允许调用四个登记工具，每一步产物落盘可追溯。

## 当前版本

对外名称：**V1.0**；机器版本号：`1.0.0`。本次为现有成品版本统一命名，承接原 v0.4.0 已合并改进；V10/V9 数值模型、报告组件 `1.1.0` 与报告结构 `1.0` 分别保留。

当前源码入口为仓库根目录 `agent/`，发布快照为 `.publish/agent/v1.0-20261107/`。旧 `.publish/agent/v0.3.1-20261106/` 及旧日志保留历史标识，不作为当前发布入口。解压完整配套包后在 `XRF作品提交包` 根目录执行命令，需保留其 `deliverables/` 冻结模型与示例。

## 目录

| 路径 | 内容 |
|---|---|
| `agent/` | 可运行代码：四工具入口、编排与宿主、注册表（`agent/registry/`） |
| `agent-workspace/` | P0 基线测量结果与调试探针脚本 |
| `verify_p1.py` / `verify_p2.py` / `verify_p3.py` | 自动化校验套件 |
| `jobs/` | 每个任务的产物：输入、解析、推理、对照、审计轨迹、报告 |
| `智能体构建情况与使用指南.md` | 构建状态、工具契约、核验结果与已知限制 |

## 快速开始

依赖 Python ≥ 3.12.14、numpy 2.4.6、scipy 1.17.1、xraylib 4.3.0（见指南 §1 与 §5）。

```bash
python -m agent.cli agent \
  --task-file deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json \
  --sample-description "合金合成计数谱，原始计数"
```

每次分析前会先核验**实际运行模型子进程的解释器**（不是父进程）是否满足 `agent/registry/runtime_policy.json` 声明的版本策略，并把指纹写进任务状态、JSON 与报告；环境不符时按 `RUNTIME_MISMATCH` 拒绝运行（不留静默回退），依赖缺失按 `DEPENDENCY_MISSING` 拒绝。需要临时放行时只能用 `--allow-unverified-runtime`（唯一入口，结果如实标记为未验证）。跨环境的旧结果不会复用：去重键已绑定运行环境指纹。

四工具也可单独驱动：`analyze_spectrum`、`get_job_status`、`compare_models`、`export_report`，参数与返回值见 `agent/registry/tool_contracts.json` 与指南 §3。

多轮追问用 `--interactive`：会话记录当前谱、主任务与对照任务（`audit/session.json`），追问直接读取已有结果，不再重新推理；轨迹中每轮标注 `answer_source`（`model` / `program_fallback`）。真实宿主用 `--host-mode api` 加 `XRF_AGENT_LLM_*` 环境变量；请求/响应中可核验的模型标识是 `Sage-A1.5`。

## 边界

- `formal_report_eligible=false`、`hardware_validated=false`：报告是研究草稿，不构成定量验收结论，两版模型均未达到相对误差 ≤5% 目标。
- V9 不是真值，两版一致也可能共同偏误，不做平均或逐元素择优；对照策略集中写在报告第 7 节，规则取自 `agent/registry/comparison_policy.json`。
- 只接受 2048 道、`synthetic: true` 的计数 JSON；拒绝原因以中文 `user_message` 给出（保留机器码与英文调试信息），实测谱接入需单独验收。
- 其余限制见 [智能体构建情况与使用指南.md](智能体构建情况与使用指南.md) §8。
