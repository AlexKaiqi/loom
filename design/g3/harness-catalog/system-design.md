# harness 示例：system-design（自顶向下系统设计）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

把一个系统**从整体设计到局部**：先定目标 / 不变量 / 边界，再逐层分解到子系统、协议、接口，最后到可实现单元。**设计不单指文档，也含协议类代码（类型 / 接口 / schema）**。

要治的实际病：

- 模型**不局部修改**，一动手就整体重写 → 结果**面目全非**；
- **无法稳定推进到最终设计**，来回调整、反复推翻。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `design.unit.proposed{unit_id, parent_id, level, spec_ref}`；`design.unit.accepted{unit_id, base_rev, evidence_refs[]}`；`design.unit.state.changed{unit_id, from, to, rev}`；`design.check.failed{unit_id, check_ref, detail_ref}`；`design.decision.recorded{decision_id, rationale_ref, affects[]}`；`design.amendment.requested{amendment_id, unit_id, reason_ref, impact_refs[]}`；`design.amendment.accepted{amendment_id, base_rev}` |
| 产生者 | 提案 / 决策 / 修订请求 = harness 或模型经受理；接受 / 修订接受 = harness 声明（或外部评审） |
| 触发与受理 | 前沿出现新单元 → 开轮细化；`check.failed` → 纠正轮；`amendment.accepted` → 受影响单元回到 draft 并开轮；受理**以 `base_rev` 做比较交换**，陈旧基线拒绝 |
| 投影 | **不变量与已冻结接口 + 当前单元 + 相邻冻结单元**（有界）；设计索引给指针；**不展开全量设计** |
| 逻辑 | 分层分解（父先于子）、前沿选择、影响分析（改祖先 → 后代失效）、冻结判定、一致性检查（文档 ↔ 协议代码） |

## 通用原语映射

P1 声明｜P2 受理（**含 `base_rev` 条件**）｜P3 触发｜P4 投影（有界 = 局部化的工作集）｜P5 逻辑（前沿 / 影响 / 冻结）｜P6 身份（`unit_id`/`decision_id`/`amendment_id` + `rev`）｜P7 观测（预算 / 上下文）。

## 三条"不面目全非"的机制

1. **冻结**：`accepted` 单元对模型只读；要改必须 `amendment.requested`（带理由 + 影响），**不能靠重写文件**。
2. **条件受理**：接受 / 修订带 `base_rev`；基线不是当前 `head` 就拒绝——挡住"基于旧阅读的静默重写"。
3. **有界投影**：每轮只给当前单元 + 接口 + 不变量；模型**根本没有全量重写的上下文**，局部是结构造成的，不是靠纪律。

## 稳定收敛（单调进展）

- 进展**可观**：`draft → proposed → accepted/frozen`；已冻结单元只在显式修订下回退。
- 变更**必留影响**：`design.decision.recorded{affects[]}` + 修订事件；后代失效是**事件**，不是悄悄改文件。
- 每轮一个 revision（`head`）+ 事实区间 → 设计演进史可对照、可回退、可审计。
- 反例：全量重写设计文档；用"最新文件"覆盖已接受的决策；改不变量不留修订；把实现代码当设计权威（或反之）。

## 与实现的关系

- **设计产物**（含协议代码）在 `surface/content/`：权威、版本化；
- **实现**（可运行代码/仓库）在外部 Workspace，**不进任务目录**（v5:38、G1:25）；
- 单元验收条件可含"协议与实现一致"的 checker，但须独立证据。

## 框架缺口

- **条件受理（`base_rev` 比较交换）**：需要通用的"以某版本为基础，否则拒绝"受理语义（现在只是候选，未成契约）。
- **冻结与修订**：把"已接受即只读、改动走修订"做成通用原语，还是仅由 admission 规则表达？待更多示例判定。
- **失效传播 / 依赖**：改祖先 → 后代失效需要通用依赖表达，否则每个 harness 自造一套。

## 现实参照

本仓库（Loom）自身的开发流程就是这个 harness 的一个实例：门（gate）、修订（amendment）、反例先行、证据准入、已通过项不静默改、影响分析。**可作观察来源，但不是框架标准**。
