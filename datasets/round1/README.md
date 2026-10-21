# 第一轮交付归档（round1）

| 原目录 | 本轮归档位置 |
| --- | --- |
| datasets/A-part-20261018 | [A-part-20261018](A-part-20261018/README.md) |
| datasets/B-part | [B-part](B-part/README.md) |
| datasets/C-part-20261018 | [C-part-20261018](C-part-20261018/README.md) |

本次只改变三个目录的上级位置，目录内部原件逐字节保留：配方、源脚本、README、报告、manifest/integrity、ZIP/分卷与原哈希清单均未改写。
A/B 原始谱仍是 workflow_pilot_only；C 仍保留 review_failed / workflow_pilot_only 的历史身份。第一轮本地研究模型的许可/研究侧车不自动改变这些原始包的用途。

原目录内记载的旧绝对/仓库路径是历史证据，不随搬迁批量替换。按 path_migration.json 将外部路径前缀映射到新位置；不能为了修路径重写封存文件及哈希清单。
ZIP 内部布局和独立 audit/replay 用法未变。复现历史设计/打包脚本时，应在独立恢复工作区重建其原来要求的目录布局/生成器位置，再执行源码快照；不能假定所有旧脚本在增加一层目录后可直接从新位置运行。不要在活动 datasets 根目录重新创建一套旧数据副本。

第二轮从 [../round2/README.md](../round2/README.md) 进入，禁止按旧 generator_split 直接加载整个归档作为本轮训练。
