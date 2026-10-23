# 第三轮 B：正式试片交接

四方候选已通过已知历史范围内的全局检查，PR #28已合并。固定输入见 `shared/freeze_v1`；owner_release_v2只批准你先做90谱试片，**不批准批量生产**。你的最终基础谱1,500条、内部留出配方41个、追加T谱246条，最终总数1746条；90谱计入基础谱，不能另加。

同步包含本次release的分支/PR后，在仓库根目录、具有numpy/scipy/xraylib及封存生成器依赖的Python环境运行：

```powershell
powershell -NoProfile -File datasets/round3/shared/production_tools/run_member_pilot.ps1 -Member B -Python python
```

逐批确切参数见 `member_B_pilot_commands.json`。底板族、profile、全部计数种子来自已冻结表；不自由jitter、不换种子凑数量、不向sealed目录追加，已有目录会拒绝覆盖。控制器每批都实际执行生成、窗外预算、完整audit、完整物理replay与pack，不传--limit。任何失败都保留原始输出/日志并停止，不放宽窗外预算或删难谱。

提交：全部原生无损ZIP及其.sha256、完整audit/replay/window_budget JSON与终端日志、commands/environment、external_record_index和实际耗时/体积；大文件只传ZIP并核对SHA/CRC，不上传展开谱目录。A只复核数量/版本、哈希、自检证据、全局分组；正常情况下不再替你重做所有物理replay。

通过本人90谱试片并由A复核后，A才发布允许你批量的下一个release；当前程序会拒绝你的base/challenge批次。T只供内部留出物理QC，不能进入训练/字典/校正/选参；未记录历史亲缘不能排除，仍不称外部独立盲测或真实设备精度验收。
