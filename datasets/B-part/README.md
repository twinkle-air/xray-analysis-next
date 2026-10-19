# 成员 B 交付正文 —— 仓库镜像状态（指针，非正文）

- 权威正文：本机 `datasets/B-part/README.md`，33,319 字节，SHA-256 `8af130b421ff55cb275eb1f0fd43d6ff295367a6771d307ae41891bdff86dd91`（同一摘要也记录在已镜像的 `B_delivery_hashes.json` 中）。
- 本机 `README.md` 内容未被改动；本文件只覆盖 GitHub 上的镜像副本。

## 为什么正文此刻不在仓库里

1. 本机 `github.com:443` 可 TCP 连接但 TLS/HTTP 不通，`git push` 与 `git ls-remote` 均失败（exit 128）；唯一可用通道是 `api.github.com`（GitHub MCP 的 Contents API）。
2. 该通道要求把文件内容逐字符写进调用参数。首次镜像 `README.md` 时正文出现 15 行转录错误（第 13、54、85、118、124、130、138、215、225、235、240、249、269、287、293 行），已核对：仓库里存的字节与我写出的字节一致（blob SHA-1 `70bc455dfc47f0cb79d9a482f2c0d103e1b40e07`），误差来自书写环节，不是 GitHub。其中一处把「稀疏/边界」写成「常规/边界」，属实质性错误。
3. 因此缺陷副本已撤回，不再作为交付正文引用。它仍留在历史 commit `66acd81be88484c5ddaa19b526e4dff3b1da7357` 中，仅供审计，**不得**据此复核。

## 已在 main 且逐字节校验通过（8 个文件）

校验方法：对本地交付字节做 LF 归一化后计算 `sha1("blob %d\0" + bytes)`，与 Contents API 返回的 `sha` 比对，全部相等；长度亦相等。注意仓库副本是 LF，而 `B_delivery_hashes.json` 里登记的权威摘要针对本机 CRLF 字节，两者不同属预期，不是不符。

- `P3_candidate.json`、`P4_candidate.json`、`B_design_ranges.json`
- `pilot_P3_v1_pack.zip.sha256`、`pilot_P4_v1_pack.zip.sha256`
- `B_M1_status.json`、`B_pilot_family_exposure.csv`（含 3 字节 UTF-8 BOM，已按原样保留）
- `B_delivery_hashes.json`
- 另有 `work/pilot_ledger.json`（逐阶段命令与退出码台账）同样校验通过。

## 尚未镜像，需由能连通 github.com 的环境用 git 或网页上传

| 本机路径（相对 `datasets/B-part/`） | 字节 | SHA-256 前 12 位（全值见 `B_delivery_hashes.json`） |
| --- | --- | --- |
| `README.md`（权威正文） | 33,319 | `8af130b421ff` |
| `B_delivery_status.json` | 26,077 | `0abea6f7e47d` |
| `B_samples.json` | 11,893,487 | `214ac617e74c` |
| `B_pilot_samples.json` | 807,612 | `ed3c26bc86c9` |
| `B_formula_registry.csv` | 339,969 | `f292e5bc4f31` |
| `pilot_P3_v1_pack.zip` | 42,228,605 | `50c82cc4e136` |
| `pilot_P4_v1_pack.zip` | 46,111,903 | `d585a87fb08e` |

密封目录 `pilot_P3_v1/`、`pilot_P4_v1/` 与隔离环境 `work/venv313/` 不上传；前两者的搬运载体就是上面两个 ZIP，其外部 SHA-256 已在 main 上。

## 复核口径不变

`passed` 只用于本机实际跑完、报告已落盘、结论由报告字段导出的项目；本交付仍是单人自检，不是 A 对 B 的交叉复核，也不是 C 的主审。P4 试产未通过自设 1 % 窗口损失预算（70/200），该失败保留在 `work/pilot_reports/pilot_P4_v1/verification_v3.json`；M1 状态仍为 `M1_pending_profile`。
