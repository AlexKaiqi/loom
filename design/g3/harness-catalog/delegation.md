# harness 示例：delegation（跨工作委派）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

把一部分工作交给另一个 Work（子工作），等待其结果，再继续自己的推进。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `work.delegated{parent, child, scope, input_refs[], deadline?}`；`work.accepted` / `work.rejected{reason}`；`work.reported{child, result_ref, evidence_refs[]}`；`work.cancelled` |
| 产生者 | `delegated`/`reported` = 委派方 harness；`accepted`/`rejected` = 子工作（经**其** admission） |
| 触发与受理 | `accepted` / `reported` → 开父工作轮；`rejected` → 父轮决定改派 / 降级 / 暂停 |
| 投影 | 子工作**状态摘要 + 结果引用**（不读子工作正文） |
| 逻辑 | wants/grants 关系、超时与取消、结果证据引用 |

## 通用原语映射

P1 声明｜P2 受理（**跨面唯一门**）｜P3 触发｜P4 投影｜P5 逻辑｜P6 身份（parent/child/scope）。

## 边界与反例

- **无中心行动者**：委派 = 两个 Work 之间的事件受理，不需要编排中心（glossary:19,32）。
- **不继承授权**：B 声明 wants、A 记录 grants；复制目录**不产生授权**（不变量 I8）。
- 父工作**不能直接写**子工作 `content/`；只能发事件、等受理。
- 反例：父工作共享子工作的可写目录；按 `work.json` 文本冒充授权；一个工作里跑两套状态机冒充多工作。

## 框架缺口

**跨工作关系与授权查询的正式语义**：wants 记在谁、grants 何时生效、受理时如何查**当前 generation**——glossary 已注明"机制待定"（glossary:82-84）。
