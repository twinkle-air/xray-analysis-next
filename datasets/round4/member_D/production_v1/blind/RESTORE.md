# 仅盲样本导出分片

`D_round4_blind_inputs.zip` 共 160,410,944 字节，超过 GitHub 单文件 100 MB 硬限且本仓库未启用 Git LFS，
因此按每片约 40,102,736 字节拆成 4 片随仓库交付；分片内容互不重叠，顺序拼接即还原原包。

```bash
cat D_round4_blind_inputs.zip.part01 D_round4_blind_inputs.zip.part02 D_round4_blind_inputs.zip.part03 D_round4_blind_inputs.zip.part04 > /tmp/D_round4_blind_inputs.zip
sha256sum -c D_round4_blind_inputs.zip.sha256            # 期望 cbd82cb4894fedc429a80e732c4fb7aa91abcacf8daea753d25a434b1fc612df
unzip -t /tmp/D_round4_blind_inputs.zip                  # CRC 全部通过
unzip -l /tmp/D_round4_blind_inputs.zip | tail -1        # 20000 个 opaque 条目
```

分片自身哈希见 `PARTS.sha256`；整包另可由 200 个原生归档经冻结 runner 的打包步骤逐字节复现。
包内仅含 `axis`、`counts`、`signal_unit`、`synthetic`、`x`，不含成员、元素、浓度、族、条件或种子标签。

本次交付已在本地完成还原校验：拼接后 SHA-256 与固定值一致，ZIP 内部 CRC 通过，条目数 20,000。
