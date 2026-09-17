# g3 设计导读（当前基线 · review 索引）

地位：**索引，不是新规范**——告诉你读什么、按什么顺序、带什么问题。基线以
glossary v3.3（Task→Work、Workspace→Userspace，2026-09-17 用户裁决）为术语前提。
整理日期：2026-09-17。

系统一句话：**一个 Work 是推进所需的全部持久物（目录即 T0），"活"= 在册且被关注；
Runtime 持机制（事件底座、受理、触发求值、Round 执行、账本），Work 携带自己的
Harness 持策略（看什么、何时推进、如何接线）；模型是瞬时能力；轮间归零，接续从 T0 重放。**

## 1. 建议阅读顺序（review 主体）

| 序 | 文档 | 一句话定位 | 规模 |
|---|---|---|---|
| ① | [../GOAL.md](../GOAL.md) | 项目目标、G1–G5 阶段与通过标准 | — |
| ② | [../AGENTS.md](../AGENTS.md) | 执行纪律：独立证据、判据不放宽、历史保留 | — |
| ③ | [glossary.md](glossary.md) | **术语基线 v3.3**：推导链 N1–N9 → 18 词条（概念→定义→边界）→ 禁混表 → 墓碑 | 180 行 |
| ④ | [work-directory.md](work-directory.md) | **目录形态定稿**：目录树、写者归属（路径前缀=谁能写）、git 边界、待定机制题 | 129 行 |
| ⑤ | [work-directory-landing.md](work-directory-landing.md) | **落盘机制 v2**：双层落盘 D1、三分区 D3、拓展点目录树 v2、逐路径规范、原子性、挂载矩阵、可机检不变量、U1–U6 根本级待裁决 | 612 行 |
| ⑥ | [work-runtime-contract.md](work-runtime-contract.md) | **runtime↔harness 接口（M1 实现契约）**：Runtime 机制清单、Harness 策略清单、manifest 实际字段、已知缺口、修订记录（D1–D7） | 101 行 |
| ⑦ | `lore_harness_base.py`（仓库根） | **共享基座，代码即契约**：动作协议/解析、事实折叠、轮门骨架、受理工厂、投影脚手架（187 行，stdlib-only，不进 harness digest） | — |
| ⑧ | [harness-catalog/README.md](harness-catalog/README.md) | **示例集**：统一模板 + 派生新 harness 的编写期复用路径 + 十示例索引 | 56 行 |
| ⑨ | [design/backlog.md](../backlog.md) | **路线图**：B02–B21（DOING/PENDING/ADJUDICATE/IDEA） | — |

**代码与设计的对照物**：`lore_work/`（runtime）、`lore_harness/`（十示例）、
`validation/work_runtime/`（离线用例 + 独立校验器）。读 ⑥⑦ 时直接对着代码看。

## 2. 精读建议（时间有限时）

- **验收语义**：harness-catalog/goal.md——完成声明 ≠ 终态 ≠ 验收。
- **跨工作组合**：harness-catalog/delegation.md + work-runtime-contract 的 relay——
  wants+grants+host 权威，副本不继承授权；组合只在编写期（共享基座 + 参考合并 +
  事件受理），**无 runtime 组合机制**。
- **冻结/修订**：harness-catalog/system-design.md——局部修改、单调收敛。
- **扩展哲学**：landing §4.3 P1–P8 通用原语 + catalog 规则"示例定义不出的地方回补
  通用原语，不加领域目录"。

## 3. 前瞻设计（B16，全部 UNVERIFIED 设计稿）

[voice-assistant/](voice-assistant/README.md)（9 文件，~1400 行）：助手 = 一个长期
Work 的完整解剖——实时语音双工、对话记录目录化、日程复用标准 crontab、执行存活
（check 不自动杀）、延迟预算与知识维护两策略。review 时作为"通用原语够不够用"的
试金石（其缺口清单 = 下一批通用原语候选）。

## 4. 历史层（review 时不作为当前设计，供追溯）

- `harness-runtime-revised-v5.md`（v5 系统设计，**锁定**；glossary 墓碑多处引用其行号）
- G3/G4 期组件记录：`e/ f/ r/ s/ v/ x/ system/ reviews/ provider/ tool-service/
  file-publication/ session-plans/`、`coordination.md`、`x-*.md`、
  `minimal-harness-extension-points.md`（早期接口说明，拓展点语义已被 landing §4 吸收）
- 修订与验收记录（dated，旧名照原样保留）：`amendment-*.md`；
  `validation/work_runtime/FINDINGS-2026-09-16.md`、`acceptance/`、`docs/validation-status.md`

## 5. 建议的 review 检查清单

1. **推导链完整性**：每个词条是否真回答了 N1–N9 里的一个问题；有没有"说不清楚
   却进了表"的词。
2. **禁混表与墓碑**：逐条核对当前文档与代码无复活（run/turn/agent/orchestration/
   delivery/rendering/repo/task/workspace…）。
3. **单写者边界**：work-directory 写者表 ↔ runtime contract 的提交点（head 唯一）↔
   harness 只读（逐 Round digest 复核）三者一致。
4. **两份目录树一致**：work-directory.md 树 ↔ landing §4 目录树 v2（M1 按子集实现）。
5. **判据可执行性**：landing §13 与 voice-assistant validation-plan 的用例是否预登记
   判据（可拒绝、范围匹配）；实现者自跑 ≠ 独立验收。
6. **通用原语充分性**：十示例是否只用通用点即可表达（否则是缺口，不是新目录）。

## 6. 待裁决汇总（review 重点；均有登记，未擅自定死）

**根本级（landing §12.2，阻塞 B21 之前的形态定版）**
- U1 D1 双层落盘模型（目录=工作侧 T0 + 每工作设施根）
- U2 三分区与 glossary T0 修订（Session/观测原件归属）
- U3 content revision 机制（F capture vs worktree git）
- U4 R 控制库归属（工作侧 vs host 侧，建议拆分）
- U5 Userspace 迁移责任；U6 事件导出时机

**机制级**
- grants 同词异义：`relations.grants`（发送侧授权）与 Round Grant 撞名，Round Grant
  尚无实现物——改 glossary 还是改名，待裁决
- `harness/tools/`、`harness/budget/` 是否入选标准拓展点（landing §12.3；backlog B11）
- 落盘行形状与 landing §5 对齐：attempts/grant_snapshot/grant generation/生命周期
  命令（backlog B21，涉及 digest/恢复/校验器联动，建议单独设计）

**已取 M1 取舍、记录在案可复议**：U26（check 数值）、U27（硬上限配置来源）、
U28（finished 并入 result）、U30（check 落库粒度）——见 contract 修订记录。

**B16 框架定版**：LiveKit Agents vs Pipecat（plan 鉴权差距与许可待审）。

## 7. 实现状态快照（2026-09-17，实现者自跑）

- **已落地**：M1 runtime（单写者、触发水位、head 唯一提交、受理幂等 foreign_id、
  admit/relay、recover、工具存活三参数制）+ 十示例 harness 全部迁移至共享基座 +
  术语对齐（glossary v3.2/v3.3 两次）。
- **验证**：12 离线用例 + VO37–42 + `verify_goal_work.py` 端到端全绿——**均为实现者
  自跑；独立复跑未做**，组件不声称"通过"。
- **证据**：`validation/work_runtime/evidence/`（gitignore，不入库）。
