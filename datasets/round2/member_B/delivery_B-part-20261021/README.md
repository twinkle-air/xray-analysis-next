# 第二轮成员 B：完整 ZIP 交付

本目录无损传输完整的 B-part-20261021 文件夹（4,809 个文件，1,911,776,872 字节）。ZIP 为 665,548,698 字节，SHA-256：510cff2947e18e8b3dccf39a383d187ae62834174fef2551f7ac2e570800c55d。因上传限制，将 ZIP 拆为 80 个 8 MiB 分块；分块不是谱，不应递归加载。

在本目录运行（仅需 Python 标准库）：

```powershell
python -B restore_transport.py
python -B restore_transport.py --extract
```

脚本逐块校验 SHA-256，恢复 ZIP 后检查全部 CRC；加 --extract 后恢复文件夹并按 source_manifest.json 核验每个原始文件 SHA-256。冲突文件不会被覆盖。transport_manifest.json 列出全部分块及哈希。

本批为用户授权的 **B 本地暂定**：250 配方、P1/P2/P3 各 500 谱，共 1,500 谱；30 个封存批次自行全量 audit/replay 通过，最大数组差异 0。使用 A 封存 profile 与 B 独立种子；全局冻结、协调人纳入、合库分组和训练放行仍待确认。完整报告、命令、环境和原始证据均在恢复后的目录中。
