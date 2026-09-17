# harness 示例：goal（目标 + 完成 + 验收）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

外部给出目标与验收条件；harness 推进，直到给出"完成"声明；**验收由外部独立检查**。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `task.objective.set{objective_ref, acceptance_refs[]}`；`task.phase.changed{goal_id, from, to, rev}`；`task.completed{goal_id, evidence_refs[]}`；`task.blocked{reason_ref}` |
| 产生者 | `objective.set` = 外部受理；`phase.changed` / `completed` / `blocked` = harness 声明 |
| 触发与受理 | `objective.set` → 开第一轮；`completed` → `rounds` 不再开轮；`blocked` → 默认不开轮（等外部）；受理按契约校验、幂等去重 |
| 投影 | 当前 objective + phase + **验收清单** + 证据指针（给指针不灌全文） |
| 逻辑 | phase 状态机；验收引用解析；"完成"只做声明，不自行判定业务成功 |

## 通用原语映射

P1 声明（kinds/契约）｜P2 受理｜P3 触发｜P4 投影｜P5 逻辑｜P6 身份（`goal_id` + `rev`）｜P7 可选观测（预算/时间）。

## 边界与反例

- `task.completed` 是 **harness 声明的事件**，不是 runtime 通用终态（v5:161,208）。
- **"完成" ≠ 不活**：任务仍在册，直到管理动作 Archive。
- **完成声明 ≠ 业务验收**：验收在 V/外部（GOAL §4）。
- 反例：runtime 合成终态；把模型最终回答当完成；完成即自动 Archive；把 `goal_id` 编进目录名。

## 框架缺口

**无。** 这条本身就是结论：goal 不需要任何新框架目录，只需要声明 + 受理 + 触发 + 投影 + 逻辑。
