# 通用 X 射线谱分析智能体 v0.3.1（2026-11-06）

> v0.3.0（2026-10-31）的延续版本。本目录是自包含工作区：`agent/` 是代码，`verify_p*.py` 是校验脚本，
> `deliverables/` 放功能测试谱集；V9/V10 冻结模型包不重复入库，按 §5 从
> `models/v9-v10-20261030/` 解压到 `deliverables/xrf-models-v9-v10-20261030/`。
> 相比 v0.3.0 的 `agent-workspace/` 嵌套布局，本版改为扁平布局，本目录即工作区根，
> 快速开始中的命令可以直接运行。

## 1. 构建状态总览

| 项 | 值 |
|---|---|
| 版本 | v0.3.1-20261106 |
| 状态 | **153 项自动化用例通过**（P1 72 + P2 36 + P3 45，UTF-8 由启动入口内置，不再依赖手工环境变量） |
| 主后端 | V10（完整分类＋定量增量），默认 |
| 复核后端 | V9（联合强度定量＋谱支持诊断），按请求触发 |
| 语言／运行时 | Python 3.12，numpy 2.4.6 / scipy 1.17.1 / xraylib 4.3.0 |
| 宿主 | `local_simulation`（确定性本地路由，默认）；`api` 后端已用真实 **Sage-A1.5** 验证 |
| 源码 | `agent/`，15 个 `.py` 文件（v0.3.0 为 14 个，新增 `session.py`） |
| 注册表 | `agent/registry/`，4 份 JSON + 1 份提示词 + 1 份模板 |

真实宿主复测（Sage-A1.5）：T01 四轮连续会话（分析 → ppm 追问 → V9 对照 → 未报出含义）通过；
T02/T03 正常分析通过且数值与冻结参考逐字节一致；T05/T06 被正确拒绝且无成功报告。

## 2. 相对 v0.3.0 的变更

- **会话上下文**：新增 `agent/session.py`，交互模式记录当前谱、主任务与对照任务，追问不再重新整条编排。
- **`follow_up()` 接通**：追问注入已有结果摘要；拒绝再次调用 `analyze_spectrum`；工具执行后把结果回传宿主，由宿主生成中文结论。
- **回答来源可追溯**：每轮轨迹与 `audit/session.json` 记录 `answer_source`（`model` 或 `program_fallback`）及兜底原因；对照轮为混合执行（宿主调用 `compare_models`，程序补齐报告导出）时区分明确。
- **复用来源可见**：CLI 摘要与报告“复用来源”行写明来源任务、模型版本、输入哈希与模型包哈希。
- **UTF-8 启动入口**：CLI 启动时统一设置 stdio／控制台编码，中文提示、报告与管道输入不再需要手工 `PYTHONUTF8`。
- **真实宿主路径修复**：历史重放去除重复 `system` 消息（曾导致 Sage 端 HTTP 400）；提示词中的谱文件路径解析为工作区绝对路径，避免宿主改写相对路径。

## 3. 目录结构

| 路径 | 内容 |
|---|---|
| `agent/` | 可运行代码：四工具、`session.py`、`orchestrator.py`、`host.py`、注册表 |
| `verify_p1.py` / `verify_p2.py` / `verify_p3.py` / `verify_common.py` | 自动化校验套件 |
| `deliverables/智能体功能测试谱集-20261031/` | 功能测试谱集（T01–T06）与验收参考 |
| `deliverables/xrf-models-v9-v10-20261030/` | 解压后的冻结模型包（不入库，按 §5 解压） |

## 4. 快速开始

在本目录运行（Python 需含 numpy/scipy/xraylib，见 §5）：

```bash
python -m agent.cli agent \
  --task-file deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json \
  --sample-description "铝合金粉末，未知仪器"
```

四工具也可单独驱动：`analyze`、`status`、`compare`、`export`；参数与返回值见
`agent/registry/tool_contracts.json`。多轮追问用 `--interactive`，
会话记录写入任务目录 `audit/session.json`，工具轨迹写入 `audit/trajectory.json`。

真实宿主运行（密钥只放进程环境变量，不要写入文件或聊天）：

```bash
XRF_AGENT_LLM_HOST=api XRF_AGENT_LLM_API_BASE=https://discovery-api.intern-ai.org.cn \
XRF_AGENT_LLM_API_KEY=*** XRF_AGENT_LLM_MODEL=Sage-A1.5 \
python -m agent.cli agent --interactive --host-mode api --task-file .../T01.json
```

## 5. 解压模型包

```bash
python -m pip install -r deliverables/xrf-models-v9-v10-20261030/requirements.txt
unzip models/v9-v10-20261030/<模型包>.zip -d deliverables/xrf-models-v9-v10-20261030/
```

完整性由 `agent/registry/model_registry.json` 与模型包内 `freeze.json` 在每次分析前校验。

## 6. 模型名称口径

请求与响应中可核验的模型标识是 **Sage-A1.5**（`XRF_AGENT_LLM_MODEL` 与轨迹
`host_config.model`）。文中“书生 S2”指服务方对该产品序列的称呼，发布材料统一以
API 可核验的 `Sage-A1.5` 为准，避免混用。

## 7. 边界与限制

- `formal_report_eligible=false`、`hardware_validated=false`：报告是研究草稿，不构成定量验收结论。
- V9 不是真值，两版一致也可能共同偏误，不做平均或逐元素择优。
- 只接受 2048 道、`synthetic: true` 的计数 JSON；实测谱接入需单独验收。
- 真实宿主复测覆盖 T01–T06；超出该范围的超时、取消、路径权限、安全与完整实测定量验收仍需另行执行。
