> **D后续复核（2026-10-24）**：[PR #34](https://github.com/twinkle-air/xray-analysis-next/pull/34) 修复提交0935bd9已批准合并。成功日志与QC ZIP原件一致，两层manifest全部通过；50个ZIP及原核验数据未改变。D完成1716谱交付；B仍待其原PR修复。详细证据见 [D增量复核](D_PR34_rereview.json)。下文保留首轮Request changes的历史记录。

# 第三轮B/D全量交付审查（2026-10-24）

结论：两份PR均Request changes，暂不合并。修复交付/辅助脚本后复审，不要求重生成谱。

| PR | 固定审查head | 数量 | 结论 |
| --- | --- | ---: | --- |
| [B #35](https://github.com/twinkle-air/xray-analysis-next/pull/35#pullrequestreview-5638394051) | `6a7a945a5b15fad8d1cc642494d8da8a50589968` | 1500+246=1746，50批 | 清单README哈希/大小错误；续跑未验QC；PowerShell失败未传播；full_delivery入口不存在 |
| [D #34](https://github.com/twinkle-air/xray-analysis-next/pull/34#pullrequestreview-5638394197) | `50f8d3a234184b0becf4d17cc626dfdaceeb3b3e` | 1500+216=1716，48批 | 清单引用的successful_rerun.log未纳入Git；QC ZIP已有完全相同原件 |

四项核验：全部原生ZIP SHA/CRC、内部integrity、blind/full哈希；逐字段record_plan及配方组成、32标签/O基体、profile/噪声种子和整族用途；每批完整audit/all_records replay及命令/退出码、预注册窗外预算；生成器0.2.1/核心0.2.0和冻结输入身份。D的1716条不透明盲包也已核对每条哈希/格式/CRC。最大回放数组差均为成员报告的0.0，本负责人没有重复全库物理重算，不宣称独立复算或真实仪器准确度。

B故障注入：模拟已有sealed目录却无QC，Python续跑输出run=0 failed=0并正常返回；模拟PowerShell子进程返回23，脚本记录FAILED后仍能继续到调用后位置。未实际生产数据。仅编译PR中的Python源码并核对PowerShell语法，未执行发布脚本或访问成员环境。

修复任务已写回[B任务](../../../planning/B_任务清单.md)、[D任务](../../../planning/D_任务清单.md)。冻结配方/profile/种子/全局分组和物理核心不修改。C #33已有Request changes仍待修复；全员数据未合并完成，训练入库仍为false。
