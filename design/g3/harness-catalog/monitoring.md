# harness 示例：monitoring（条件/定时监视）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

长期盯一个条件（时间点、外部状态、其他工作的事实），满足时行动；期间工作**不占资源**。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `monitor.condition.set{monitor_id, predicate_ref, deadline?}`；`monitor.condition.met{monitor_id, fact_ref}`；`monitor.condition.expired{monitor_id}`；`sys.time.*`（若框架提供定时观测，如 `sys.time.due{at}`） |
| 产生者 | `monitor.*` = harness 声明；`sys.time.*` / 外部事件 = **runtime 观测 / 外部受理** |
| 触发与受理 | 条件满足的事实落面后由 **Trigger Condition** 求值开轮；同一事实只开一轮；截止到点 → `expired` 路径 |
| 投影 | 监视目标 + 当前条件求值状态 + 最近观测 |
| 逻辑 | 条件谓词由 runtime 按声明求值；截止分级；重复/漏通知的核对 |

## 通用原语映射

P1 声明｜P2 受理｜P3 触发（承重）｜P4 投影｜P5 逻辑｜P6 身份（`monitor_id`）｜P7 观测（定时）。

## 边界与反例

- **等待期工作专属资源归零**（v5:90）：不保留常驻进程/长连接；等待是数据 + 触发条件。
- 触发是**事实流上的谓词**，不是轮询，也不是进程唤醒（glossary:63-66）。
- 条件**已经发生**时也要不漏（注册与历史扫描分开，G1:74）。
- 反例：常驻一个 while 循环轮询；用时间戳推全局因果；把 `sys.time.*` 当业务事件自定义（R5）。

## 框架缺口

**定时/时钟观测与等待责任**：需要一个规范化的定时触发原语（或明确"定时一律由外部事件源承担"）。R 的 waits 目前只是候选实现，未形成契约。
