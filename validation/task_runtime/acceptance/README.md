# 独立验收（2026-09-16）

范围：任务目录 runtime（`lore_task/`）与 9 个 harness 场景的真实模型验证证据。

角色与方法（先声明，后填结果）：

| 角色 | 承担者 | 独立性 |
|---|---|---|
| 实现者 | 实现会话（本仓库工作区） | — |
| 验收 A（契约与证据核对） | 独立 Agent（新上下文，未参与实现） | 部分：同机、同工作区、由实现会话派出 |
| 验收 B（对抗性复跑与证伪） | 独立 Agent（新上下文，未参与实现） | 部分：同机、同工作区、由实现会话派出 |

锁定契约：`design/g3/task-runtime-contract.md`、`design/g3/task-directory-landing.md`。
报告：`independent-acceptance-A.md`、`independent-acceptance-B.md`（由验收者本人撰写）。
证据：`../evidence/ark-*`（真实模型运行）、`../offline_*.py`（无网络用例）、`../verify_*.py`（独立校验器）。

已知局限（不因验收而消除）：校验者与实现者同机同工作区、由实现会话启动，**不是第三方独立机构**；`Workspace` 只有路由与记账，**不是隔离**（X 沙箱未接）；并发/单写者租约与任意切点崩溃注入未验证。
