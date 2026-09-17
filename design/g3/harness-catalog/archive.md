# harness 示例：archive（上下文控制 / 归档折叠）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

上下文窗口有限：把离开窗口的内容无损归档，只留摘要与指针；或做有损摘要（须留证据链）。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `sys.context.usage{window, used}`；`sys.context.threshold.crossed{kind: soft\|hard, threshold, used}`；`archive.requested{reason}`（模型主动）；`archive.performed{scope, from, to, fold_digest, original_refs[], mode: lossless\|lossy}` |
| 产生者 | `sys.context.*` = **runtime 观测**（框架规范契约，**阈值由 harness 配置**）；`archive.*` = harness 声明 |
| 触发与受理 | 软阈值跨越或 `archive.requested` → 开维护轮；硬阈值行为由 harness 的 `rounds` 决定（不硬编码在 runtime） |
| 投影 | 折叠后投影"**摘要 + 指针 + 尾部保留**"；完整原文经工具按需取回 |
| 逻辑（organization） | threshold archive = **无损**（原文仍在 content/session，只缩视图）；LLM 摘要 = **有损**，必须记 `fold_digest` 与 `original_refs` |

## 通用原语映射

P1 声明｜P3 触发｜P4 投影｜P5 逻辑｜P6 身份（`fold_digest`/`original_refs`）｜**P7 观测事实**（本示例的主承重）。

## 边界与反例

- **只改可见视图，不删恢复依据**（v5:252）；折叠产物是记忆本身，落 `content/`（T0），**不进 `derived/`**（T1 缓存）。
- runtime 不注入固定压力文本；是否开维护轮由 harness 触发条件决定（`minimal-harness-extension-points.md` §3）。
- 反例：用 `derived/` 当归档区；摘要丢原文且无指针；runtime 硬编码阈值；把 `sys.*` 当应用事件自定义（R5）。

## 框架缺口

**规范观测目录**：runtime 必须明确"保证产生哪些 `sys.*` 观测"（含阈值/配置契约与可观测性）。这是 P7 的**细化**，不是新目录。
