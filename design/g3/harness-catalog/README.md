# harness 示例集（harness-catalog）

地位：**示例集，不是框架标准点**，不表示任何能力通过；全部 UNVERIFIED。
目的（用户 2026-09-16 提议）：一种 harness 一个文件，讨论它**如何只用框架通用原语定义**。定义不出来的地方，就是**通用原语缺口**——回补原语，**不加领域目录**（"宁缺毋滥"）。
相关：[../task-directory-landing.md](../task-directory-landing.md) §4.3–4.7（五件套、P1–P8 原语、manifest 解析、信息项/投影/呈现）。

## 统一模板

1. **场景**：一句话。
2. **五件套**：词表 + 契约 / 产生者 / 触发与受理 / 投影 / 逻辑。
3. **通用原语映射**：用到 P1–P8 的哪些。
4. **边界与反例**：明确不许变成什么。
5. **框架缺口**：只记"缺哪个**通用**原语"；不得写"需要一个 `xxx/` 目录"。

## 规则

- 只用框架通用原语；**不得为本示例新增框架目录或字段**。
- 示例是**能力**，不是框架知识；框架不因示例知道 goal / plan / archive。
- 新示例：先在下面索引加一行，再写文件。

## 索引

| 文件 | 场景 | 结构上考什么 | 框架缺口 |
|---|---|---|---|
| [goal.md](goal.md) | 目标 + 完成 + 验收 | 完成声明 ≠ 终态 ≠ 验收 | 无 |
| [plan.md](plan.md) | 阶段推进与下一阶段投影 | spec vs state、有界投影 | 无 |
| [archive.md](archive.md) | 上下文控制（归档/折叠） | 观测事实触发组织轮、无损 vs 有损 | 规范观测目录（`sys.*`）细化 |
| [ask-user.md](ask-user.md) | 向人提问并等待 | 出站通知 + 入站受理 + 零驻留等待 | 对外通知/投递原语 |
| [coding.md](coding.md) | 改代码 / 跑测试 / 迭代 | 工具结果归 Session、双域、Workspace 版本 | `tools/` 落点（§4.1 待裁决） |
| [research.md](research.md) | 检索与素材沉淀 | recall 成本与"恢复不重放" | 模型辅助召回契约 |
| [delegation.md](delegation.md) | 跨任务委派 | 关系 + 授权 + 事件受理 | 跨任务授权查询语义 |
| [monitoring.md](monitoring.md) | 条件/定时监视 | 长等待、零驻留、触发 | 定时/时钟观测与等待责任 |
| [system-design.md](system-design.md) | 自顶向下系统设计 | 局部修改、冻结/修订、单调收敛 | 条件受理（base_rev）、冻结与修订、失效传播 |
| [voice-assistant.md](voice-assistant.md) | 实时语音助手（流式听/说、双工、可换语音模型） | 实时设施与事件任务面的接缝、流式产出、二进制 artifact | 对外投递、流式观测通道、媒体 artifact 通用化、实时会话设施归属 |

## 待写（宁缺毋滥，一次一个）

computer-use（浏览器/桌面）、review / critic（独立评审）、reflection / memory（记忆整理）、A/B shadow（多策略对比）、data-pipeline（批处理）、support-ticket（工单）、multimodal-input（图像输入）、verification-harness（验收执行）、retrieval-index（索引维护）。
