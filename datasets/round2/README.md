# 第二轮工作区（round2）

状态：planning_only。尚无本轮冻结主表/权威索引、尚未生成本轮能谱，不能把文档或第一轮归档当可训练数据。

当前执行预算：1,000 独立配方（silicate_oxide 600、iron_rich_oxide 400）× P1/P2/P3 × 两次计数噪声，共 6,000 谱；名义训练/验证/新家族测试约 4,200/900/900。约 300 谱流程试产单独版本，峰值按十进制 10 GB 规划。
模型负责人避免预先接触测试组成：成员 A 设计开发 510、B 设计开发 340、D 独立设计受限测试 150（两类各 90/60），C 受限核查与分组。材料类别与人员编号不同。

- [10 GB 执行方案](planning/10GB训练集执行方案.md)
- [容量预算](planning/storage_budget.json)
- [四人任务包与发送说明](planning/tasks/README.md)
- [共同规则与命令](planning/tasks/00_共同规则与命令.md)
- [可转发给队友的四段消息](planning/tasks/给队友的四段消息.md)
- [成员 A](member_A/README.md)、[成员 B](member_B/README.md)、[成员 C](member_C/README.md)、[成员 D](member_D/README.md)
- [开发共享目录约定](shared/README.md)

目录只负责分轮，不代替用途/权限隔离。训练须显式绑定 round2 的已验收开发索引，不能递归加载 round1。
第二轮新测试主表、标签及 full_results 不提交全组可读仓库；由 D 在受限位置保管，冻结模型后再按协议复核/评分。
仓库 private 或名为 member_D 的目录都不构成组内访问隔离。这里只提交任务说明，没有配置新权限。
