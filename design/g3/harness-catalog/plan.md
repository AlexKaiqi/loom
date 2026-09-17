# harness 示例：plan（阶段推进与下一阶段投影）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

把工作分成阶段；**完成一个阶段，就把下一阶段投影进上下文**，直到计划走完。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `plan.created{plan_id, stages[]}`；`plan.revised{plan_id, rev, diff_ref}`；`plan.stage.started{stage_id}`；`plan.stage.completed{stage_id, evidence_refs[]}`；`plan.completed{plan_id}` |
| 产生者 | 创建/修订 = 外部或模型经受理；阶段推进 = harness 声明 |
| 触发与受理 | `plan.stage.completed` → 开一轮并投影下一阶段；`plan.completed` → `rounds` 停止开轮；修订只追加 |
| 投影 | **只投影当前阶段 + 紧邻下一阶段**（有界）；全 plan 给指针；已完成的阶段只给结论 |
| 逻辑 | 阶段门控（完成条件、证据要求）、顺序约束、修订处理 |

## 通用原语映射

P1 声明｜P2 受理｜P3 触发｜P4 投影（有界）｜P5 逻辑｜P6 身份（`plan_id`/`stage_id`/`rev`）。

## 边界与反例

- **spec 与 state 分开**：`stages[]` 定义可以是 `content/` 文件（版本引用）；**当前阶段是事件**（§4.4）。
- plan **不调度**：推进由 `rounds` 的触发条件决定，plan 逻辑只回答"阶段算不算完成"。
- 反例：把 plan 做成 runtime 调度器；把全 plan 塞进上下文；阶段完成只看模型自述；用 `derived/` 存阶段状态。

## 框架缺口

**无。** 需要的只是"有界投影"和"事件触发"，两者都在通用原语内。
