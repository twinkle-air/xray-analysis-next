# 通用 X 射线谱分析智能体 v0.3.0（2026-10-31）

> 本目录是智能体首版的入库副本，位于 `xray-analysis-next` 仓库的 `agent/v0.3.0-20261031/`。
> 记录实际构建状态、调用方式与核验结果。它是对 [`docs/agent-construction-v1/完整构建方案.md`](../../docs/agent-construction-v1/完整构建方案.md)（方案 v1.1 单人版）的实施落地，不是新的方案设计。
>
> **本目录是自包含工作区**：`agent-workspace/` 是代码与校验脚本，`deliverables/` 放功能测试谱集与解压后的 V9/V10 模型包。模型权重不重复入库，按 §5 从 `models/v9-v10-20261030/` 解压。

## 1. 构建状态总览

| 项 | 值 |
|---|---|
| 版本 | v0.3.0-20261031（方案 v1.1 首版落地，入库于 `xray-analysis-next`） |
| 状态 | **全部 153 项自动化用例通过**（P1 72 + P2 36 + P3 45，2026-11-02 复跑） |
| 主后端 | V10（完整分类＋定量增量），默认 |
| 复核后端 | V9（联合强度定量＋谱支持诊断），按请求触发 |
| 语言／运行时 | Python 3.12，numpy 2.4.6 / scipy 1.17.1 / xraylib 4.3.0（见模型包 `requirements.txt`） |
| 宿主 | `local_simulation`（确定性本地路由，非真实模型）；预留 `api` 后端接口 |
| 源码 | `agent-workspace/agent/`，14 个 `.py` 文件，约 2,460 行 |
| 注册表 | `agent-workspace/agent/registry/`，4 份 JSON + 1 份提示词 + 1 份模板 |

**已交付（首版收束范围）：** 一个文件入口、V10 主分析、按需 V9 对照、一份研究报告＋证据包、真实大模型宿主接口、最薄交互界面。单线程、状态落本地文件。

**未交付（已明确暂缓）：** 多智能体、向量库、长记忆、批量并发、微服务、自动重训、自动门控、仪表盘、实测谱（`.pu` 等）接入。

## 2. 系统结构与职责边界

```
用户能谱 + 样品描述
      │
      ▼
┌─────────────────────┐   input_contract.py  五字段契约校验（axis/signal_unit/synthetic/x/counts）
│ 文件接入与输入校验   │   → 拒绝：多余字段、非整数、负值、道数≠2048、总计数≤0、路径穿越
└─────────┬───────────┘
          ▼
┌─────────────────────┐   job.py           不可变原文件只读 + 逐桶产物目录 + 自动清理 .tmp-*
│ 任务与状态管理       │   状态机：parsing → inference → comparison → exported / failed
└─────────┬───────────┘
          ▼
┌─────────────────────┐   runner.py        隔离子进程 + 采样工作集 + 超时 kill + 失败不发布
│ V10 隔离数值进程     │   registry.py      冻结版本/入口/元素集，提示词不能改写；完整性校验
└─────────┬───────────┘                    不重新算哈希"修复"失配
          │  成功
          ▼
┌─────────────────────┐   tools.py         四工具入口；失败返回结构化 status=failed + error_code
│ 工具调度             │   error_codes.json 10 个登记错误码（HTTP 风格 400/404/409/500/504）
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ 是否触发对照？       │   review_rules.json  R01 用户请求 / R02 报出≤2 元素 / R03 主分析失败
│ review_decision     │   证据必须来自工具实际返回，语言模型不能编造触发条件
└───────┬─────┬───────┘
        │是   │否
        ▼     ▼
┌─────────────┐   ┌─────────────────┐
│ V9 独立进程  │   │                 │
│ compare_    │   │ reporting.py    │  六段式 Markdown + 程序化表格↔JSON 一致性检查
│ models      │   │                 │  ppm = % × 10000，只换单位不回写结果
└──────┬──────┘   └────────┬────────┘
       │                   │
       └─────────┬─────────┘
                 ▼
┌─────────────────────┐   report_template.md  固定模板；formal_report_eligible=false
│ 研究报告与证据包     │   hardware_validated=false
└─────────────────────┘   报告不构成定量验收结论
```

### 数据流向（一次完整请求）

1. `analyze_spectrum` → 校验 → 锁 V10 → 跑子进程 → 写 `jobs/<id>/inference/result.json`
2. `review_decision` 查登记规则 → 需要则 `compare_models`（V9 独立任务，不覆盖 V10）
3. `export_report` → 先跑一致性检查 → 写 `report.md` + `result.json`
4. 每一轮宿主往返记作 trajectory 的一 `turn`，全程可追溯

## 3. 四工具契约（`tool_contracts.json`）

| 工具 | 必填参数 | 返回值要点 | 备注 |
|---|---|---|---|
| `analyze_spectrum` | `task_file`（绝对路径） | `job_id`, `status`, `input_sha256`, `model_version`, `model_package_sha256`, `warnings`, `error_code`, `elapsed_s` | 校验失败也创建 job 以便追踪；不覆盖已有结果 |
| `get_job_status` | `job_id` | `stage`, `stage_elapsed_s`, `error_code`, `artifact_refs`, `exists` | 未知 job 只返回 `exists: false`，**不枚举/读取其他目录** |
| `compare_models` | `job_id` | `v9_job_id`, `n_reported_v10/v9`, `differing_elements[]`, `note` | 同一输入最多跑一次 V9；不平均、不挑值、不把 V9 当真值 |
| `export_report` | `job_id`, `include_comparison` | `markdown`, `json_path`, `markdown_path`, `consistency_check` | `include_comparison=true` 要求一次已完成的对照 |

`additionalProperties: false` —— 宿主不得发明契约外的参数。

## 4. 宿主与意图路由（`host.py`）

宿主只负责"下一步调用哪个登记工具"并解释工具返回的证据；**不能改模型版本、不能改输入契约、不能编谱**。

后端二选一（环境变量 `XRF_AGENT_LLM_HOST`）：

- `local_simulation`（默认）：确定性路由，不读谱、不跑模型、不写内容。所有使用它的轨迹都带 `simulated: true`，**不作为真实模型调用呈现**。
- `api`：需 `XRF_AGENT_LLM_API_BASE`、`XRF_AGENT_LLM_API_KEY`、`XRF_AGENT_LLM_MODEL`。

### 路由规则

| 当前对话状态 | 下一步 |
|---|---|
| 已跑过对照且用户未提新要求 | `export_report`（`include_comparison=true`） |
| 用户说"导出/报告" 且 主分析成功 | `export_report` |
| 用户说"对照/V9/差异复核" 且 主分析成功 | `compare_models` |
| 谱文件已给、尚无工具跑过 | `analyze_spectrum` |
| 以上都不是 | 拒绝，提示上传五字段 JSON |

### 2026-10-31 修复

上一版路由扫描**整段对话历史**，导致用户一旦说过"请导出报告"，后续所有追问（含"请跑一次 V9 对照"）都永远命中导出分支。已改为：

- `_last_user_text()` 只取**最新一条真实用户提问**，跳过宿主转发的工具结果回声（`报告导出返回。` / `V9 对照返回。`）。
- `_compare_completed` 只把"最后一次明确要求对照**之后**跑出的 `compare_models`"算作已完成。这顺带修掉一个隐患：若 R02（报出≤2 元素）在 turn 2 自动触发了对照，后续的"V9 对照"请求不会被误判为"已完成"。

修正后 thin 界面五轮走通：`analyze → export → export（用户要报告）→ compare（用户要对照）→ export（用户再要报告）`，共用一条 trajectory 与一个 job id。

## 5. 环境与安装

以下命令都在本目录（`agent/v0.3.0-20261031/`）下执行。

```powershell
# 1. 解压 V9/V10 模型包（仓库已带 ZIP，不重复入库权重）
#    Windows PowerShell:
Expand-Archive ..\..\models\v9-v10-20261030\xrf-models-v9-v10.zip -DestinationPath deliverables\xrf-models-v9-v10-20261030
#    Linux / macOS / Git Bash:
# unzip -q ../../models/v9-v10-20261030/xrf-models-v9-v10.zip -d deliverables/xrf-models-v9-v10-20261030

# 2. 准备数值环境（模型包自带 requirements.txt）
cd deliverables\xrf-models-v9-v10-20261030
python -m pip install -r requirements.txt
python -B verify_package.py --smoke      # 预期: {"status": "pass", "files_checked": 189, ...}
cd ..\..

# 3. 智能体本身无额外依赖，复用同一解释器；调用时必须把 agent-workspace 放进 PYTHONPATH
set PYTHONPATH=%CD%\agent-workspace
```

**路径约定**（不要改）：

- 本目录（`agent/v0.3.0-20261031/`）就是工作区根
- `agent-workspace/` 含 `agent/` 包 + `verify_common.py` / `verify_p1.py` / `verify_p2.py` / `verify_p3.py`
- `jobs/` 是任务产物目录（可安全清空重建，已被 `.gitignore` 忽略）
- `deliverables/智能体功能测试谱集-20261031/` 是功能测试谱集
- `deliverables/xrf-models-v9-v10-20261030/` 由 §5 第 1 步从仓库 `models/` 解压得到

> ⚠️ `agent.cli` 是模块入口，`python -m agent.cli` 与 §6 的 `-c` 形式**都能用**，唯一前提是 `agent-workspace` 必须在 `PYTHONPATH` 内（或 cwd 本身就是 `agent-workspace`）；否则一律报 `ModuleNotFoundError: No module named 'agent'`。三套 `verify_p*.py` 正是靠 `PYTHONPATH` 运行 `python -m agent.cli` 的。调用前务必先设好 `PYTHONPATH`。

## 6. 使用指南

### 6.1 单工具调用（可独立审计，不需要 LLM）

```powershell
# 分析一张谱（跑 V10）
python -m agent.cli analyze --task-file "deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json" --sample-description "铝合金粉末"

# 查一个任务
python -m agent.cli status --job-id "<job_id>"

# 对已有 V10 任务跑 V9 对照
python -m agent.cli compare --job-id "<job_id>"

# 导出报告（含对照）
python -m agent.cli export --job-id "<job_id>" --include-comparison
```

每个子命令返回纯 JSON 到 stdout，便于脚本串联与独立核验。

等价的 `-c` 写法（不依赖 `-m` 的模块解析）：

```powershell
python -c "import sys, agent.cli; sys.argv=['agent.cli','analyze','--task-file','deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json','--sample-description','铝合金粉末']"
```

### 6.2 自然语言编排（宿主 + 四工具）

```powershell
python -m agent.cli agent --task-file "deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json" --query "请分析这张谱" --sample-description "铝合金粉末"
```

返回 JSON 含 `status` / `job_id` / `markdown` / `json_path` / `markdown_path` / `trajectory_ref` / `review_decision` / `host_config`。

常用变体：

| 参数 | 含义 |
|---|---|
| `--query` | 自然语言请求，默认"请分析这张谱" |
| `--compare` | 显式请求 V9 对照（触发 R01） |
| `--no-export` | 分析/对照后停，不写报告 |
| `--interactive` | 对同一张谱连续追问 |
| `--once` | 只跑第一回合 |
| `--host-mode api` | 切换到真实 API 宿主（需配三个环境变量） |

### 6.3 最薄交互界面（连续对话）

```powershell
python -m agent.cli agent --task-file "deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json" --sample-description "铝合金粉末" --interactive
```

**每一问都是重新编排**，有自己的轨迹与 job id，不跨回合恢复状态——这是设计选择，避免代理"记住"它其实没记住的东西。空行 / `q` / `exit` 退出。

程序化追加追问（不经过 REPL）：

```python
from agent.orchestrator import follow_up
from agent.core.paths import Workspace
follow = follow_up(agent_root, "请跑一次 V9 对照", job_id, Workspace(workspace_root))
# 返回: status / job_id / tool_calls_executed / markdown / markdown_path / consistency_check
```

### 6.4 推荐测试流程（T01–T06）

见 `deliverables/智能体功能测试谱集-20261031/先看这里.md`，要点：

1. 依次上传 T01 / T02 / T03 → 正常分析
2. 上传 T04（与 T01 逐字节相同）→ 检查预测一致、不覆盖旧报告
3. 上传 T05（全零计数）、T06（2047 道）→ 检查拒绝，无伪成功报告
4. 回到 T01 任务 → 请求 V9 对照 → 追问 ppm 换算
5. 对照 `03_验收参考/任务清单.csv`、原始参考 JSON、`参考含量表.csv`

> `03_验收参考` 是评估材料，**不是**上传谱；参考含量属于模型输出，不是模拟配方真值。

## 7. 核验结果

### 自动化套件（全部 PASS）

| 套件 | 覆盖 | 通过 |
|---|---|---|
| `verify_p1.py` | T01–T06 数值闭环：V10 锁定、32 元素值与参考一致（rtol=1e-9/atol=1e-10）、输入 SHA-256、V9 对照、差异元素与 abs_diff_ppm、报告导出（含对照）、被篡改的去重缓存不采信、超大计数结构性拒绝、未知 job 不枚举、临时目录清理 | **72 项** |
| `verify_p2.py` | 宿主接入：H01 自然语言上传、H02 用户请求对照一次调用、H03 恶意备注存入但不执行、H04 失败输入无报告、R01/R02/R03 规则、宿主后端选择、API 客户端契约（无真实网络） | **36 项** |
| `verify_p3.py` | E05 多余字段拒绝且点名、E06 完整性失配报告不重算哈希（含处理依赖）、E07 超时 kill 整个进程树无产物、E08 路径穿越/缺失/目录拒绝、空 jobs/ 完整链路、thin 界面五轮、F05/F06 对照写入报告且等值不误报、工具拒绝未声明参数 | **45 项** |

### 关键行为断言（已验证）

- 报出状态："未报出"≠0 含量≠元素不存在，报告里渲染为"本模型未报出"
- 两版结果各自保留独立 job id，V9 任务 `version=="V9"`
- ppm = % × 10000，由程序换算，不回写数值结果
- 一致性检查逐格比对 Markdown 表格与结构化 JSON
- E07：`run_model` 给定 0.2 s 超时即返回 `TIMEOUT`，子进程树（含孙进程）被 kill，不发布产物，`.tmp-*` 暂存目录清除（墙钟 < 10 s）
- 未知 host 模式（`--host-mode unknown`）在交互模式下仍返回 rc=2 + `UNSUPPORTED_HOST`
- 去重缓存命中前逐项核对 model_version / adapter / 模型包 SHA-256 / 输入 SHA-256 / 产物 SHA-256，任何一项不符或结果损坏都重算，不沿用旧值
- 报告先在私有暂存目录生成，一致性检查通过后才原子发布；失败时不留下半成品

### 2026-11-01 修复

- **ppm 单位纠偏**：对照结果的 `abs_diff_pp` 更名为 `abs_diff_ppm`（值本来就是 `% × 10000`），契约、报告与校验脚本同步。
- **V9 等值误报**：报告改读对照里的完整 `v9_predicted_element_percent`，不再只依赖 `differing_elements`，因此两版相等的元素显示 V9 值而不是"V9 未报出"。
- **缓存可信性**：去重命中改为校验式复用，坏缓存（含被改写数值）直接丢弃重算。
- **输入上界**：counts 增加 2^53−1 结构性上限，超大整数返回 `INVALID_COUNTS` 而不是让下游数学溢出。
- **进程清理**：Windows 上用 Job Object 绑定数值子进程树，超时/失败时整棵树一起终止，避免孙进程残留。
- **参数面收敛**：工具执行器按 `tool_contracts.json` 拒绝未声明参数（`CONTRACT_VIOLATION`），不再依赖提示词约束；移除调试日志旁路。

### 2026-11-02 修复

- **依赖完整性**：`verify_package` 除 `local_files` 外同时校验 `freeze.json` 的 `processing_dependencies`（V9 运行包）。此前缓存命中不会执行入口自检，依赖被换掉也可能沿用旧结果；旧格式（裸 `files` 映射）按原样兼容。
- **进程树终止修正**：`JOBOBJECT_BASIC_LIMIT_INFORMATION` 的字段顺序写错（`JobSet` 按指针、`Affinity` 按 DWORD），结构体实际变成 72 字节，后续字段被截断，`KILL_ON_JOB_CLOSE` 可能未生效。按 MSDN 布局改回 64 字节后，超时终止覆盖整棵进程树。
- **证据清单收敛**：报告第 6 节不再包含报告自身哈希（自引用永远无法收敛），`evidence_manifest.json` 在发布后按最终文件重新生成；发布仍是「暂存 → 校验 → 原子替换」。
- **E06 用例修正**：完整性测试拷贝 V10 包时一并补齐 V9 依赖，避免因缺依赖而误判，只测被篡改的目标文件。
- **发布失败处理**：`evidence_manifest.json` 写入失败时不再删除已发布的 JSON/Markdown
  （一次失败的重建不该抹掉上一份报告），改为抛 `ReportError`，暂存目录始终清理。
- **进程终止兜底**：`CreateJobObjectW` / `OpenProcess` / `AssignProcessToJobObject` 任一失败
  都用 `taskkill /T /F` 终止整棵进程树；`JOBOBJECT_BASIC_LIMIT_INFORMATION` 按 x64 真实布局
  重排为 64 字节，`LimitFlags` 之后的字段不再错位。
- **R03 探针**：`probe_r03.py` 注入 `QueryInformationJobObject` / `OpenProcess` /
  `AssignProcessToJobObject` 失败，另加无注入的对照用例，断言必须报错、暂存目录清理、
  孙进程不存活；探针在系统临时目录里使用替身入口，不改动冻结模型包。

## 8. 入库范围与仓库位置

本目录是 `xray-analysis-next` 仓库内的独立版本目录（`agent/v0.3.0-20261031/`），按该仓库 [CONTRIBUTING.md](../../CONTRIBUTING.md) 经任务分支与 PR 提交，**不直接推送 main**。

**入库内容：**
- `agent-workspace/agent/`、`agent-workspace/verify_*.py` 与 `agent-workspace/probe_r03.py`：当前可运行的代码与本机校验脚本。
- `deliverables/智能体功能测试谱集-20261031/`：6 个功能测试输入、3 份评估参考与说明，共约 300 KB。
- `README.md`（本文件）与 `.gitignore`。

**未入库：**
- V9/V10 权重与运行包（82 MB）已在仓库 `models/v9-v10-20261030/` 单独发布，按 §5 解压复用，不重复入库。
- `jobs/`、`__pycache__/`、`.venv/`、`outputs/` 等任务产物、缓存与本地环境，已由 `.gitignore` 忽略。
- 无密钥、账号信息、私人实测谱或模型会话。

**版本独立性：** 本版是方案 v1.1 的全新实现，自成一套代码与产物，不依赖任何历史版本目录。

### 已知限制（不掩盖）

1. **两版模型均未达到相对误差 ≤5% 目标**，`formal_report_eligible=false`、`hardware_validated=false`；演示不能表述为定量标准已通过。
2. **V9 不是真值**。两版一致也可能共同偏误；不做自动平均、逐元素择优或模型投票。
3. **当前只支持 2048 道合成原始计数 JSON**（`synthetic: true`）。不能把实测谱改标为 `synthetic=true` 绕过检查；实测谱接入需单独验收。
4. **`local_simulation` 不是真实模型**，只做路由。切换真实宿主前需配齐三个 `XRF_AGENT_LLM_*` 环境变量并实测。
5. 氧及其他未建模基体不补算，不强制归一到 100%。
6. T01–T06 只覆盖正常/对照/重复/输入拒绝/报告功能，不替代超时、取消、路径权限、安全审计与完整实测定量验收。

## 9. 快速对账命令

```powershell
# 0. 进入本目录并设好 PYTHONPATH（见 §5）
cd agent\v0.3.0-20261031
set PYTHONPATH=%CD%\agent-workspace

# 1. 模型包自检（需先按 §5 解压）
cd deliverables\xrf-models-v9-v10-20261030
python -B verify_package.py --smoke
cd ..\..

# 2. 全部回归（从本目录运行，约 3–5 分钟）
python agent-workspace\verify_p1.py
python agent-workspace\verify_p2.py
python agent-workspace\verify_p3.py

# 3. 单张谱端到端
python -m agent.cli agent --task-file "deliverables/智能体功能测试谱集-20261031/01_正常输入/T01.json" --sample-description "铝合金粉末" --interactive --once
```

预期三套套件末尾均输出 `ALL CASES PASSED`；模型包自检输出 `{"status": "pass", ...}`。

> 校验脚本会自动设定 `PYTHONUTF8=1` 并在启动时清理只读残留，可在中文 Windows 上连续重复运行。