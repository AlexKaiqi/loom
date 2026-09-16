# 设计与执行资产导航

阅读顺序是目标、性质、抽象、用例、实现和证据。源码快照的最新进展见 [验证状态](validation-status.md)；G1/G2 等历史文档中的“当前”指当时阶段。

| 问题 | 入口 |
| --- | --- |
| 系统解决什么问题 | [v5 设计](../harness-runtime-revised-v5.md)、[完整目标](../GOAL.md) |
| 原始要求是否有覆盖 | [需求矩阵](../design/requirements-matrix.md)、[逐条需求](../design/requirements/) |
| 如何划分职责与事实归属 | [顶层契约](../design/g1/top-level-contracts.md)、[因果论证](../design/g1/causal-arguments.md) |
| 为什么选择这些机制 | [方案比较](../design/g1/alternatives-review.md)、[机制决策](../design/g1/mechanism-decisions.md)、[研究综合](../design/g2/synthesis.md) |
| 开源定向调研 | [调研清单](../harness-runtime-open-source-research-list.md)（§11 执行编排与沙箱底座增补、§12 Cursor 产品参照）、[执行平台调研记录](../design/g2/execution-platforms-survey-2026-09-15.md)（OpenHands v1.18.0 / SWE-agent v1.1.0 / AutoCodeRover v1.1.0 / E2B / Daytona v0.190.0）、[Cursor Cloud Agent 参照](../design/g2/cursor-cloud-agent-reference-2026-09-15.md)、[借鉴取舍评估](../design/g2/adoption-assessment-2026-09-15.md)（A 立即/B 近期/C 后置/D 不采纳） |
| 如何独立验证组件 | [G3 组件契约和用例](../design/g3/)、[验证程序](../validation/components/) |
| 执行后端接缝与沙箱环境扩展如何预留 | [X 后端接缝与环境扩展](../design/g3/x/backend-seam.md)（判断记录，非契约修订）、[M06 浏览器沙箱环境契约](../design/g3/system/m06-browser-environment.md)（已立项，未运行） |
| 系统如何验收 | [系统契约](../design/g3/system/)、[验收映射](../governance/runtime-acceptance-map.md)、[系统验证程序](../validation/system/) |
| 如何避免长任务妥协与漂移 | [检查表](../governance/checklists.md)、[执行指南](../governance/execution-guide.md)、[证据指南](../governance/evidence-guide.md)、[记录模板](../governance/templates.md) |

当前落地的主要边界：R 用 SQLite 保存受理和推进责任，E 使用 NATS JetStream，F 使用 Git，X 使用 Docker，S 适配 Pi。Runtime 组合这些组件；业务终态由 Harness 给出，Runtime 不根据业务文件内容自行宣布完成。

这些原则和判断是版本化资产。历史研究中的候选实现不等于当前代码依赖；例如早期 R 的 Node SQLite 候选已经与现有 Python SQLite 实现不同。当前依赖事实以 [依赖说明](dependencies.md)及源码为准。

公开整理保留原组件接口与产品源码；省略了开发机的原始证据、准备快照和部分仅用于绑定原件的索引，因此历史记录中指向这些原件的引用在公开仓库不一定可解析。不要将缺失引用视为通过，也不要直接沿用旧机器的哈希/物理身份清单作为新环境证据。
