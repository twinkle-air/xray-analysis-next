# 当前放行：owner release v3（2026-10-24）

owner 明确要求取消 B/C/D 分阶段试产，直接全量生产、自检、提交PR，之后统一审查。当前入口为 `owner_release_v3.json` 和 `../production_tools/run_member_full.ps1`；B/C/D分别1,746/1,686/1,716谱，含各自1,500基础谱与246/186/216留出T谱。

既有phase=pilot的90谱纳入全量基础谱，无需单独提交或等A放行。不更改freeze_v1、物理核心、用途、profile、种子或预算；不取消逐批全量audit/replay/窗口预算及ZIP SHA/CRC。T仅留出QC，训练入库仍未批准。A既有1752谱不重新生产。各成员完成后提交本人完整PR，由owner统一审查，再决定数据合并与后续任务。

v2及旧试片脚本保留历史身份；只允许A批量的旧规则已被v3替代。使用旧release会继续触发旧门禁，不应修改旧release绕过。
