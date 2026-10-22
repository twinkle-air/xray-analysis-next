# 第三轮公共输入准备 v1（未生产冻结）

已登记420个设计族的四人分配、9开发/3留出完整配置与哈希，并完成24次固定探针数值检查。P1/P2/P3逐字节继承第二轮A；D/T是工程压力假设，没有实测标定。未生成训练谱，未执行90谱试片。

- [设计分配](design_allocation.json) · [条件及角色](profile_registry.json)
- [源与环境](source_identity.json) · [窗口预算](window_budget.json)
- [固定探针输入](numeric_probe_inputs.json) · [24项数值结果](profile_numeric_checks.json)
- [文件哈希](preparation_manifest.json)

development_profiles只包含P1/P2/P3/D1～D6；heldout_profiles_qc_only中的T1/T2/T3禁止用于训练、校正、响应字典或选参。目录分离不是自动强制隔离；模型侧白名单/禁入适配尚未完成。420个design_seed是候选设计种子，不是已冻结的噪声子种子。

窗口预算在24次探针计算前写入；它是工程拦截阈值，不保证定量性能。完整候选的窗口复核、全局划分、每族条件匹配、长曝光覆盖、噪声种子、90谱试片及最终数量仍待完成。本目录的manifest不是生产批准书。
