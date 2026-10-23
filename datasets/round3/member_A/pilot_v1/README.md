# A 第三轮90谱试片（2026-10-24）

从已固定训练用途的1梯度族、1干扰族、1配对族、2常规族取15配方，按各族三个profile×2噪声形成90谱。它们计入A基础1,500谱，剩余基础1,410谱尚未生产。八个原生ZIP保留blind_inputs、truth、full_results、六分量/谱线/窗外账目、inputs/configs、manifest/integrity及生成器/依赖快照。

每批均用包内封存app.py实际完成完整audit、完整物理replay和pack（无--limit），90/90通过，最大数值数组差0；逐谱窗口预算通过，ZIP CRC和SHA-256通过。实际命令、环境、耗时与退出码位于reports；原生split忽略，以外置record_index中的整族用途为准。

archives/A_pilot_blind_only.zip只含90个opaque命名的原始通道计数文件和格式说明；不含配方、profile、种子、族或元素标签。隔离映射在record_index.csv，不能作为推理输入。

当前仅试片QC通过，不是完整A数据交付、训练入库、外部独立盲测或真实设备准确度验收。批量生产仍关闭；先评审公共输入、程序和试片证据，再版本化放行。
