# V9 / V10 模型交付

下载本目录的`xrf-models-v9-v10.zip`与同名`.sha256`，先校验SHA-256，再解压到独立目录。无需下载整个数据仓库。运行与输入说明见[运行包说明](运行包说明.md)。

```powershell
Get-FileHash ./xrf-models-v9-v10.zip -Algorithm SHA256
Expand-Archive ./xrf-models-v9-v10.zip -DestinationPath ./xrf-runtime
Set-Location ./xrf-runtime
python -m pip install -r requirements.txt
python -B verify_package.py --smoke
python -B run_model.py --model V10 --input examples/synthetic_blind.json --out result.json
```

`registry.json`给出入口、包哈希及拟议职责。没有修改现有智能体配置，也没有把本机默认V9切换为V10。包内必须保留完整目录结构，历史名称的计算组件属于V9/V10依赖，不发布独立V6。

验证包括源码编译、逐文件哈希、ZIP CRC、全新解压目录推理、异常输入及篡改拒绝、迁移／退役前后数值一致。见[evidence](evidence/)。汇总表保留V6历史指标仅用于证据追溯。

[智能体完整构建方案](../../docs/agent-construction-v1/完整构建方案.md)明确后续接口、报告、ABCD建议分工和分阶段验收。当前只支持合成研究输入；测试不是新独立盲测，不承诺真实仪器≤5%误差。
