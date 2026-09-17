# Loom 工作目录 Runtime：系统设计全文（外部 AI 评审包）

快照日期：2026-09-17 · 基线：glossary v3.3 · M1 实现（lore_work）
本文件**自包含**：评审所需的设计语料全部内嵌，无需访问仓库。
各章标注了来源文件；除"评审指令/综述/问题清单"等明确署名章节外，内容为原文照录。

## 目录

- 0. 给评审 AI 的说明（评审范围、纪律、输出格式）
- 1. 项目目标（GOAL.md 原文）与执行纪律（AGENTS.md 原文）
- 2. 术语基线 v3.3（glossary 全文）
- 3. 架构总览（评审包作者综述）
- 4. 目录形态定稿（work-directory 全文）
- 5. 落盘机制 v2（work-directory-landing 全文，612 行，本包最重一章）
- 6. runtime↔harness 接口契约 M1（全文）+ 工具存活修订（全文）
- 7. 共享基座 lore_harness_base.py（全文源码）
- 8. harness 示例集（catalog 全部 11 文件）
- 9. 事件词表清单（按 harness 机械生成）
- 10. CLI 参考（从源码机械生成）
- 11. 前瞻设计：语音助手（voice-assistant 全部 13 文件）
- 12. 路线图（backlog 全文）
- 13. 待裁决问题清单（评审重点，含原文）
- 14. 实现状态快照与历史层边界
- 15. 评审输出格式要求


---

# 0. 给评审 AI 的说明
你是本次系统设计评审的评审者。评审对象：Loom——一个"工作目录 runtime"的系统设计（目标形态 + M1 实现）。

## 评审范围与语料分层
- **当前设计**：第 2–12 章（术语 → 形态 → 落盘 → 契约 → 基座 → 示例 → 前瞻 → 路线图）。
- **历史层**（第 14 章列出）：v5 设计、G3/G4 期组件记录、dated 修订/验收记录。它们不是当前设计，仅用于追溯设计沿革；其中的旧术语（Task/Workspace 等）照原样保留是**有意为之**（记录不回写）。
- 第 3、9、10、13、14、15 章由本评审包作者（实现者）撰写或机械生成，请以同样的怀疑态度审阅它们。

## 你应当知道的设计纪律（按此标准要求这份设计）
1. **术语纪律**：术语以英文为准，能消歧就用短语；禁混表与墓碑**具约束力**。2026-09-17 刚完成 Task→Work、Workspace→Userspace 更名（用户裁决：task 的日常读法歧义）；历史记录中的旧名不回写。
2. **概念推导链**：每个术语必须回答推导链 N1–N9 中的一个问题；"没有它说不清楚的词"不准进表。
3. **判据文化**：验证判据预登记、不放宽、失败不删；实现者自跑 ≠ 独立验收；组件通过 ≠ 组合/系统通过。
4. **单写者**：路径前缀 = 谁能写；head 是唯一提交点；harness 只读（逐 Round digest 复核）。
5. **扩展哲学**：示例 harness 只用通用原语表达；表达不出的地方**回补通用原语，不加领域目录**（宁缺毋滥）。

## 我们特别想听的
- 推导链哪里断裂：哪个概念其实没被任何性质强制出来，或哪个性质缺概念支撑。
- 禁混表漏了哪些高危险混淆；墓碑词是否有人仍在建议复活的迹象。
- 单写者/受理幂等/触发水位在 M1 取舍下是否有原则性漏洞（而不只是未实现）。
- 通用原语 P1–P8 的充分性：十示例 + voice-assistant 是否暴露了必须新增的原语。
- U1–U6（第 13 章）六个根本级待裁决项，你若有一致推荐的组合，请给出理由与风险。

---

# 1. 项目目标与执行纪律
> 来源：GOAL.md / AGENTS.md 原文

# Harness Runtime：设计、调研、构建与独立验收目标

公开源码快照：2026-09-13。完整目标与完成标准保留；发布源码不表示目标完成，当前进展见 [验证状态](docs/validation-status.md)。2026-09-14 起开发、验证与部署面向 Unix 系统（macOS/Linux）；容器执行使用 Linux 容器运行时，历史上 WSL 证据仍属其原环境范围。

## 目标正文

依据本仓库的 v5 系统设计和用户已明确的约束，自顶向下完成 Harness Runtime 的目标细化、顶层设计论证与模拟、开源调研、可复用组件的独立验证、分层构建、组合验证和独立最终验收。持续推进至原始目标在明确且有依据的适用范围内得到兑现，交付可运行系统、可复现证据和完整设计资产。

### 1. 必须先读的依据

- [AGENTS.md](AGENTS.md)：执行原则、禁止事项与完成门槛。
- [v5 系统设计](harness-runtime-revised-v5.md)：系统目标、原则、核心不变量与待验证工程选择。
- [开源调研清单](harness-runtime-open-source-research-list.md)：主清单、候选身份、专项及各项目交付要求。
- [执行指南](governance/execution-guide.md)、[检查表](governance/checklists.md)、[证据指南](governance/evidence-guide.md)。
- [性质验收映射](governance/runtime-acceptance-map.md)与[记录模板](governance/templates.md)：作为细化起点，不能代替原始要求的完整覆盖。
- [执行环境](governance/linux-environment.md)与[模型验证配置](governance/validation-environment.md)：明确 Unix 主机执行目标（macOS/Linux）、Linux 容器运行时和项目外凭据引用。

保留目标与原则，区分核心不变量、候选实现、事实、假设与未知项。候选项目、示例接口和目录不能反向决定目标；工程决策可以因新证据修订并留下依据。

### 2. 系统最终应具备的能力

Runtime 与 Harness 分离：Runtime 提供事件底座、Surface、工作环境沙箱、解释 Harness 并执行推进四项契约；Harness 以外部定义决定模型看什么以及如何推进。清楚划分 Surface、Userspace、局部 Session 与 Runtime 的职责和权威状态，优先复用既有事实记录。

兑现 v5 的主要价值：多策略原生并存和解耦演进；等待期工作专属进程、长连接与沙箱资源归零；持久状态和已受理推进责任支撑长程接续；双域分立、权限边界与可控破坏范围；约定范围内的版本追溯与状态恢复。

遵循模型熟悉的普通代码、文件和 Shell 语义，优先复用成熟基础设施，以确定性和可逆性约束设计。明确状态回退与外部副作用补偿的区别，明确已确认状态及可恢复边界，不以重跑冒充无损接续。

最终范围包括最简闭环之后、v5 已要求的多 Surface 等待与信息传递、多策略隔离与对比，以及等待驻留和活跃吞吐的规模验证。最简闭环只是中间里程碑。具体工作负载、故障范围、资源和指标在对应阶段先论证并形成验收基线，不预设未经依据支持的容量数字，也不在测量后自设及格线。

### 3. 必须遵守的推进顺序

1. **G0：建立目标与验收基线。** 逐项提取原始要求、边界、非目标、优先级和必须性质，建立覆盖矩阵；区分当前里程碑与最终完成范围。
2. **G1：完成顶层抽象、论证与模拟。** 明确分层、依赖方向、职责、状态、权限和恢复契约，比较方案并检查关键反例。影响下一层的关键假设有证据支持后才继续。
3. **G2：定向克隆并研究开源项目。** 按既有清单完成源码与相关运行实验，必要时围绕证据缺口扩展项目。记录固定版本、适用前提、可复用模块、适配缺口和不采纳理由，区分声明、源码、实测及推断。
4. **G3—G4：先准备独立用例，再构建与验证组件。** 每个组件先有抽象和契约，定义性质、独立预期、通过标准、正常/边界/相关失败用例及可运行环境，再实现并迭代修复。组件独立通过后才能进入系统。
5. **G5：逐步组合并验证整体性质。** 先完成单 Surface、单 Userspace 的最简真实闭环，再继续相关故障、恢复、多 Surface、多策略和规模验证。组件通过不能替代组合与系统证据。
6. **G6：独立验收与交付。** 对照原始目标检查当前版本的完整证据，直接核验产物和关键运行事实，独立复跑核心检查，处理异议并完成必要修复与回归。

各阶段按治理文件的证据门槛自主推进，不以用户逐轮审批为默认流程。阶段通过后自动继续下一已授权阶段；未通过时暂停依赖该门槛的跨层工作，同时继续有依据说明无依赖的工作。新证据否定上层假设时，回到最早受影响层修订和重验。

顶层模拟和探索性测量必须先有待检验问题、观测方法与停止条件；探索结果不得充当正式性质通过。正式组件开发前，准备好相关验收契约、用例与验证环境。

### 4. 独立验收与防止妥协

每项必须性质都须有：来自目标或契约的独立判据、实际观测、能够拒绝相关错误的验证、匹配的适用范围，以及实现/测试/数据/环境的明确版本。直接检查真实产物和必要的依赖侧或执行环境事实，不能以 Agent 自述、应用声明、退出码或同源日志代替验收。

使用可用的独立 Agent 或外部验收器核对原始要求与证据并复跑。把可机械判定的必须项接入可重复运行的验收入口，至少检查目标覆盖、实际用例执行、关键产物、证据与版本一致性及未通过项；完成声明不能代替验证结果。该设施限定于本系统开发验收所需，不扩张为通用平台，也不在 Runtime 中新增通用业务终态协议。

禁止因困难、时间、预算或上下文切换而删掉失败用例、降低阈值、换简单数据、缩小必须范围或隐藏失败。必要的标准修订须有独立理由、保留原记录并重新检查目标符合性。失败、阻塞、未验证和失效证据均不得计入必须项通过。

### 5. 必须沉淀的交付资产

- 目标、原则、非目标、核心性质与完整覆盖矩阵。
- 顶层设计、抽象与契约、模型与模拟、关键判断、备选方案和取舍记录。
- 固定版本的开源调研结论、相关实验、复用与适配决策。
- 通过独立验证的组件、分层系统实现及必要的验收设施。
- 可重建的验证快照、原始证据、失败修复与回归记录、独立验收报告。
- 实际可用的启动、验证与恢复说明，以及可接续的工作状态记录。

保持“原始目标 → 性质 → 抽象与判断 → 组件契约 → 用例 → 实现 → 验证证据”的追溯关系。设计与判断资产优先于具体代码，随实现和新证据同步维护。架构审查包含职责分层、依赖方向、变化隔离、单文件复杂度与事实归属。

### 6. 完成与停止条件

只有当本目标范围内的原始必须项全部获得当前有效且层级匹配的通过证据，重要失败与独立验收异议解决，系统可运行、验证可复现、资产与交付版本一致时，才可标记目标完成。

不能因计划写完、调研摘要完成、最简演示成功、组件全绿或一个阶段完成而停止整个目标。所有约定必须项通过后，范围外优化进入后续记录，不无限扩展当前工作。

由 Agent 自主承担日常方案比较、实施、验证和修复。遇到决定根本目标且无法从已有依据推导的事项，或实际不可满足的执行条件，应保存失败证据、未决项及接续状态，继续其他可推进工作；全部可推进路径确实耗尽时如实报告阻塞，不以猜测或降低要求宣告完成。平台目标状态与预算操作遵循实际工具规则。

## 提交方式

用户已在 Linux 环境调整完成后明确要求继续。确认旧目标不存在后，已按本文件完整正文和 Linux 约束创建持续目标。后续先查询实际状态，避免重复创建未完成目标；阶段与接续信息见 governance/work-state.md。


## 执行纪律（AGENTS.md 原文）

# 本仓库 Agent 工作约束

本仓库为 Loom 的开发中源码快照，Python 包暂保留 lore_* 名称。目标、阶段与通过标准见 [GOAL.md](GOAL.md)，当前状态见 [验证状态](docs/validation-status.md)。

## 执行平台

- 当前目标为 Unix 系统（macOS/Linux）：开发、构建与验证在 Unix 主机执行；容器执行使用 Linux 容器运行时。
- 不把开发者机器路径或单一宿主（WSL、Windows 等）语义引入产品依赖；平台相关行为按 `sys.platform` 显式分支并记录证据范围。
- 凭据保存在仓库外的受限目录，不进入 Git、镜像、证据包或任务环境。
- 新环境重新生成依赖的路径与物理身份 manifest，不复制旧机器的 inode/device 标识。

## 开始或恢复任务时

1. 读取用户当前要求、[v5 系统设计](harness-runtime-revised-v5.md)和[开源调研清单](harness-runtime-open-source-research-list.md)。区分目标、核心不变量、待验证工程选择。
2. 读取[执行指南](governance/execution-guide.md)、[证据指南](governance/evidence-guide.md)和当前阶段的[检查表](governance/checklists.md)。
3. 检查最近的任务恢复记录、验收契约、失败记录和实际文件状态；上下文摘要不能替代原始要求与证据。
4. 明确当前授权范围、所处阶段、未通过门槛及下一步要解决的问题。找不到已有通过证据时保持未验证，不根据上一位 Agent 的口头结论继续跨层推进。

## 必须遵守

- 自顶向下：目标与性质 → 顶层抽象、论证与模拟 → 定向调研 → 组件契约与用例 → 独立实现验证 → 组合验证 → 独立验收。
- 对应实现开始前，先确定性质、适用范围、判据与验证用例。生产组件开发前还须准备可执行的验证环境；顶层模型与模拟先有待检验问题和判据。
- 未过当前门槛，暂停依赖该门槛的跨层工作，补齐证据、修复失败或修订上层判断；有依据说明无依赖的已授权分支可以继续。禁止用框架选型或底层代码反向决定系统目标。
- 独立验证通过是组件进入系统的前提；组件通过不等于组合或系统通过。
- 独立证据要求判据来源独立、直接观测、能拒绝相关错误、范围匹配、版本明确。换一个 Agent 复述报告不构成独立验收。
- Agent 自述、应用声明、退出码、绿色截图、测试数量、代码量和投入时间均不能单独证明任务完成。
- 禁止通过删掉失败用例、放宽误差、换简单数据、隐藏跳过、缩小范围或修改预期来制造成功。必要的标准修订须保留独立理由、旧记录及影响分析。
- 未验证、失败、阻塞、证据失效都不能计入通过。预算或时间不足只改变进度，不改变完成标准。
- 分层职责、依赖方向、变化隔离、单文件复杂度和事实归属必须审查；具体限制从问题推导，不擅自冻结技术栈或行数。
- 目标、性质、判断、取舍和验证资产与实现同步维护；更新时保留来源和历史，不覆盖不利证据。
- 在既有目标与授权内自行比较方案、实现、验证、修复，不把日常推进变成用户逐轮审批。缺乏依据且决定根本目标的未知项不得随意补造。
- 目标运行期间，阶段通过后自动继续下一已授权且前提满足的阶段。不得把工作单元或里程碑自行改成整项任务的终点；当前全部授权目标完成，或确实无法继续且已保存接续状态，才结束推进。尊重用户在应用中的暂停状态。

## 完成门槛

必须通过[最终验收清单](governance/checklists.md#终验最终独立验收)：约定范围全部必须项都有当前有效证据；组件、组合和系统证据层级匹配；重要失败修复；独立验收者直接核对原始证据并复跑核心检查；交付内容与被验版本一致。

独立证据验收是必须项。具备多 Agent 或外部验收器时分配独立验收角色，要求其从原始契约出发、直接检查或复跑，不接受实现者报告代替证据。仅有单 Agent 时仍须从锁定契约重新观测并复跑，记录角色未分离及其局限，不能声称他人已验收；若契约明确要求角色分离，则该条件仍是必须项。不得为回避审查而将可用验收能力声称为不可用。

当前的[系统性质验收映射](governance/runtime-acceptance-map.md)仅是从 v5 提取的待细化用例，不表示系统已被实现或验证。[记录模板](governance/templates.md)用于后续建档；空模板和勾选本身不是证据。

这些 Markdown 规则依赖执行者遵守，尚无自动强制门禁。后续获授权构建执行机制时，应让独立验证结果决定可否完成；同一可写工作区内的多 Agent 不构成安全隔离。


---

# 2. 术语基线 v3.3
> 来源：design/g3/glossary.md 原文（2026-09-17 更名后的现行版）

# 术语与概念基线 v3.3

地位：概念与术语基线，不是规范。v3.2 于 2026-09-16 定稿：每个术语先阐明概念
（它回答什么问题），再给定义。**术语以英文为准；能消歧就用短语——清晰优先于
简洁，不为单词而单词；中文译名可选。**
禁混表与墓碑具约束力；进入组件合同时逐词复核。来源：2026-09-16 术语对话（用户裁决）；
v3.3 更名（Task→Work、Workspace→Userspace）来自 2026-09-17 用户裁决。

## 概念推导链（每条目标性质强制出哪些概念；没有它说不清楚的词才准进表）

- N1 长程工作**在等待中活、在执行时算**（归零）→ 活的单位 ≠ 执行的单位 → Work / Round
- N2 一切因果**可恢复、可审计、可协作** → 事实有属地、准入有唯一门、语义有身份
  → Surface / Fact Admission / Fact Contract / Event
- N3 推进策略**因工作而异、可对比** → 策略与机制分离 → Harness / Runtime
- N4 模型是**瞬时能力** → 意图与供给分离 → Model Ref / Model Routing；供给的节拍 → Step
- N5 执行**开放长** → 权能必须短命 → Round Grant；执行要有承载 → Work Environment / Userspace
- N6 模型**只能看见被供给的内容** → 内容/形式分离 + 按需深挖
  → Projection / Presentation / Context Organization
- N7 交互史**是观测不是因果**；数据**可重建性不同** → Session；T0/T1/T2
- N8 轮要能**开始和结束**、工作要能**"不活"** → Trigger Condition / Attempt / Archive
- N9 跨工作协作**无中心行动者** → 各工作 Harness 声明受理（N3+N2 推论）

## 目标形态

一个 Work 是推进所需的全部持久物，"活"的唯一单位：在册即活，Runtime 关注它——
求值其 Surface 上的 Trigger Condition、执行其 Fact Admission 规则。工作携带自己的 Harness（推进定义）：
面形态约定、Projection 策略、Round 逻辑、Fact Admission 规则、Trigger Condition 与前置逻辑代码——
不同工作有不同的目录结构、投影方式与推进方式，这些都属于工作目录。
推进只由 Event 驱动：外来事件（用户、时钟、外部系统、其他工作的 Surface）经 Fact Admission
落为面的事实；Trigger Condition 满足时工作进入一个 Round——Harness 逻辑前置（可选）将事实
转换为面内容，若干 Step 完成模型工作（模型按 Model Ref 经 Model Routing 供给），新事实
落面，Round 结束资源归零。一切事实落面；Round 之间工作休眠——纯数据驻留，Trigger Condition
仍被求值；接续 = 从 T0 重放（含 Harness）。多工作协作 = 面间事件受理，按各自
Harness 声明，无中心行动者。

## 概念条目（概念 → 定义 → 边界）

### 机制与策略
- **Runtime（运行时）**。概念：机制的所有者——"怎么执行"归它。
  定义：事件底座、工作登记与关注、工作环境生命周期、解释 Harness 并执行推进、
  记录与恢复。边界：不内置任何策略；策略全部来自工作携带的 Harness。
- **Harness（推进定义）**。概念：策略的所有者——"看什么、何时推进、如何接线"归它；
  回答"工作的个性放在哪"。定义：面形态约定（目录结构）+ Projection 策略 +
  Round 逻辑（含结束条件）+ Fact Admission 规则与 Trigger Condition + 前置逻辑代码；内容寻址、
  随工作登记固定，改一字节即新版本；可从模板实例化，登记后是工作自己的数据。
  边界：与 Runtime 的分界 = 策略 vs 机制；模型默认不可自改自己的 Harness。

### 活与推进
- **Work（工作）**。概念：回答三问——什么是"同一个工作"（身份）、什么算"活着"
  （在册+被关注）、接续的边界（自包含）。定义：**推进所需的全部持久物** = Harness +
  Surface + Session + 可用沙箱（环境绑定，实例按 Round 分配）+ 关系绑定 +
  授权身份与 Model Ref（秘密与端点在 runtime 侧）+ Runtime 账本记录。
  Work 与 Surface 1:1。边界：模型与 Runtime 不在工作内（轮执行期间供给的瞬时能力）；
  无业务终态；"不活"仅管理动作（Archive）。
- **Round（轮）**。概念：授权、资源、预算、恢复需要共同的边界——有界性是四者的
  共同前提。回答"一次推进从哪到哪"。定义：Trigger Condition 满足 → Harness 逻辑前置（可选）→
  ≥0 Step → 事实落面 → 归零；Round Grant、预算、截止挂它；正式行文可用"推进轮"。
  边界：轮有结束条件，工作没有；attempt 是轮内重试，不改轮身份。
- **Attempt**。概念：执行可崩溃，重试不得制造第二个推进单位。定义：Round 内一次
  进程级执行尝试；崩溃重试不改 Round 身份。
- **Step（步）**。概念：模型工作的原子节拍——没有供给的调用是盲调用。
  定义：上下文供给（Projection → Presentation）→ 模型调用 → 工具执行 → 观测；
  观测进入下一次供给。
- **Trigger Condition（触发条件）**。概念：轮的启动是声明条件的求值结果——不是轮询，
  也不是进程唤醒。回答"什么让一轮开始"。定义：Surface 事实流上声明的谓词；
  每次落事实后由 Runtime 求值；满足即开轮；不重复开轮的去重挂 Runtime 账本。
  边界：Trigger Condition 是谓词，不是事实（禁混表）。
- **Archive（归档）**。概念：工作的"不活"是管理动作，不是业务终态。
  定义：数据保留、Runtime 停止关注（不再求值 Trigger Condition、不再受理）。

### 因果与准入
- **Surface（面）**。概念：事实必须有属地——没有落面的信息不是事实。
  回答"因果记在哪、模型在改什么"。定义：Work 的内容与事实平面 = 工作副本 +
  发布头 + 事实流；外来事实经 Fact Admission 进入。边界：内容回答"现在是什么"，
  事实回答"为什么/何时"，互不可替。
- **Event / Fact stream（事件/事实流）**。概念：因果的唯一记录，append-only。
  定义：落面的因果事实；业务事实有 Fact Contract；Runtime 私有账本（Fact Admission 去重、
  Round 记录）是运行记录，不是事件。
- **Fact Contract（契约）**。概念：事实的语义身份——没有声明 schema 的事实无法校验、
  路由、安全消费。定义：payload schema 的内容寻址身份；digest 变 = 语义变。
- **Fact Admission（受理）**。概念：外来事实与一个面之间的唯一门——门上只挂三件事：
  Fact Contract 校验、幂等去重、允许；多门即不可审计。回答"外面的发生如何变成这个面的
  事实"。定义：外来事件经它成为面流事实；规则由工作自己的 Harness 声明；跨工作
  受理需对方允许（授权语义，机制待定）；受理不改变事实内容——语义身份由 Fact Contract
  决定，它只决定收不收。边界：**门外是世界，门内是面的事实流；门后的一切
  （Trigger Condition 求值、Round 推进）都不属于它。**

### 行动与承载
- **Tool（工具）**。概念：模型行动的两类通道——工作域执行与 Runtime 域操作；
  跨界必须显式且限时。定义：普通工具（bash / MCP 同类，工作域执行）∥
  受控设施（emit/publish 类 Runtime 薄包装，需 Round Grant）。
- **Work Environment（工作环境）**。概念：执行的承载——可分配、可归零，
  与工作数据的持久性分离。定义：挂载 Userspace 的执行环境；沙箱实例按 Round
  分配、轮间归零、可短暂保温。
- **Userspace（用户空间）**。概念：授权的文件范围——"能碰什么"与"在哪里执行"分离。
  定义：文件范围引用（owner/kind/身份/版本）；host/用户授予的外部领地，被授权进入。
- **Round Grant（轮授权）**。概念：最小授权——模型执行开放长，权能必须比它短命。
  定义：Round 作用域的权能（受控设施、资源）；Round 结束失效。

### 模型供给
- **Model Ref（模型引用）**。概念：意图与供给分离的需求侧——换模型 = 换引用，
  多策略对比免费。定义：工作按用途声明的模型引用（reasoning / recall / embedding 等）；
  秘密与端点不在工作内。
- **Model Routing（模型路由）**。概念：意图与供给分离的供给侧——引用如何变成一次真实调用。
  定义：模型目录 + 显式解析（不静默回退，缺引用响亮失败）+ 凭证持有 +
  用量计量（挂 Round，观测域）。所有模型调用都经它：Step 主推理、Projection 辅助
  召回、维护轮的折叠/索引。

### 感知
- **Projection（投影）**。概念：内容决策——模型只能看见被供给的内容；观测仪器
  钉在它的产物上。定义：持久状态 → 模型感知内容的声明式映射：策略由 Harness 固定、
  成本有界（挂 Round）、产物可观测（T1 落盘可复核）；给指针不灌全文；可声明模型
  辅助召回（recall 引用）；恢复从 T0 重建，不重放召回调用。
- **Presentation（呈现）**。概念：形式适配——与 Projection 的"内容/形式"分立。
  定义：Projection 内容 → 特定模型请求形式（prompt 拼装、协议字段、模态包装）；
  只改形式，不得改变内容。

### 观测与恢复
- **Session（会话）**。概念：观测域——审计需要它，接续与 Projection 不依赖它。
  定义：模型交互史。
- **T0/T1/T2（持久层级）**。概念：可重建性决定持久义务——接续集、废弃集、授权集
  按层取子集。定义：T0 权威事实（面内容+发布头、事实流、Harness、Runtime 账本）；
  T1 派生可重建（折叠、索引、Projection 缓存）；T2 瞬态（沙箱实例、运行现场）。
  接续集 = T0。
- **Context Organization**。概念：上下文是稀缺资源——治理 = 隔离 + 按需。
  定义：空间轴（多面隔离）、时间轴（Archive：无损驻留+指针）、深度轴
  （固定 Projection + 工具按需深挖）。

## 禁混表

Work ≠ Surface（数据全体 vs 其内容+事实平面）｜Work ≠ Round（生命周期全体 vs 有界单位）｜
Round ≠ 会话轮次 ≠ Attempt｜Harness ≠ Runtime（策略 vs 机制）｜Harness ≠ Surface
（推进定义 vs 工作内容）｜Harness ≠ Round（定义 vs 一次执行）｜Trigger Condition ≠ Event
（谓词 vs 事实）｜Projection ≠ Presentation（内容 vs 形式）｜Fact Admission ≠ Event
（门 vs 门内事实）｜Fact Admission ≠ Trigger Condition（落面之前 vs 落面之后对事实求值）｜
Event ≠ 私有账本（因果事实 vs 运行记录）｜普通工具 ≠ 受控设施
（工作域 vs Runtime 域）｜Model Routing ≠ Model Ref（供给侧 vs 需求侧意图）｜
工作的"活" = 在册+被关注 ≠ 进程存活｜**agent ≠ Work**（agent 是工作在 Round 执行
期间的临时形态——模型在环；工作才是持久单位。系统无常驻 agent；模型不在工作数据内）｜
Work ≠ Userspace（工作全体 vs 授权的外部文件范围——工作用 Userspace，不拥有它）

## 墓碑（已废词，勿复活）

- **orchestration**：并入 **Harness**——v5:46 本义即"Harness 推进定义中涉及多个
  Surface 的普通代码"；跨工作接线 = Harness 的 Fact Admission 规则与触发条件，
  不再是独立登记实体。
- **run**：概念正确（自包含、在册即活）但词带过程味；概念并入 Work（v3.2 时称 Task）。
- **turn**：生命周期义归 Work，有界义归 Round。废因：消息族"会话轮次"歧义 + 参照实现授权机制包袱。
- **reaction**：并入 Round 的 Harness 逻辑前置阶段。
- **delivery / input / advance**：统一为"Event + Fact Admission"。
- **series**：被 Work 取代（即原"跨轮持久身份"）。
- **execution（名词）**：降为动词。
- **mapping / ingest**：最终更名 **Fact Admission（受理）**——mapping 暗示变换函数；
  ingest 是 ETL 词（把数据搬进存储），丢了"准入有标准、落地即因果、需被允许"
  三件事；本义即 v5 中 R 的受理责任。
- **rendering**：更名 **Presentation**——与 Projection 的"内容/形式"对照更直接。
- **repo**：口语，指 Work 的 T0 全体；不进契约。
- **task（v1–v3.2 用作核心词）**：概念不变（推进所需的全部持久物），更名 **Work**。
  废因：日常"一件可完成的工作"读法与 agent 框架"给 agent 的工作项"读法双重歧义，
  覆盖不了长期开放、被持续办理的形态（如助手）；2026-09-17 用户裁决。
- **workspace（v1–v3.2 用作核心词）**：更名 **Userspace**——为 Work 让位近形词；
  实质本就是用户侧授权领地。2026-09-17 用户裁决。

## 版本沿革

- v1（2026-09-16）：初版，含 Run/Reaction/持久工作集等词，随后逐一废止。
- v2：剥离参照实现痕迹；确立在册即活；设禁混表与墓碑制。
- v2.1：Step 补全投影/呈现循环；mapping→Ingest、rendering→Presentation；术语以英文为准。
- v2.2：Harness 进表（任务携带推进定义）；orchestration 入墓碑。
- v2.3：Model Ref 与 Routing 进表；Projection 放宽为声明式；agent ≠ Task。
- v3：概念层——推导链 + 每词条"概念→定义→边界"；补 Runtime / Trigger / Attempt /
  Contract / Tool / Archive 六个被使用却失定义的词。
- v3.1：Ingest→Admission（受理）——ETL 词丢"准入有标准/落地即因果/需被允许"；
  给出一句话边界（门外世界，门内事实流，门上三件事）。
- v3.2：命名规则升级"清晰 > 简洁，短语优先"；五处消歧短语化——Trigger Condition /
  Fact Admission / Fact Contract / Round Grant / Model Routing。
- v3.3（2026-09-17）：**Task→Work**（task 的"可完成工作"与 agent 框架工作项双重读法
  歧义，覆盖不了长期开放的形态；用户裁决）；**Workspace→Userspace**（为 Work 让位近形词，
  实质即用户侧授权领地）；Task Environment 随之更名 Work Environment；
  禁混表补 Work ≠ Userspace；墓碑补 task/workspace 两条。


---

# 3. 架构总览（评审包作者综述）
本节是给评审者的导读性综述，非规范；规范以第 4–7 章为准。

## 3.1 持久与瞬时的三界
- **Work（工作）**：全部持久物 = Harness（推进定义，内容寻址）+ Surface（工作副本+发布头+事实流）+ Session（观测）+ 关系绑定 + Model Ref + Runtime 账本。目录即 T0；"活" = 在册 + 被关注，无进程含义。
- **Round（轮）**：有界执行单位——授权/资源/预算/恢复的共同边界；结束归零。
- **模型**：瞬时能力，按 Model Ref 经 Model Routing 供给；不在任何持久物内。

## 3.2 一次推进的因果链
外部事件（用户/时钟/外部系统/其他 Work 的 Surface）→ **Fact Admission**（唯一门：Fact Contract 校验 + foreign_id 幂等去重 + 允许判定）→ Surface 事实流（append-only）→ Runtime 求值 **Trigger Condition**（声明谓词；水位防重复开轮）→ 开 **Round**：Harness 逻辑前置（可选，把事实折叠为域状态）→ 若干 **Step**（Projection 供给上下文 → 模型产出**一个 JSON 动作** → 工具执行 → 观测落面）→ head **唯一提交点** → Round 归零。

## 3.3 关键取舍（M1 现状）
- **单写者**：Runtime 写面；harness 模块只读（加载时逐 Round 复核 digest）；模型输出是动作（shell / emit / final），emit 声明的事实经受理落面，final 不自动等于完成。
- **工具双域**：普通工具（工作域 shell，userspace 路由，未登记目标拒绝）∥ 受控设施（emit/relay = Runtime 薄包装，需 Round Grant）。
- **工具存活**（2026-09-17 修订）：`check_interval` 只发 `sys.tool.check` 观测不杀（退避×2 封顶 60s）；`budget_ms` 是策略预算（SIGTERM→宽限→SIGKILL → outcome=timeout）；runtime 硬上限 600s 是安全网（回收即 unknown + `sys.tool.abandoned`）。`outcome` 权威（ok/failed/timeout/unknown），`exit` 仅兼容镜像。
- **跨工作协作**：无中心行动者。关系声明 wants/grants + host 权威；`relay` 把一个 Work 的事件经另一个 Work 的受理门落入（副本不继承授权）。**组合 = 编写期复用（共享基座 + 参考合并）+ 事件受理；明确不引入 runtime 组合机制**（无 extends/override/插件）。
- **恢复**：接续 = 从 T0 重放（含 harness）；中断 Round 的未提交事实隔离进观测区（crashed/）+ 截断 + repairs 账本。
- **M1 明确不做**（登记为缺口，非缺陷）：沙箱隔离（X 职责，模型脚本可 cd 逃逸已如实记录）、租约、调度（crontab 叫醒）、对外通知/投递、多 Work host 登记/索引。

## 3.4 评审者值得注意的张力点（作者观察，不预设结论）
1. glossary 断言"Work 与 Surface 1:1"，而 Context Organization 空间轴写"多面隔离"——单面是当前事实还是长期约束？
2. "在册即活"的权威：M1 无 host 登记/索引，landing §12.3 问"能否仅靠扫描 works-root 重建在册"。
3. 零驻留（轮间无进程无连接）与 monitoring/定时唤醒：等待责任归谁（runtime 内建循环 vs 宿主调度器）尚未裁决（B16 ④）。
4. Round Grant 无实现物，而 `relations.grants`（发送侧授权）已用 grants 一词——同词异义待裁决。
5. 事件导出/读端循环（landing §12.3）与单写者 head 提交的接口边界。
6. P1–P8 充分性：voice-assistant 缺口清单（对外投递、流式观测通道、媒体 artifact、实时会话设施归属）是最激进的压力测试。

---

# 4. 目录形态定稿
> 来源：design/g3/work-directory.md 原文

# 工作目录框架（目标形态定稿）

地位：`glossary.md`（v3.2）的第一个伴生文档——把概念边界落成磁盘布局。
2026-09-16 按对话裁决定稿；进入实现前按机制题清单逐项复核。

> **v2 补全**：[work-directory-landing.md](work-directory-landing.md) 补本文件没有回答的另一半——
> 目录与既有设施（R/E/F/S/X）的关系、持久分区、逐文件规范、原子性、生命周期、权限矩阵、
> 五个机制题的裁决与预登记用例。本文件已裁决的框架原则保留；对 v1 的修订集中在 v2 件的 §12。

## 核心原则

**框架目录固定（runtime 语义），内容目录自由（harness 约定）。**
目录结构是概念边界在磁盘上的投影：框架区对所有工作同构，runtime 语义只有一套；
工作的个性（目录结构、投影方式、推进方式）只落在 `surface/content/` 内部。

## 目录树

```
<works-root>/<work-id>/
├── work.json                  # 身份与绑定：授权身份、model refs、沙箱绑定、
│                              #   关系（受理声明与允许）、harness digest、状态
├── harness/                   # 推进定义——登记后只读，模型永不可写
│   ├── manifest.json          #   入口与各策略引用（含自身 digest，改一字节即新版本）
│   ├── conventions/           #   面形态约定：content/ 内部该怎么长
│   ├── projection/            #   Projection 策略（供给什么内容，含 recall 引用配置）
│   ├── organization/          #   组织策略：怎么重组 content 降低上下文（折叠/归档/压缩）
│   ├── rounds/                #   Round 逻辑：何时开维护轮、何时结束
│   ├── admission/             #   Fact Admission 规则：收什么、凭哪个 Fact Contract
│   └── logic/                 #   前置逻辑代码
├── surface/                   # 工作平面
│   ├── content/               #   ★模型唯一可写区；内部结构由 conventions 决定；
│   │                          #     git 管理（每 Round 一个 commit）
│   ├── head                   #   发布头 → 当前权威 revision（内容寻址 digest）
│   └── facts.jsonl            #   事实流（append-only，runtime 写）
├── session/                   # 交互史（观测域，runtime 写）
│   └── rounds/<round-id>.jsonl
├── ledger/                    # Runtime 账本（运行记录，不是事实）
│   ├── admission.jsonl        #   外来事件去重账（foreign id → digest）——不重复受理的机制所在
│   └── rounds.jsonl           #   轮记录：触发求值、起止、attempt 列表、Grant 快照、计量
└── derived/                   # T1 可重建：投影缓存（观测仪器钉在其上）、embedding 索引——随时可删
```

**T2 不进工作目录**：沙箱实例、轮执行现场放 runtime 临时区，按 Round 分配释放。
目录里永远只有"接续所需的持久物"——**拷走目录 = 搬走完整工作**（可移植性不变量）。
revision 的存储以 git commit 为载体（机制），`head` 仍是显式 digest 指针——概念不变，机制可换。

## 写者归属（路径前缀 = 谁能写）

| 路径 | 写者 | 层级 |
|---|---|---|
| `surface/content/` | **模型**（轮内工具，唯一可写区） | T0 |
| `surface/head` | Runtime（轮提交时原子推进） | T0 |
| `surface/facts.jsonl` | Runtime（append-only） | T0 |
| `harness/` | 登记时一次写入，此后只读 | T0 |
| `session/`、`ledger/`、`work.json` | Runtime / 管理面 | T0 |
| `derived/` | Runtime 重建 | T1（可删） |
| （目录外）沙箱实例 | Runtime 按 Round 分配释放 | T2 |

## 设计陈述

1. **不同工作的"不同目录结构"只落在一个点**：`surface/content/` 内部（助手工作长成
   `journal/ + index.md`，编码工作长成 `src/ + tests/`，由各自 conventions 决定）。
2. **Harness 与内容同目录但物理隔离**：模型在 `content/` 里再怎么写也碰不到自己的
   推进定义；只读性按目录边界执行（沙箱只挂载 content/），不靠模型自觉。
3. **事实与内容分文件**：内容回答"现在是什么"（head → revision），事实回答
   "为什么/何时"（append-only 流）——禁混表"互不可替"在磁盘上就是两个路径。
4. **账本与事实流分家**：受理去重、round/attempt 记录是运行记录不是因果事实
   （Event ≠ 私有账本），磁盘上同样分家。

## 拓展点映射

`harness/` 子目录 = 拓展点的物理形态，磁盘上看得见：

| 目录 | 对应拓展点 |
|---|---|
| `harness/conventions/` | 面形态约定（目录结构） |
| `harness/projection/` | 投影策略（模型看什么） |
| `harness/organization/` | 组织策略（怎么重组降低上下文） |
| `harness/rounds/` | Round 逻辑（维护轮时机、结束条件） |
| `harness/admission/` | Fact Admission 规则 |
| `harness/logic/` | 前置逻辑代码 |
| `work.json` 字段 | model refs、沙箱绑定、受理关系、授权身份 |

Runtime 侧拓展点（工具执行、事件底座）不在工作目录——它们是机制，不是工作个性。

## 组织策略（organization/）与 derived/ 的分界

- **组织策略改写 `surface/content/` 本体**——折叠后的 journal、归档后的目录是模型的
  **记忆本身，T0**；
- **`derived/` 只放可重建的缓存**（投影快照、索引，删了能算回来，T1）。
  折叠产物不是缓存，不放 derived/。
- 组织策略的**执行时机**由 `harness/rounds/` 声明（如内容量超阈值触发维护轮），
  产物落 content/。

## git 边界

判据一句话：**git 管人要读历史的，不管机器要重放的。**

| 部分 | git？ | 理由 |
|---|---|---|
| `surface/content/` | ✅ | 模型工作的演进史；**每 Round 一个 commit**（runtime 提交，message 带 round id + 事实区间 digest，内容↔因果可对照） |
| `harness/` | ✅ | 策略代码演进需人审；`work.json` 的 digest 钉住准入版本，git 管"怎么变来的" |
| `work.json` | ✅ | 绑定/授权/关系变更史 = 管理审计 |
| `surface/facts.jsonl` | ❌ | 已是 append-only 历史，git 版本化冗余；重放靠它自己 |
| `session/`、`ledger/` | ❌ | 观测域/运行记录，无 diff 价值 |
| `derived/` | ❌ | 可重建，版本化无意义 |

整个工作目录 = 一个 git repo（`facts/` `session/` `ledger/` `derived/` 进 ignore）——
repo 边界 = 工作边界，可移植性不破坏。

## 各目录明细

- **`session/rounds/<round-id>.jsonl`**：每轮模型交互（消息、工具调用、token 用量）。
  观测域：审计、仪器、调试用它；接续与 Projection 不依赖它。
- **`ledger/admission.jsonl`**：外来事件去重账——Fact Admission 幂等性的机制所在。
- **`ledger/rounds.jsonl`**：轮记录——轮级恢复与审计靠它。
- **`derived/projection-cache/`、`derived/index/`**：投影产物落盘（观测仪器钉在其上）
  与 recall 索引；整个 derived/ 随时可删重建。
- **`work.json`**：唯一"既是数据又是配置"的文件，git 管变更史。

## 待定机制题（进入组件合同时逐项裁决）

1. 事实流分片策略（按量/按时间滚动），接续重放语义不变；
2. revision 粒度（默认每 Round 一个快照；工具调用级是否留痕交 conventions）；
3. 关系允许的双向性：B 受理 A 的事实，允许记录记在谁的 work.json
   （倾向 B 声明 wants、A 侧 grants，归 admission 合同）；
4. 归档区位置：框架不设 `surface/archive/`，由各工作 conventions 决定
   （助手工作 `content/archive/`，编码工作可不需要）；
5. session/ 观测数据的保留与修剪策略。


---

# 5. 落盘机制 v2
> 来源：design/g3/work-directory-landing.md 原文（v2 补全草案）

# 工作目录：落盘机制与设施归属（v2 补全草案）

地位：[work-directory.md](work-directory.md)（v1，2026-09-16 对话裁决定稿）的补全件——v1 定了框架（框架固定/内容自由、目录树、写者归属、拓展点映射、git 边界、T2 外置），本件补它没有回答的另一半：**目录与既有组件设施（R/E/F/S/X）的关系、持久分区、逐文件规范、原子性、生命周期、权限矩阵、五个机制题的裁决，以及可机检不变量与预登记用例**。
状态：**DRAFT，无实现、无验证证据**；全部为设计判断或候选工程决策，不表示任何性质通过。v1 已裁决的框架原则不改；凡本稿修订 v1 处，集中在 §12 列出以待裁决，不静默覆盖。

来源与权威次序（冲突时按此排序，不按文档新旧）：v5 目标与不变量 → G1 顶层合同 → glossary v3.2 概念 → 各组件 G3 合同 → v1 工作目录框架。本件属最后一层的机制细化，**其中固定下来的目录名/文件名是 G3 组件级选择，可经修订更改，不上升为 v5 级不变量**（v5:349 明确目录名、每步 Git 提交等不冻结；v5:343 目录布局本身即待验证选择）。

### 0.1 硬约束 vs 候选（2026-09-16 用户："不要过早限制，宁缺毋滥"）

| 类别 | 内容 |
|---|---|
| **硬**（改变即改目标/语义） | L0 必需骨架与缺失语义（§4.1）；事件是唯一推进与接入契约 E1–E5（§4.4）；事件为状态权威（§4.4）；保留名与命名空间原则（§4.5）；不变量 I1–I8（§11）；"能力只用通用原语表达，缺则补原语而非领域目录"（§4.3） |
| **候选**（宁缺毋滥，等证据/实现再定） | L1 标准点清单（`conventions/projection/organization/rounds/admission/logic` 之外是否加 `tools/budget/views/presentation`）；manifest 的字段名与层级（§4.5 仅示意）；`views` 的 `source`/`resolver` 取值空间（§4.7）；具体设施落点（§2）；`surface/facts/` 分片命名（§9-1）；revision 机制 D2（§9-2） |

**佐证方式**：不靠争论，靠 [harness-catalog/](harness-catalog/)——每个文件讨论一种 harness 如何只用通用原语定义；定义不出来的地方，就是通用原语缺口，回补原语、**不加领域目录**。其中 [system-design.md](harness-catalog/system-design.md)（自顶向下系统设计）是 Surface 模型的最强验证：**有界投影 + 冻结/修订 + 条件受理**直接对应"模型不局部改、整体重写导致面目全非、收敛不到最终设计"这一实际病。

---

## 1. 事实基线：今天不存在 work-root

经源码核对（只读盘点，未改动）：

- 运行时的根是**分别配置**的：`bootstrap.assemble` 要求 `runtime{control_db, files_dir, execution_dir, session_dir, engine_endpoint, nats_url, authority, worker_id, event_profile}`、`startup_root`、`provider` 等，`Runtime.__init__` 再逐项复核路径与所有者根一致（`lore_runtime/bootstrap.py:59-95`，`lore_runtime/runtime.py:27-36`）。
- 实际落盘以 `sha256(具体 id)` 为键，**没有任何 `work_id` 或工作根**：R 控制库（`lore_control/storage.py:8,24-33`，登记含 realpath/dev/ino，`lore_control/registration.py:22,34`）、E 的 NATS stream `<prefix><ns>`（`lore_events/service.py:41-63`）与输入发布 `<input_root>/<sha256(invocation)>/{events.jsonl,invocation.json,execution-targets.json,manifest.json}`（`lore_events/input_files.py:7,18-30`）及 `.puback` 回执（`lore_events/receipts.py:9`）、S 快照库 `confirm-<sha256(request_id)>/…`（`lore_session/snapshots.py:99-119`）、X 执行库 `sha256(execution_id)/record.json`+blobs 与 `.slots/`、`.owner-lock`（`lore_execution/journal.py:47-100`、`slots.py:84-115`）、F `versions.git`+`artifacts/<sha256(ref)>/`（`lore_files/versions.py:14-60`）、provider wire `<sha256(effect_id)>/`（`lore_session/provider.py:111-129`）、plan 投影（`lore_runtime/session_plan_files.py:48-129`）。
- 只有 `startup_root` 已长得像工作根（`artifacts/ plans/ authority/ X-state/ E-inputs/`，`lore_runtime/startup_assets.py:42-46`）；NATS、Docker、控制库、F/S/provider 根、共享依赖卷是**有意 host 全局**的。
- 存在可复用的先例：验证驱动已把 R/F/S/provider 根放进同一个 `out/`，把 X-state/plans 放进 `host/`（`validation/system/m01_run.py:100-103`）——"每工作设施根"已被实际跑过，只是没被命名为工作目录。
- S 侧的**持久屏障已设计**：X 暂停 namespace → 导出同 exec/generation 的 Session manifest 与精确字节 → 校验后**外部持久化** → resume（`design/g3/s/contract.md:29,41`）。这条"外部持久化"至今没有指定落点；工作目录正是它的落点。

结论：v1 的目录树不是今天磁盘上已经成立的事实，而是一个**尚未接线的新分组**。补全件必须先回答"目录里的字节从哪来、和活设施谁是权威"。

---

## 2. 双层落盘模型（建议 D1）

**活层（live）**：设施持有的工作权威——E 持事件字节与顺序，R 持控制关系，S 持会话原件，F 持版本归档，X 持执行原件，provider 持传输原件。可以是 host 全局的、常驻的。
**落盘层（landing）**：工作目录内、与活层 manifest/digest **逐字节绑定**的副本或引用，对模型只读。
**T2 外部**：沙箱实例、轮执行现场、单写者租约锁、socket、Docker 对象、共享依赖卷——永不进目录。

规则：

- **L1 单一活权威**。每类事实只有一种可写权威；落盘层不产生第二种可写真相。目录副本按原所有者 manifest 绑定（事件按 E manifest 形状、Session 按 X 导出 manifest、版本按 F `version_ref`），恢复时以落盘层重建活层并逐项校验 digest；不符显式失败，不猜测、不静默补齐。
- **L2 静止点落盘**。落盘发生在 Round 边界或显式 quiesce，批量 fsync；活层与落盘层之间**不做跨设施事务**（G1:32 已声明不假设跨设施事务），用 manifest digest 比对代替分布式提交。
- **L3 目录只装工作侧持久物**。host 共享机制（NATS 服务器、Docker Engine、共享依赖卷、宿主 authority 配置）不进目录；其工作相关字节按范围导出落盘。
- **L4 目录是可移植单元，但不是授权单元**。搬走 = 接续区 + 观测区落盘；导入需**重新登记/授权**、重建活层、按引用重新提供外部 Userspace（见 §12 U5、I8）。

设施归属表（"落点"列为建议，非既有实现）：

| 活权威（今天） | 今天的配置根 | 目录落点（建议） | 分区 | 说明 |
|---|---|---|---|---|
| R 控制 sqlite | `runtime.control_db` | `ledger/control.sqlite`（每工作库）+ host 侧登记/授权索引 | A | 拆分见 U4 |
| E 事件流 | `runtime.nats_url`（全局服务器） | `surface/facts/`（范围导出 + 索引） | A | 服务器不外迁 |
| E 输入发布 | `event_profile.input_root` | `derived/input/` | C | 可由落盘 facts 重建 |
| E `.puback` 回执 | `input_root` 父目录 | `ledger/receipts/` | B | 原件、体量小 |
| S 快照库 | `runtime.session_dir` | `session/snapshots/` | B | 原件 |
| S/Pi JSONL | 快照内 `original.tar` | `session/rounds/<round-id>.jsonl` | B | X 导出屏障的落点（s:41） |
| X 执行库/归档 | `runtime.execution_dir` | `session/exec/`（引用 + 按需导出） | B/T2 | 原件在设施，冻结导出落盘 |
| F 版本库 | `runtime.files_dir` | `surface/versions.git` + `surface/artifacts/` | A | content/ 的版本机制（D2） |
| provider wire | `provider.root` | `session/provider/` | B | 传输原件 |
| plan 投影 | `startup_root/plans` | `derived/plans/` | C | 可重建 |
| Docker Engine / 共享依赖卷 | `engine_endpoint` / 绝对路径 | — | T2 | 不进目录 |

与 v5 的一致性：v5 明确 `events.jsonl` 可以是**输入视图或导出格式**（v5:131）；R 合同禁止把 NATS 事件正文复制成"竞争真相"（`design/g3/r/contract.md:7`）——本模型的落盘副本由原所有者 manifest 绑定、恢复时回灌同一稳定身份，不新增可写真相，满足该禁令。G1 允许"受控导出/缓存，但须标明来源、版本及非权威性质"（G1:32），落盘层的 `index.json`/manifest 必须记录来源设施、范围与 digest。

---

## 3. 持久分区：三分区修正（建议 D3）

glossary 的 T0/T1/T2（`design/g3/glossary.md:120-123`）：

- T0 = 权威事实：面内容+发布头、事实流、Harness、Runtime 账本；
- T1 = 派生可重建：折叠、索引、投影缓存；
- T2 = 瞬态：沙箱实例、运行现场；
- "接续集 = T0"。

**缺口**：Session 是观测域，"接续与 Projection 不依赖它"（glossary:118-119），却既不在 T0 列举里、又不可重建（不属于 T1）、更不是瞬态（不属于 T2）；而 v1 写者表把 `session/` 记作 T0（v1:51）。两处冲突。

建议分区（待裁决 U2）：

| 分区 | 内容 | 性质 | 与既有层级 |
|---|---|---|---|
| **A 接续区（carry）** | `work.json`、`harness/**`、`surface/content`+`head`、`surface/facts/`、`ledger/**` | 不受损即可接续；glossary"接续 = 从 T0 重放"的 T0 实操含义 | T0（接续集） |
| **B 观测区（observation originals）** | `session/**`（Pi JSONL、快照、provider wire、X 原件导出）、`ledger/receipts/` | 原件、不可重建、非接续依赖；审计与仪器依赖 | T0 的观测子集（glossary 现未列） |
| **C 派生区（derived）** | `derived/**` | 随时可删可重建，产物可复核 | T1 |
| （目录外） | 沙箱实例、运行现场、锁、socket、Docker 对象 | 释放即归零 | T2 |

术语修订建议：把 glossary T0 写成 **"T0 = A ∪ B（不可重建的原件）"**，并新增一句 **"接续集 = A ⊊ T0"**；或者增设 `T0o（观测原件）`。两种写法都可消除缺口，但都动到已定稿的 glossary，须独立复核。

保留纪律：B 区可按声明策略修剪/导出，但修剪必须留**墓碑**（范围 + digest + 原因 + 时间），仪器可 pin 保留下限（对齐"保留/归档不得静默破坏仍被承诺的恢复依据"，v5:123；"保留范围不得删除仍被已受理责任依赖的记录"，G1:44）；B 缺失时恢复照常，但审计/仪器必须**显式报告缺失**，不得静默补造。

---

## 4. 拓展点与目录树 v2

### 4.1 目录是下界：三层与开放规则

v1 的"框架目录固定"固定的是**语义角色**，不是**闭集**。目录是下界——**至少**要有能兑现 runtime 语义的那几项；其余允许拓展。为同时满足"框架对所有工作同构"与"策略演进不侵入底座"（v5:18；`minimal-harness-extension-points.md`"策略可整体替换，缝隙不变"），分三层：

| 层 | 内容 | 约束 |
|---|---|---|
| **L0 必需骨架** | `work.json`、`harness/manifest.json`、`surface/content`、`surface/head`、`surface/facts`（基础为单文件 `facts.jsonl`，分片是后加机制）、`ledger/`（至少 control + rounds） | runtime 必须能解析；缺失 = 非法工作，登记/恢复响亮失败。**顶层只有 4 项**：`work.json`、`harness/`、`surface/`、`ledger/` |
| **L1 默认实例与标准点** | `harness/{conventions,projection,organization,rounds,admission,logic}`（+ 待裁决的 `tools/`、`budget/`；+ 可选的 `views/`、`presentation/`，见 §4.7）、`session/`、`derived/` | **不是骨架**：有默认路径；**可缺席**（缺席 = 该能力关闭）；可由 manifest 改指；**可多实例**（多策略对比，v5:18） |
| **L2 开放扩展** | `harness/ext/<ns>/`、`derived/ext/<ns>/`、`surface/content/**`、`work.json.extensions` | 命名空间下自由；runtime **保留、不解释、不因未知而失败** |

绑定**角色**而非路径：`harness/manifest.json` 声明 `roles:{<role>:[{ref,digest}...]}` 与 `extensions:[{id,kind,ref,digest}]`；runtime 先按声明解析，未声明才回退默认路径；未知 `kind` = 惰性数据，既不报错也不执行。

保留名与冲突：顶层目录名、`surface/head`、`surface/facts`、`harness/manifest.json` 为框架保留；L2 不得遮蔽；同角色多实例以实例名区分。

缺失语义：L1 角色缺席等于该能力关闭（无 `organization/` = 不折叠、不归档）；首轮前可无 `session/`；`derived/` 可整体缺失。

**与最简 harness 拓展点清单的对齐**（`minimal-harness-extension-points.md` 的 10 点，防止两套清单漂移）：

| 拓展点 | 工作目录落点 | 归属 |
|---|---|---|
| 1 模型基线 | `work.json.model_refs`（意图）+ runtime Model Routing（供给） | 工作声明 / runtime 落实 |
| 2 每步投影 transform_context | `harness/projection/` | 工作 |
| 3 上下文工作集维护 | `harness/organization/`（策略）+ `harness/rounds/`（触发） | 工作 |
| 4 预算准入 | `harness/budget/`（标准点，待裁决；或并入 rounds） | 工作 |
| 5 截止层次 | `harness/rounds/` + 环境 profile（T2，runtime） | 分层 |
| 6 X slot 包络 | **不在工作目录**（runtime 修订） | runtime |
| 7 事件与通知 | `harness/admission/`（收什么）+ `harness/projection/`（输入视图筛选） | 工作声明 / E 落实 |
| 8 终止判定 decide | `harness/logic/`（+ `rounds/` 结束条件） | 工作 |
| 9 观测协议 | **不在工作目录**（V/外部仪器；钉在 `derived/` 产物上） | 外部 |
| 10 工具执行 | 执行**不在工作目录**（runtime X）；工具**定义**在 `harness/tools/`（标准点，待裁决） | 分层 |

结论：v1 的标准点清单漏了 `tools/`，`budget/` 归属未定；上表把 10 点逐一对齐，并把"在 runtime 侧"的点显式标注，防止误把机制塞进工作目录。开放规则的可证伪判据见 §13 VD13/VD14。

### 4.2 基础目录树（宁缺毋滥）与默认实例

**基础树：只有这 4 项是骨架（必需）**

```
<works-root>/<work-id>/
├── work.json                # 身份/绑定/策略引用/状态（可变；runtime/管理面写）
├── harness/
│   └── manifest.json        # 声明：事件词表 + 角色引用（登记后只读）
├── surface/
│   ├── content/             # 模型唯一可写区：产物（设计/文档/协议代码/笔记）
│   ├── head                 # 提交点：head → revision（原子替换）
│   └── facts.jsonl          # 事实流（append-only；分片是后加机制，不改语义）
└── ledger/                  # 运行账本：受理去重 + 轮记录（Event ≠ 私有账本）
```

**按需位置**（出现即合法，不出现也合法）：`session/`（观测原件；接续不依赖，审计/仪器/无损归档用）、`derived/`（可重建：投影产物、索引、召回）。
**目录外**：Userspace 授权范围；T2（沙箱实例、轮现场、租约锁、socket）；host 共享机制（NATS/Docker/共享依赖卷/宿主授权配置）。

**为什么恰好是这 4 项**——不是分类学，是四条硬测试：

| 测试 | 问题 | 结论 |
|---|---|---|
| 存活 | 不拷它还能接续吗？ | `work.json`、`harness/`、`surface/`、`ledger/` |
| 权限 | 模型能写吗？ | 只有 `surface/content/` 可写 → 必须能单独挂载 |
| 语义 | 回答"现在是什么 / 为什么 / 运行记录"？ | content / facts / ledger 三者**互不可替，不能合并** |
| 拓展 | 新能力能只靠声明表达吗？ | 能 → **不加目录**（9 个示例，0 个新增顶层目录） |

**默认实例**（最小 harness 的完整形态，**不是骨架**；子目录可缺席、可改指、可多实例）：

```
<works-root>/<work-id>/                       # 目录名 = work_id；稳定、可移植、仅 [-._A-Za-z0-9]
├── work.json                    [A] 身份/绑定/策略引用/关系声明/状态/落盘边界；无密钥无端点
├── harness/                     [A] 推进定义（登记后只读，模型不可写）
│   ├── manifest.json            #   入口与各策略引用 + 自身 digest
│   ├── conventions/ projection/ organization/ rounds/ admission/ logic/
│   │                            #   标准拓展点：默认路径，可缺席、可改指、可多实例
│   ├── views/ presentation/     #   [可选标准点] 信息项声明与形式装配（§4.7）；缺席=只用 L0 最低信息
│   ├── tools/                   #   [标准点，待裁决] 工具定义与交互解析
│   ├── budget/                  #   [标准点，待裁决] 预算与截止声明
│   └── ext/<ns>/                #   [L2 开放] 工作自定义拓展（runtime 保留不解释）
├── surface/                     [A] Surface 1:1
│   ├── content/                 #   模型唯一可写区（经 Surface 域 Shell）；内部结构由 conventions 决定
│   ├── head                     #   提交点（原子替换）：revision_ref + facts_end + round_id + ledger_seq
│   ├── facts/                   #   事件范围导出：seg-<start>-<end>.jsonl + index.json（E manifest 形状）
│   ├── versions.git/            #   [机制候选 D2] F 版本归档库
│   └── artifacts/<sha256(ref)>/ #   [机制候选 D2] F 归档原件 archive.tar + manifest.json
├── session/                     [B] 观测原件
│   ├── rounds/<round-id>.jsonl  #   每轮 Pi 原字节导出（X pause→export 屏障的落点）
│   ├── snapshots/               #   S 快照库（original.tar + 4 JSON + charge/owner/result）
│   ├── provider/                #   provider 传输原件
│   ├── exec/                    #   X 执行原件/冻结导出（引用或按需拷贝）
│   └── blobs/<sha256>           #   大对象按 digest 存原字节，不内联进 jsonl
├── ledger/                      [A] 运行账本（不是事实）
│   ├── control.sqlite           #   R 控制库（每工作根；host 登记/授权索引在目录外，见 U4）
│   ├── admission.jsonl          #   外来事件去重账（接受行可由 facts 重建；拒绝行是原件）
│   ├── rounds.jsonl             #   轮记录：触发求值、起止、attempt、Grant 快照、计量
│   └── receipts/                #   [B] 设施回执原件
├── derived/                     [C] 可重建（随时可删）
│   ├── projection-cache/ index/ plans/ input/ recall/
└── (目录外) Userspace 范围 | T2：沙箱实例、轮现场、单写者租约锁、socket
```

**场景证据（harness-catalog/ 9 个示例，全部只用基础树，无新增顶层目录）**：

| 示例 | 用到的基础位置 | 新增顶层目录？ |
|---|---|---|
| goal | `work.json` / `harness/` / `facts` / `content/` / `ledger/` | 否 |
| plan | 同上（spec 在 content，状态在 facts） | 否 |
| archive | `content/` / `facts` / `derived/`（按需）/ `session/`（按需） | 否 |
| ask-user | `facts`（外部受理）+ 等待（本就不需要目录） | 否 |
| coding | `content/`（笔记）/ `facts` / `session/`（工具结果）/ Userspace（目录外） | 否 |
| research | `content/`（素材）/ `derived/`（索引）/ `views`（声明） | 否 |
| delegation | `work.json`（关系）/ `facts` / 对方工作目录（目录外） | 否 |
| monitoring | `facts` + 触发条件（无目录） | 否 |
| system-design | `content/`（设计本体）/ `facts`（决策·修订）/ `head` | 否 |

结论：**能力都长在 `harness/` 的声明与 `content/` + `facts/` 的数据里，不产生新顶层目录**；示例暴露的是**通用原语缺口**（backlog B14），不是目录缺口。

**Userspace 不在工作目录内**：v5/G1 把 Userspace 定义为独立的"授权文件范围引用"（v5:38、G1:25），`work.json` 只存 owner/kind/身份/版本引用；目录可移植不等于外部 Userspace 可移植，导入时按引用重新提供或显式拒绝（见 U5）。

### 4.3 示例：在目录上定义一个 harness（goal 模式 / plan 模式）

**先纠一个方向（用户 2026-09-16 纠正）**：目标（goal）与计划（plan）**不是框架要认识的目录**。它们是"在这个目录结构上怎么定义一个 harness"的**示例**——用框架的**通用拓展机制**定义出来，框架不因它们新增任何标准点。本件早期草稿曾把它们提升为 `harness/goal/`、`harness/plan/`、`harness/events/` 三个"标准点"，那是把领域策略写进底座，违反 v5:18 与 v5 §5.4"Runtime 不内置策略"。**该错已撤回，记录保留于此**（不掩盖不利记录）。

**示例 A：goal 模式**——一个 harness，用通用点表达"目标 + 完成事件 + 验收引用"：

| 它要做的事 | 用哪个通用点 |
|---|---|
| 定义自带事件（`work.completed` 等） | 声明：manifest 的 kind + Fact Contract 引用（P1） |
| 完成声明进门、去重 | `admission` 规则（P2） |
| 何时继续、何时不再开轮 | `rounds` 的 Trigger Condition 与结束条件（P3） |
| 把当前目标/阶段渲染给模型 | `projection`（P4） |
| 目标状态机、验收条件引用 | `logic` 前置逻辑（P5） |
| 目标/阶段身份稳定 | 事实 id + revision（P6） |
| 人类可读记录 | `surface/content/`（结构由 conventions 决定） |

**示例 B：plan 模式**——同样只用 P1–P6：阶段完成是自带事件（P1/P2），"下一阶段进上下文"是投影规则（P4），何时推进是 `rounds`（P3）。**不需要框架为 plan 开后门，也绝不让 plan 变成 runtime 调度器。**

**通用原语清单（充分性检查）**：goal/plan 能被表达，靠的是这八项**通用**能力；缺哪项就补哪项**通用原语**，而不是加领域目录：

| P | 通用原语 |
|---|---|
| P1 | **声明**：manifest 可声明 harness 自有的 kind/契约/角色/扩展，未知不报错 |
| P2 | **受理**：`admission` 规则按契约收事，幂等去重 |
| P3 | **触发**：Trigger Condition 在 harness 自有谓词上求值（runtime 按声明，不内置语义） |
| P4 | **投影**：把 harness 自有当前态渲染进上下文 |
| P5 | **前置逻辑**：轮前/步内任意判断（含状态机） |
| P6 | **身份**：事实带稳定 id/revision，可审计、可重放、可跨轮引用 |
| P7 | **观测事实**：runtime 产生声明式观测，harness 消费（见下边界 4） |
| P8 | **保留名**：框架保留前缀 + 扩展命名空间，防遮蔽 |

**示例带出的边界（适用于任何 harness 定义，不只 goal）**：

1. 形如 `work.completed` 的是 **harness 声明的事件**，不是 runtime 通用终态。v5:161 明确 `ready/done/fail` 不是每个 Harness 必须接受的 Runtime 业务语义；v5:208"没有通用 Surface 终态要求"。Runtime 只做三件事：产生观测事实、按声明求值触发条件、按声明投影。
2. **"完成" ≠ Work 不活**。Work 的"不活"只有管理动作 Archive（glossary Work 边界）；该事件至多让这个 harness 不再开轮，工作仍在册。
3. **完成声明不构成业务验收**。验收独立（V/外部验收器）；Runtime 只记录声明与证据引用（GOAL §4；AGENTS.md"禁止以应用声明证明完成"）。
4. **"上下文窗口接近"这类是 runtime 的声明式观测事实（P7）**：阈值由 harness 配置（领域调参），runtime 跨阈值落事实，是否开组织轮由 harness 的触发条件决定；**不是 runtime 注入固定文本**（这保持 `minimal-harness-extension-points.md` §3"缝隙在宿主、策略可换"，并满足 O6 可观测性）。

**可证伪判据（见 §13 VE01–VE05）**：示例 harness 只用 P1–P8 即可表达；**若必须新增框架目录才能表达，判为"框架缺通用原语"，补 P 项而不是补领域目录**。

**V-A 已裁决（2026-09-16）**：实例状态权威在**事件**，见 §4.4。`content/` 只放产物与渲染，Projection 由事实派生当前态。

### 4.4 事件是唯一的推进与接入契约（用户 2026-09-16 裁决）

用户裁决："我们都是基于事件的……推进也是一样；事件是接入实现的最好方式，不然就搞乱了。"本框架据此固定以下规则（与 v5/glossary 既有主线一致：Trigger Condition 是事实流上的谓词，glossary:64-66；一切事实落面，glossary:31；回放只恢复已记录事实、不重做其中动作，v5:163）：

| 规则 | 内容 |
|---|---|
| **E1 进来只有一个门** | 外来、跨工作、系统观测一律经 Fact Admission 落面；没有 Fact Contract 的事件进不来（无法校验、路由、安全消费） |
| **E2 出去也走事件** | harness 的结论——含"阶段推进""完成"这类声明——落为**声明事件**，不是直接改状态、不是直接调 runtime |
| **E3 推进由事件触发** | Round 的开始是 Trigger Condition 在事实流上求值的结果（不是轮询、不是进程唤醒）；结束由 `rounds` 逻辑决定，产物仍是事件 |
| **E4 接入面 vs 调用面** | **事件是 harness 的接入契约**（收什么、发什么、什么触发）；**roles 是 runtime 的调用契约**（怎么调用 harness 的代码）；两者都在 manifest 声明 |
| **E5 内容不是侧信道** | `content/` 是产物（笔记/报告/代码），由事件**引用其版本**（revision_ref）；不能靠"模型改了文件"隐式改变推进语义 |

**三种情况必须分清（否则"全事件化"就乱了）**：

1. **产物 vs 状态**：`content/` 继续回答"现在是什么"——指**产物**；**推进状态**（阶段、完成、目标 phase）由**事实**回答。两条不冲突，别把状态又塞回文件。
2. **面事实 vs 局部事实**：Session／执行器／工具往返是**局部执行事实**，属观测域，通过**引用**进入面；不复制成第二套面事件流（R 合同禁止竞争真相，r:7）。否则"全事件化"会变成两套事件流。
3. **不是每次文件写入都事件化**：内容写入不逐条事件化（流水爆炸）；轮提交点由 revision + 轮记录引用；只有**语义声明**（阶段推进、完成、受理决定）才是事件。

**推论**：manifest 的核心是**事件声明**（kinds + contracts + triggers + admission），roles 退为调用面；P1（声明）与 P2/P3（受理/触发）成为最关键的三项原语。

### 4.5 manifest：事件声明与解析规则（2026-09-16 裁决：声明优先 + 保留前缀 + 扩展命名空间）

**形态（示意，字段名为 G3 候选，须进组件合同）**：

```json
{
  "schema": "lore-harness/v1",
  "entry": { "ref": "logic/main.mts", "digest": "sha256:…" },
  "facts": {
    "kinds": [
      { "kind": "work.completed",
        "contract": { "ref": "contracts/work-completed.json", "digest": "sha256:…" },
        "producer": "harness" },
      { "kind": "sys.context.window.approaching",
        "contract": { "ref": "<框架随版本提供>", "digest": "sha256:…" },
        "producer": "runtime" }
    ],
    "triggers": [
      { "id": "goal-progress",
        "on": ["work.completed", "sys.context.window.approaching"],
        "when": { "ref": "triggers/goal.mts", "digest": "sha256:…" } }
    ]
  },
  "views": [
    { "id": "goal-state", "source": "facts.query",
      "resolver": { "ref": "views/goal.mts", "digest": "sha256:…" } }
  ],
  "roles": {
    "conventions":  [ { "id": "default", "ref": "conventions/", "digest": "sha256:…" } ],
    "projection":   [ { "id": "ctx",     "ref": "projection/ctx.mts", "digest": "sha256:…" } ],
    "organization": [ { "id": "archive", "ref": "organization/archive.mts", "digest": "sha256:…" } ],
    "rounds":       [ { "id": "continue","ref": "rounds/continue.mts", "digest": "sha256:…" } ],
    "admission":    [ { "id": "default", "ref": "admission/default.mts", "digest": "sha256:…" } ],
    "logic":        [ { "id": "pre",     "ref": "logic/pre.mts", "digest": "sha256:…" } ]
  },
  "extensions": [ { "id": "acme", "kind": "policy", "ref": "ext/acme/", "digest": "sha256:…" } ]
}
```

**解析规则**：

| 规则 | 内容 |
|---|---|
| **R1 声明优先，默认路径兜底** | runtime 先按 `roles.<role>` 解析；未声明该角色才回退约定目录（`projection/` 等）；两者都没有 = 该能力**关闭**，不是错误 |
| **R2 注册严格** | 每个 ref 必须存在且 digest 匹配；kind 的 contract 必须合法；trigger 的 ref 必须可解析。任一对不上 → **注册响亮拒绝**（不降级、不猜） |
| **R3 未知不报错** | 未声明的目录、未知 `extensions` 条目、未知字段：**原样保留、不解释、不因未知而失败**（"允许拓展"成立的前提） |
| **R4 多实例** | 同一角色可有多个条目，以稳定 `id` 区分；runtime 按声明调用（多策略对比即多实例）；`id` 参与 harness digest |
| **R5 producer 权限** | `runtime` 类只能**订阅**框架随版本提供的规范契约，不得自定义；`harness` 类必须落在自己的命名空间；`external` 类按 `admission` 规则受理 |
| **R6 digest 不自引用** | manifest **不内嵌自身 digest**；其 digest 由规范字节计算，记在 `work.json.harness.digest` 与登记记录里（【v2 修订 v1:19 的"含自身 digest"措辞】） |

**保留名与命名空间**（Q3 裁决：保留前缀 + 扩展命名空间）：

| 类别 | 保留 / 规则 |
|---|---|
| 路径 | 顶层 `work.json / harness / surface / session / ledger / derived`；`surface/{content, head, facts}`；`harness/manifest.json`。扩展只能放 `harness/ext/<ns>/`、`derived/ext/<ns>/`；`content/` 内部由 `conventions/` 决定，框架不保留具体名 |
| 事件 kind | 框架保留 **`sys.*`**（runtime 产生的观测，如 `sys.context.window.approaching`）；harness 自定义 kind 必须落在**自己的命名空间**（如 `acme.*`）。所以 `work.completed` 这个名字本身不归框架，是某个 harness 自选的 |
| 命名空间所有权 | 命名空间在 manifest 声明，**同一宿主内不得与其他已登记 harness 或保留前缀冲突**；冲突 → 注册拒绝（命名空间申请/转让机制留后续） |

### 4.6 能力怎么定义：五件套模板 + work / plan / archive 三个示例

**一个能力 = 五件套**（全部由 harness 声明，框架只提供 P1–P8 原语与 §4.5 解析规则）：

| 件 | 作用 | 落点 |
|---|---|---|
| ① 词表 + 契约 | 有哪些事件、payload schema（digest 即语义） | `facts.kinds` + contracts |
| ② 产生者 | 谁产生：**runtime 观测**（`sys.*`）／**harness 声明**（自己命名空间）／**外部受理**（外来） | kind 的 `producer` |
| ③ 触发与受理 | 什么事件开轮、什么事件被收/去重 | `facts.triggers` + `roles.admission` |
| ④ 投影 | 把"当前态"渲染给模型（给指针不灌全文） | `roles.projection` |
| ⑤ 逻辑 | 状态机、判定、门控 | `roles.logic`（+ `roles.rounds` 结束条件） |

产物是 `content/` 文件，由事件**引用其 revision**。**注意**：产生者不等于"谁都能写事实"——所有落面仍由 runtime 单写者执行；harness"产生"是调用声明过的受控入口（E1/E2）。

#### 示例 1：work 功能（工作级：进度 + 委派）

| 件 | 进度侧 | 委派侧（跨工作） |
|---|---|---|
| 词表 | `work.objective.set`（objective ref + acceptance_refs）、`work.phase.changed`、`work.completed` / `work.blocked`（附 evidence_refs） | `work.delegated`（parent/child、scope、input_refs）、`work.accepted`/`work.rejected`、`work.reported`（result_ref + 证据） |
| 产生者 | 外部受理（objective）+ harness 声明（progress/completed） | harness 声明（delegated/reported）+ 对方受理（accepted/rejected） |
| 触发 | `objective.set` → 开第一轮；`completed` → `rounds` 不再开轮 | `accepted`/`reported` → 开父工作轮 |
| 投影 | 当前 objective + phase + 验收清单 + 证据指针 | 子工作状态摘要 + 结果引用 |
| 逻辑 | phase 状态机；验收引用解析（谁验不归它） | 关系声明（wants/grants）、超时/取消判定 |
| 边界 | `work.completed` 只是声明，不是 runtime 终态（§4.3 边界 1–3） | 委派 = 两 Work 间事件受理，**无中心行动者**；**不继承授权**（B 的 wants + A 的 grant；副本不带授权） |
| 反例 | 把 `work.completed` 当 runtime 终态 | 父工作直接写子工作 `content/`；凭 `work.json` 文本继承授权 |

#### 示例 2：plan 功能

| 件 | 内容 |
|---|---|
| 词表 | `plan.created`/`plan.revised`（stages[]）、`plan.stage.started`、`plan.stage.completed`（stage_id + evidence_refs）、`plan.completed` |
| 产生者 | 外部/模型经受理（创建/修订）+ harness 声明（阶段推进） |
| 触发 | `plan.stage.completed` → **开一轮，把下一阶段投影进上下文**（你原话的落法） |
| 投影 | **只投影当前阶段 + 紧邻下一阶段**（有界），全 plan 给指针 |
| 逻辑 | 阶段门控（完成条件、证据要求）、顺序、修订处理 |
| 边界 | plan **不调度**（推进由 rounds 触发）；修订只追加不改写历史；spec 可以是 content 文件（版本引用），但**当前阶段是事件** |
| 反例 | 把 plan 做成 runtime 调度器；把全 plan 塞进上下文；阶段完成只看模型自述 |

#### 示例 3：archive 策略（上下文控制）

| 件 | 内容 |
|---|---|
| 词表 | `sys.context.usage`、`sys.context.threshold.crossed`（window/used/threshold/soft\|hard，runtime 规范契约，**阈值由 harness 配置**）、`archive.requested`（模型主动）、`archive.performed`（what/from/to、`fold_digest`、`original_refs[]`、`mode: lossless\|lossy`） |
| 产生者 | runtime 观测（`sys.context.*`）+ harness/模型声明（`archive.*`） |
| 触发 | `sys.context.threshold.crossed(soft)` 或 `archive.requested` → 开维护轮；硬阈值行为由 harness 决定，不是 runtime 硬编码 |
| 投影 | 折叠后投影"摘要 + 指针 + 尾部保留"；完整原文经工具按需取回 |
| 逻辑（`organization`） | 折叠/归档策略：**threshold archive 无损**（原文仍在 content/session，只缩视图）；LLM 摘要**有损**，必须记 `fold_digest` 与 `original_refs` |
| 边界 | 裁剪**只改可见视图，不删恢复依据**（v5:252）；折叠产物是**记忆本身，落 `content/`（T0）**，不进 `derived/`（T1 缓存）；触发由 `rounds` 声明 |
| 反例 | 用 `derived/` 当归档区；摘要丢原文且无指针；runtime 硬编码阈值或注入固定压力文本 |

#### 三个示例的共同骨架

| 能力 | 词表 | 产生者 | 触发 | 投影 | 逻辑 |
|---|---|---|---|---|---|
| work | `work.*` | 外部 + harness | objective.set / reported | 目标状态 + 验收清单 | 状态机 + 委派授权 |
| plan | `plan.*` | harness + 外部 | stage.completed | 当前 + 下一阶段 | 阶段门控 |
| archive | `sys.context.*` + `archive.*` | runtime + harness | threshold.crossed | 摘要 + 指针 + 尾部 | 折叠策略 |

**结论**：能力不是框架目录，也不是 runtime 分支；能力 = **词表 + 产生者 + 触发 + 投影 + 逻辑**，全部在 harness 里声明。这与你的理解一致，只多两处必须钉住：**产生者要分三类**（否则系统观测和应用声明会混为一谈），**投影与逻辑要分开**（一个给模型看什么，一个决定推进）。

### 4.7 给模型看的信息：信息项 / 投影 / 呈现（分开定义，约束从轻）

用户 2026-09-16："给模型看的信息也需要投影给模型；是否与投影分开定义——最好分开，但也不想去限制。"三层落地：

| 层 | 回答什么 | 落点 | 约束 |
|---|---|---|---|
| **① 信息项**（what can be shown） | 有哪些东西可供展示：当前目标/阶段状态、事件视图、前序反馈、用户空间快照、检索结果、系统观测…… | manifest `views` 声明 + 可选 `roles.views`（解析器） | **从轻**：只要求稳定 `id`、来源可定位、解析器可寻址、产物可观测、缺失显式；**不定义视图类型学、不规定 schema 语言、不限数量命名** |
| **② 投影策略**（what is shown now） | 本轮/本步选哪些、给多少、什么顺序与优先级 | `roles.projection` | 有界（成本挂 Round）；给指针不灌全文；保形合同（非投影形状返回 invalid_input） |
| **③ 呈现**（how it is shaped） | 内容 → 特定模型请求形式（prompt 拼装、协议字段、模态包装） | `roles.presentation`（可选，缺省 = 默认装配） | 只改形式、不得改内容（glossary Projection ≠ Presentation） |

**L0 已要求的最低信息**：v5:204 固定运行时必须提供"当前 Surface 目录、事件与反馈位置、获准执行目标、当前推进与局部记录引用、必要限制"。这五项**不需要 harness 声明就存在**；`views` 只用于**额外**信息项。

**"不想限制"的具体含义**：

- 不规定视图种类、数量、命名法；`views` 缺席 = 只用 L0 最低信息，**完全合法**。
- 不规定解析器语言（普通代码 + 引用即可），不要求每个视图有固定 schema；只要求**产物可观测**（落 `derived/`、仪器可钉）与**缺失显式**。
- 信息项对模型**只读**；想看更多用工具按需深挖（v5:250 不预展开全量目录与全文）。

**与 archive 示例的衔接**：折叠改变的是 `content/` 里的记忆本体与 `views` 解析到的内容；**视图声明本身不变**——"折叠后只投影摘要 + 指针 + 尾部"是②投影策略的选择，不是①视图定义的改写。

**对五件套的补充**：能力定义里的"④投影"现在明确为**在已声明的信息项上做选择与装配**；需要新信息项时**加 `views` 声明**，而不是把领域字段塞进投影代码。

---

## 5. 逐路径规范

| 路径 | 格式 / 命名 | 写者 | 区 | 原子性 | 回收 / 保留 |
|---|---|---|---|---|---|
| `work.json` | JSON `lore-work/v1`：`layout_version, work_id, namespace, identity, harness{ref,digest}, model_refs{}, userspaces[], relations{wants[],grants[]}, state{lifecycle:active\|archived}, landing{boundary,last_round}, policy{session_retention}` | Runtime / 管理面 | A | 临时文件 + rename | 变更史入版本；禁密钥/端点（glossary:100-102） |
| `harness/manifest.json` | JSON：entry + 各策略 ref + 自身 digest | 登记时一次写入 | A | 写一次 | 登记后只读；改一字节 = 新版本 = 新绑定（glossary:43） |
| `surface/content/**` | 由 `conventions/` 决定（如 `journal/ + index.md`、`src/ + tests/`） | 模型（经 Surface 域 Shell） | A | 由 D2 机制在边界捕获 | 每 Round 一个 revision（默认） |
| `surface/head` | JSON：`{layout_version, revision_ref, facts_end{segment,offset,digest}, round_id, ledger_seq}` | Runtime | A | tmp + fsync + rename + dir fsync | 唯一提交点 |
| `surface/facts/seg-*.jsonl` | 每行：`{namespace, sequence, event_id_digest, bytes_digest, received_at, foreign_id?}` | Runtime（从 E 读端导出） | A | sealed 段不可变；open 段追加 fsync | sealed 不重编号；阈值见机制题 1 |
| `surface/facts/index.json` | 段范围 → digest、去重键、导出 manifest 引用来源设施/版本 | Runtime | A | 原子替换 | 重建入口 |
| `session/rounds/<round-id>.jsonl` | X 冻结导出的原 Pi JSONL 字节 + manifest digest | Runtime（S/X 屏障） | B | 写一次（O_EXCL） | Pi append 无 fsync，必须走导出屏障（s:29,41） |
| `ledger/control.sqlite` | 沿用 R 合同：WAL、`synchronous=FULL`、`BEGIN IMMEDIATE` | R | A | SQLite 事务 | quiesce 后 checkpoint 再拷 |
| `ledger/admission.jsonl` | 行：`{foreign_id, source, digest, decision:accepted\|rejected, fact_ref?\|reason, at}` | Runtime（R 规则驱动） | A/B | 追加 fsync | 接受行可由 facts 重建（T1 性）；拒绝行是原件（B） |
| `ledger/rounds.jsonl` | 行：`{round_id, trigger_eval, attempts[], grant_snapshot, facts_range, session_round_digest, revision_ref, metrics}` | Runtime | A | 追加 fsync | 轮级恢复与审计 |
| `derived/*` | 命名含输入 digest 集（cache key） | Runtime | C | 可部分写 | 删除重建须字节/digest 稳定 |
| 单写者租约锁 | 目录外 runtime spool `<locks>/<work-id>.lock` | Runtime | T2 | flock | 不进目录（拷贝不携带锁） |

---

## 6. 原子性与崩溃一致性

Round 提交顺序（默认，`§9-2` 允许 conventions 声明变体）：

1. Harness 前置逻辑（可选）与轮内 content 写入；
2. 本轮新事实**导出**到 `surface/facts/`（追加 + fsync）；
3. content revision 捕获（D2：F `capture` 或 worktree commit）→ `revision_ref`；
4. Session 轮字节落盘（X pause→export 屏障）→ manifest digest；
5. `ledger/rounds.jsonl` 追加轮记录（含 2–4 的范围/digest）+ fsync；
6. `surface/head` 原子推进（tmp + rename + dir fsync）——**读点即 head**；
7. 释放本轮沙箱与环境（T2 归零）。

- **未提交尾部**：head 之后出现的 facts/session 属 in-flight；恢复时按 G1 恢复边界表处理（"已交出、结果未确认 → 查询；无安全恢复能力则显式暂停，不把重推理/重跑冒充恢复"，G1:50-61、v5:332,336）。
- **撕裂尾行**：只承认完整行；尾部残行截断并在 `ledger/admission.jsonl` 或 repair 记录中**显式留痕**，绝不把半行 JSON 当事实。
- **幂等**：受理去重以稳定外来身份为准；接受行可从落盘 facts 重建，重复交付回到同一身份（E:17、R:76）。
- **单写者**：每工作一份目录外租约锁 + head CAS；检测到并发写者拒绝推进，不静默覆盖（v5:71、G1:88）。
- **跨设施非原子**：按 L2 用 manifest digest 比对，不引入分布式事务；失回执一律先按原身份查询（G1:38、R:31）。

---

## 7. 生命周期与身份

- **create**：从模板实例化 `harness/`（含 manifest digest）+ conventions 决定的 `content/` 骨架 + `work.json`（`layout_version`）。
- **register**：host 侧登记与授权（R），绑定 harness digest、Userspace 引用、model refs；登记不隐含启动（v5:210）。
- **run**：求值 Trigger Condition → Harness 前置逻辑（可选）→ ≥0 Step → 按 §6 提交。
- **quiesce / land**：Round 边界已是静止点；显式 quiesce 额外把 host 全局设施的工作相关范围导出落盘（事件范围、快照、回执）。
- **archive**：管理动作——数据保留、停止求值/受理（glossary:67-68）；**是状态不是目录**。
- **export / import**：quiesce 后拷贝目录即导出；导入到新宿主需重新登记/授权、重建活层、校验 digest、按引用重新提供 Userspace（AGENTS.md：新环境重新生成路径与物理身份，不复制旧 inode/device）。
- **delete**：显式动作；不得删除仍被已受理责任或其他工作引用依赖的记录（E:11、G1:44）。

身份收束：`work_id` ↔ `namespace` 1:1（最小情形），`session_scope=(namespace, surface_id, session_id, session_generation)`（`lore_session/snapshot_files.py:15`）。这回答了盘点中"代码里 work id 意图不清"：**work_id 是目录与移植的单位，namespace 是登记/授权的范围，二者在工作目录里显式绑定**。

三种 "archive" 禁混：工作级 Archive（不活，管理状态）、内容级归档（organization 策略产物，conventions 决定）、设施 archive（F/X 的原件归档）。框架不设 `surface/archive/`（v1:123 保留）。

---

## 8. 挂载与权限矩阵

| 路径 | Runtime 控制进程 | 模型 Surface 域 Shell | 工作沙箱（Userspace 域） | 观测器 |
|---|---|---|---|---|
| `surface/content/` | RW | **RW（唯一）** | ✗ | RO |
| `surface/facts/` | RW（导出） | RO（经本轮输入视图） | ✗ | RO |
| `surface/head`、`versions.git/`、`artifacts/` | RW | ✗ | ✗ | RO |
| `harness/` | RW（仅登记时） | RO | ✗ | RO |
| `session/`、`ledger/`、`work.json` | RW | ✗ | ✗ | 按授权 RO |
| `derived/` | RW | RO（可选） | ✗ | RO |
| 目录外 Userspace 范围 | 协调 | ✗ | RW | 按授权 |

【v2 修订 v1:60】v1 写"沙箱只挂载 content/"；按 v5/G1 的双 Shell 模型，写 Surface 的是**经授权的 Surface 域（Runtime）Shell**，工作沙箱写的是 Userspace/输出/临时区、**默认不挂载工作目录**（v5:70,184，G1:84）。目录边界即权限边界，只读性按挂载落实（v1 设计陈述 2 的原则不变）。

---

## 9. 机制题裁决（v1 §待定 1–5）

1. **事实流分片**：sealed 段按记录数或字节阈值（harness 配置，属领域调参；默认值待测，参照现有 8192 行/8 MiB 量级不预设 SLA），命名单调 `seg-<start>-<end>.jsonl`，**不重编号**；open 段未满不 seal；接续语义 = 按 `index.json` 顺序拼接 + 逐段 digest 校验（v1"按量/按时间滚动，接续重放语义不变"落地）。
2. **revision 粒度**：默认每 Round 一个 revision；工具调用级留痕是 conventions 选项；无论哪种，`head` 默认只在 Round 提交点推进，message/记录绑定 `round_id` + facts 范围 digest（v5:349 不冻结每步提交）。
3. **关系双向性**：消费侧 `wants` 记在 B 的 `work.json`，授权侧 `grants`（含 grant generation）记在 A 的 `work.json`；受理时由 Runtime 查 A 的**当前** generation；**副本不继承授权**——A 离线或未在新宿主重授权时，B 的 wants 不生效（见 I8）。细节归 admission 合同。
4. **归档区位置**：框架不设 `surface/archive/`；工作级 Archive 是状态、内容级归档由 conventions、设施 archive 是原件，三者不混。
5. **Session 保留/修剪**：策略声明在 `work.json.policy`（值可由 `harness/rounds` 声明）；默认全留于 B；修剪须留墓碑（范围+digest+原因）、尊重 pin 下限、缺失可发现；大对象走 `session/blobs/<sha256>`；导出可省略观测区，但导入必须报"观测缺失"。

---

## 10. 布局版本与迁移

- `work.json.layout_version` 是布局唯一版本号；目录名/框架布局属 **runtime 语义**，变更须随 runtime 版本提供迁移，未知更高版本**响亮拒绝**，更低版本迁移或显式只读。
- harness digest 与 `work.json` 绑定；换 harness = 新绑定版本，进行中的 Round 不静默换策略（G1:40）。
- 物理身份不落盘为权威：登记的真实根/dev/ino 是 **host 侧**登记事实，导入新宿主必须重新观测生成（AGENTS.md 平台约束；F:21 跨环境身份映射须显式指定并验证）。

---

## 11. 可机检不变量（草案，未验证）

| ID | 不变量 | 观测方式 |
|---|---|---|
| I1 | 接续自包含：quiesce 目录 + 重新授权可在新宿主重建活层并通过 digest 校验 | 迁移后逐项比对 facts/head/harness/ledger |
| I2 | 无宿主耦合：目录内无密钥、无绝对宿主路径（除 `work.json` 显式标注的 host-bound 引用）、不依赖 dev/ino | 扫描 + 导入不复制物理身份 |
| I3 | 权限边界：模型 Surface 域只写 `content/`；对其余 A/B 路径写尝试被拒且字节不变 | 外部观测文件系统与挂载 |
| I4 | `head` 是唯一提交点，且其引用的 revision/facts 范围/session 摘要均已落盘且 digest 匹配 | 崩溃注入后核对 |
| I5 | `derived/` 删除重建后同输入产出字节/digest 稳定 | 删后重建比对 |
| I6 | 观测区缺失显式：B 缺失时审计/仪器报缺失，不静默补造 | 删除后运行仪器 |
| I7 | 版本边界：目录 = 一个版本边界；facts/session/ledger/derived 不入内容演进史 | 版本库成员核对 |
| I8 | 授权不迁移：复制目录不产生授权，导入须重新登记/授权 | 未重授权导入必须拒收 |

---

## 12. v1 修订清单与待裁决

### 12.1 对 v1 的修订（建议，待裁决）

| v1 表述 | v2 修订 | 依据 |
|---|---|---|
| 写者表 `session/` 记 T0（v1:51） | `session/` 归观测区 B；glossary T0 未列 Session | glossary:118-123；§3 |
| "拷走目录 = 搬走完整工作"（v1:40,105） | 搬走 **A 接续区 + B 落盘**；授权、host 机制、外部 Userspace **不随目录迁移** | E/R 授权在 host 侧（e:7、r:9）；Userspace 是外部引用（v5:38、G1:25） |
| "整个工作目录 = 一个 git repo（facts/session/ledger/derived 进 ignore）"（v1:104） | 目录 = 一个**版本边界**；机制可以是 F `versions.git`（capture profile 决定成员）或 worktree git + ignore，二选一（U3） | F 合同已把版本固定为 Git 对象+archive+manifest（f:38、f/manifest-contract.md）；避免同内容双 git |
| "沙箱只挂载 content/"（v1:60） | 写 content/ 的是 Surface 域（Runtime）Shell；工作沙箱只见 Userspace 范围，不见工作目录 | v5:70,184；G1:84；§8 |
| 目录树里只有 `surface/facts.jsonl` 单文件（v1:30） | `surface/facts/` 段目录 + `index.json`；单文件是退化情形 | 机制题 1 |
| `harness/manifest.json`"含自身 digest"（v1:19） | manifest **不内嵌自身 digest**；digest 由规范字节计算，记在 `work.json.harness.digest` 与登记记录 | §4.5 R6（自引用不可能） |

### 12.2 待裁决（根本级；需用户或独立复核）

- **U1（核心）D1 双层落盘模型**：目录 = 工作侧 T0 落盘层 + 每工作设施根，host 共享机制保留在目录外。这是"目录与既有设施关系"的根决策，直接决定后续实现形态。
- **U2 D3 三分区与 glossary T0 修订**：Session/观测原件现在无层级可归；建议 `T0 = A ∪ B，接续集 = A` 或新增 `T0o`。
- **U3 D2 content revision 机制**：建议以已验的 F `capture`（versions.git + archive/manifest）为主，worktree git 作为 conventions 选项。
- **U4 R 控制库归属**：每工作 `ledger/control.sqlite`（利于"拷走即完整"）vs host 共享库 + namespace 过滤（利于跨工作关系与公平轮转）。建议**拆分**：工作侧运行账本随目录、host 侧登记/授权/跨工作关系索引留在 host，但这要动 R 合同。
- **U5 可移植性措辞与 Userspace 迁移责任**：外部 Userspace 按引用版本另行迁移或显式拒绝。
- **U6 事件导出时机**：默认每 Round 一次范围导出；每 Step 导出为 conventions 选项。

### 12.3 新增未决（机制级）

- 事件导出的接口形态：用既有 runtime 读端循环（`lore_runtime/event_reader.py` 单条读取）还是给 E 增一个窄 `export_range`（后者要动 E 合同与用例）。
- host 登记/索引的可重建性：能否仅靠扫描 `works-root` 重建"在册"？跨工作 grants 的权威是否只在 host。
- 观测区默认保留期数值：待测量，不预设 SLA。
- 标准拓展点归属：`harness/tools/`（工具定义/交互解析）与 `harness/budget/`（预算/截止）是否入选标准点，还是并入 `logic//rounds/`（§4.1 对齐表）。
- manifest 事件声明 schema 的**正式字段与 runtime 解析实现**：本稿 §4.5 已定语义（声明优先 / 注册严格 / 未知不报错 / producer 权限 / digest 不自引用 / 保留前缀），字段名仍须进组件合同并经独立用例。
- **V-A 已裁决（2026-09-16，用户）**：harness 自定义对象的实例状态权威在**事件**；`content/` 只放产物与渲染（§4.4）。不再作为未决项。
- **Q3 已裁决（2026-09-16，用户）**：保留前缀（`sys.*`）+ 扩展命名空间（§4.5）；仅"命名空间申请/转让机制"留后续。
- **通用原语充分性**：P1–P8（§4.3）是否完备——用"示例 harness 只用通用点即可表达、否则补通用原语而非领域目录"来检验。
- `views/`、`presentation/` 作为**可选**标准点的字段形态：`views` 的 `source`/`resolver` 取值空间（**从轻**，不定义视图类型学，§4.7）。
- 与既有验收映射的接线：目录相关性质尚未进入 `governance/runtime-acceptance-map.md`。

---

## 13. 验证用例（预登记候选，**未执行、无实现**）

每条须独立判据、可拒绝相关错误、明确观测；当前全部 UNVERIFIED，且本仓库无工作目录实现，故只作为后续 G4 的预登记输入。

| ID | 判据 | 相关反例 | 观测 | 独立性备注 |
|---|---|---|---|---|
| VD01 | quiesce→拷贝→新根导入→重授权后可接续，A 区逐项 digest 匹配 | 缺段/哈希不符/未重授权 | 新宿主重建后比对 | 迁移需另一工作根 |
| VD02 | 模型 Surface 域仅能写 `content/`；写 `harness/`、`ledger/`、`session/`、`head` 被拒且字节不变 | 路径别名、symlink、继承 FD | 文件系统 + 挂载外部观测 | 不许按路径名推断权限 |
| VD03 | §6 七步各切点 SIGKILL 后，`head` 引用物全部已落盘且 digest 匹配 | head 指向未落盘 facts | 崩溃注入 + 重放 | 与 P07 同型 |
| VD04 | 撕裂尾行被截断并留痕，半行不被当事实 | 残行被解析成事件 | 人工构造残行 | 独立于实现者日志 |
| VD05 | 同外来身份重放只受理一次；接受行可由 facts 重建 | 重复受理/重复副作用 | 重放 + 去重账核对 | 对齐 E:17 |
| VD06 | 删 `derived/` 后同输入重建 digest 稳定 | 重建依赖隐藏状态 | 删前后比对 | 对齐 glossary T1 |
| VD07 | 删某轮 `session/rounds/` 后恢复照常，仪器报观测缺失 | 静默补造观测 | 仪器输出 | B 区纪律 |
| VD08 | 目录内无密钥/绝对宿主路径/dev-ino；导入不复制物理身份 | 复制旧 inode/device | 扫描 + 新宿主观测 | AGENTS.md 平台约束 |
| VD09 | facts/session/ledger/derived 不入内容演进史；content 每 Round 一 revision | 流水被版本化 | 版本库成员核对 | v1 git 判据 |
| VD10 | 未知 `layout_version` 响亮拒绝；旧版本迁移保数据 | 静默按新版读 | 版本矩阵 | 迁移双向 |
| VD11 | 复制含 `grants` 的目录到新宿主，未重授权不受理 | 凭 work.json 文本继承授权 | 受理尝试 + 授权侧核对 | 安全不变量 I8 |
| VD12 | 工作沙箱不可见工作目录；Surface 域 Shell 可见 content/ 与只读 harness/ | 沙箱逃逸读写 | 挂载 + 进程身份观测 | 对齐 P02 |
| VD13 | **新增拓展点不改 runtime**：给 harness 增加一个 manifest 声明的新 kind（自定义投影器/组织策略），注册并运行；runtime 不拒绝未知项、新策略被实际采纳（观测其产物），且 runtime 产品代码零改动 | runtime 按硬编码路径清单拒绝/忽略扩展；扩展遮蔽框架保留名 | 注册结果 + 真实投影产物 + 产品代码版本 | 单靠"注册未报错"不算；须观测策略实际生效 |
| VD14 | **未知 L2 条目保真**：`harness/ext/<ns>/` 下未知条目在 Round 提交、拷贝、导入、恢复、`derived/` 重建后仍在，且从未被 runtime 解释 | 未知条目在恢复/重建时被丢弃；被当成角色执行 | 迁移前后逐字节比对 | L2 规则的直接否证 |
| VE01 | **无通用终态**：未声明 goal/plan 的工作照常运行并按声明停止，runtime 不产生也不要求 `work.completed` | runtime 合成终态；无 goal 即拒收工作 | runtime 记录 + 事实流 | 对齐 v5:161,208 |
| VE02 | **示例 harness 充分性（goal 模式）**：只用 P1–P8 通用点的 goal 模式 harness 可表达"目标 + 完成事件 + 验收引用"，实现与运行**不新增任何框架目录/字段** | 必须加 `harness/goal/` 或 runtime 分支才能表达 → 判为框架缺通用原语 | 注册 + 运行 + 事实/投影产物 + 产品代码版本 | 判据是可表达性，不是业务结果正确性 |
| VE03 | **示例 harness 充分性（plan 模式）**：阶段完成事件落面后**下一阶段被投影进下一次实际输入**，全程无 runtime 调度器、无框架 plan 目录 | 需要框架为 plan 开后门；plan 变成 runtime 调度 | 实际投影文档 + 阶段边界 | 对齐 v5:18 |
| VE04 | **观测事实（P7）**：跨声明阈值产生观测事实（如上下文窗口接近）；harness 据此开组织轮；该事实出现在下一步输入投影中 | runtime 注入固定压力文本替代事件；观测不可见 | 输入投影原文 + 组织轮产物 | 对齐 extension-points §3 与 O6 |
| VE05 | **身份与保留名（P6/P8）**：harness 自定义对象的 id（如 goal/stage）跨 Round、重放、迁移稳定；扩展占用框架保留前缀被拒 | 标识随路径/重排而变；保留名被扩展遮蔽 | 重放/迁移前后比对 + 注册拒绝 | 与 §4.3 P6/P8 配套 |
| VE06 | **manifest 解析（§4.5 R1–R6）**：声明优先、默认路径兜底、缺席=关闭；声明但 digest 不符→注册拒绝；未知条目保留不报错；`sys.*` 只能订阅不能自定义；多实例按 `id` 调用 | 按硬编码路径名调用；未知字段即失败；harness 自定义 `sys.*` | 注册结果矩阵 + 实际调用轨迹 | 正反例都要，注册拒绝≠运行失败 |
| VE07 | **archive 能力（§4.6 示例 3）**：跨阈值产生 `sys.context.*` 观测事实并开维护轮；折叠后投影缩减而原文仍在；有损摘要记 `fold_digest`+`original_refs` | 用 `derived/` 当归档区；摘要丢原文无指针；runtime 硬编码阈值 | 事实流 + 折叠产物 + 原文可达性 | 对齐 v5:252 |
| VE08 | **work 委派（§4.6 示例 1 委派侧）**：父工作只能经事件与授权受理影响子工作；未授权委派被拒；子工作结果经 `work.reported` 回来 | 父工作直接写子工作 `content/`；凭副本继承授权 | 跨工作事实流 + 授权侧拒绝 | 对齐 glossary"无中心行动者"、I8 |
| VE09 | **信息项与投影分离（§4.7）**：`views` 缺席时仅 L0 最低信息即可运行；新增信息项只加声明不改投影代码；投影产物可观测；信息项缺失显式；信息项对模型只读 | 视图定义被判据/regex 硬编码；投影改内容而非选内容；信息项可被模型写 | 实际输入投影 + 声明 diff | 轻约束的可证伪形式 |

---

## 14. 追溯

| 本稿判断 | 来源 |
|---|---|
| 框架固定/内容自由、拓展点映射、git 判据、T2 外置 | v1（用户裁决） |
| 事件可作输入视图/导出格式；内部存储不必是文件 | v5:131 |
| 目录名/布局/每步提交不在 v5 冻结 | v5:343,349 |
| 事实各有所有者 + 可验证引用；受控导出须标来源与版本 | G1:22-32 |
| 不假设跨设施事务 | G1:32 |
| 恢复边界与中断后合法动作 | G1:50-61 |
| 保留不得破坏已受理依赖；期限外缺失显式报告 | G1:44；E:11 |
| Session 是观测域，接续/Projection 不依赖 | glossary:118-119 |
| 接续 = 从 T0 重放（含 Harness） | glossary:32,123 |
| Harness 内容寻址、登记后只读 | glossary:43 |
| 模型/工作不持密钥、控制端点、NATS 凭据 | glossary:100-102；E:7；R:9 |
| X pause→导出精确字节→外部持久化→resume | s:29,41 |
| 双 Shell 写范围与权限由 Runtime 落实 | v5:184,188,190；G1:84 |
| F 版本 = Git 对象 + archive + manifest；控制/授权/Session/事件不入回退归档 | f:38；f/manifest-contract.md |
| 登记身份含 dev/ino，路径不是权限 | f:9；r:17 |
| 现状无 work-root、设施分别配置；m01 先例 | 源码只读盘点；`validation/system/m01_run.py:100-103` |
| 三种 archive 禁混 | glossary:67-68；v1:123 |
| **事件是唯一的推进与接入契约；harness 自定义对象的实例状态权威在事件** | 用户 2026-09-16 裁决；v5:40,163；glossary:31,64-66；r:7（禁止竞争真相） |
| manifest 声明优先 / 保留前缀 `sys.*` / 扩展命名空间 | 用户 2026-09-16 裁决（§4.5）；v5:349（目录名不冻结） |
| 信息项 / 投影 / 呈现 三层分开，约束从轻；L0 最低信息五项 | 用户 2026-09-16（§4.7）；v5:204；glossary:109-115（Projection ≠ Presentation） |

---

**本稿不改任何既有验收结论**；它把"工作目录"从 v1 的框架半成品补成可复核的机制设计，并把其中真正根本的分叉（U1–U6）显式交回裁决。


---

# 6. runtime↔harness 接口契约（M1）
> 来源：design/g3/work-runtime-contract.md + amendment-task-tool-liveness-2026-09-17.md 原文（修订记录 D1–D7 与 D1–D4）

# 工作目录 runtime ↔ harness 接口（M1 实现契约）

状态：**实现中的接口记录**，不是验收结论。对应实现 `lore_work/`（runtime）与 `lore_harness/goal/`（第一个 harness）。设计依据：[work-directory-landing.md](work-directory-landing.md) §4.4–4.7。

## Runtime 负责（机制）

- 基础树：`work.json`、`harness/manifest.json`、`surface/{content,head,facts.jsonl}`、`ledger/`；按需 `session/`、`derived/`。
- 事实流单写者：只有 runtime 追加 `surface/facts.jsonl`（append + fsync）；每条含 `seq/id/kind/source/payload/digest`。
- 触发器水位：`ledger/rounds.jsonl` 的 `trigger_seq` 决定"哪些事实已求值过"，与提交水位 `head.facts_end` 分开——已声明的事件仍能被下一次求值看到。
- Round 执行：求值触发 → 投影 → 模型 → 工具 → 落事实 → 提交；提交顺序见 landing §6。
- `head` 是唯一提交点（原子替换），每次提交含 `revision`（content 树 digest）+ `facts_end` + `round_id` + `ledger_seq`。
- 受理门：`admit()`（Fact Admission，2026-09-17 由 `ingest` 更名）对外来事实做幂等去重与冲突拒绝；未声明的 kind 直接拒绝；`requires_relation` 的 kind 无 sender 直接进入也拒绝。
- **跨工作中继**：`relay()`（2026-09-17 由 `deliver` 更名，墓碑 delivery）把一个工作的事实经**接收方的**受理门送入另一工作；需双方在 host 权威文件登记且路径一致、接收方 wants + 发送方 grants 双向匹配；拒绝记在接收方受理账；副本不继承授权（I8）。
- **harness 只读**：加载 harness 模块时禁用字节码写入；每轮开始/结束重算 harness digest，变化即响亮失败。
- 模型调用：`provider.complete(messages)`；凭据只在进程内，不写工作目录。
- 模型交互写 `session/rounds/<round_id>.jsonl`（观测区），**不是事实**；`reasoning_content` 与 `usage` 记在这里。

## Harness 负责（策略）

`harness/manifest.json` 声明与 `roles/` 下的普通代码模块。角色钩子：

| 角色 | 钩子 | 语义 |
|---|---|---|
| `rounds` | `should_start(*, work, facts, new, head, now) -> bool` | 触发求值；`new` = 水位之后未求值的事实；`now` = 当前 epoch（时间驱动判断归 harness） |
| `rounds` | `should_continue(*, state) -> bool` | **轮的结束条件**；每次动作后调用，False 即停步循环 |
| `projection` | `build(*, work, facts, new, head, content_dir, step, max_steps, rejected_final, userspaces, revision) -> {system, messages}` | 有界投影；步预算、已提交 revision、授权 Userspace 由 runtime 提供，怎么用归 harness |
| `logic` | `parse(text) -> action` | 解释模型输出（交互格式是 harness 选择） |
| `logic` | `guard(*, state, action) -> str \| None` | **动作执行前的拒绝权**：返回理由即拒绝该动作（落 `sys.action.rejected`，无副作用），用于挡住"原地打转" |
| `logic` | `settle(state) -> [{kind, payload}]` | 步循环结束后的收尾声明（派生事实在此计算） |
| `admission` | `accept(*, kind, payload) -> bool` | 外来事实准入规则 |

动作类型（runtime 执行、harness 解释）：`shell`、`emit`、`final`（**提案**结束本轮）、`recall`（确定性检索，落 `sys.recall.result` 观测；第四类动作，2026-09-17 补记）。

- `shell`：`{type:"shell", script, target?, budget_ms?}`；`target` = `content`（默认）｜`userspace`｜`userspace:<id>`。runtime 按 `work.json.userspaces` 解析 cwd；未登记/未知目标 → `exit 126` 拒绝且不回退宿主（v5:190，语义保持不变）。`budget_ms`（可选，模型动作内声明）是 harness/模型的**策略预算**：到点**整进程组**终止（SIGTERM→宽限→SIGKILL），结果 `outcome:"timeout"`（调用已执行，副作用可能发生）；超过 runtime 上限的声明在执行前被拒并落 `sys.action.rejected`（需声明该 kind）。**这是路由与记账，不是隔离**：真正的沙箱是 X 的职责，尚未接入。
- `emit`：`{type:"emit", kind, payload, base_rev?}`。**`base_rev` = 条件声明**：提供时必须等于轮开始时记录的已提交 revision，否则落 `sys.declaration.rejected` 并拒绝该声明（要求 manifest 声明该 kind）。
- `final`：**只是提案**（2026-09-16 反例修订）。runtime 调用 `rounds.should_continue(state)` 决定是否真的结束；被驳回的最后一句话经 `rejected_final` 回传下一次投影。

**规范观测（P7 最小实现）**：manifest 声明即启用——`sys.context.usage`（每次模型调用前落 `{step, projection_bytes, facts, content_files}`）；工具存活观测（2026-09-17 实施，均按声明启用）：`sys.tool.started`、`sys.tool.check`（默认间隔 10 s、退避 ×2 封顶 60 s，**只观测不杀**）、`sys.tool.abandoned`（资源安全网：结果未知，恢复须先查询不盲重跑）。其余 runtime 产生的观测：`sys.action.rejected`（guard/预算越界拒绝）、`sys.declaration.rejected`（base_rev 冲突）、`sys.recall.result`。`sys.clock`/定时器尚未实现，时间目前经 `should_start(now=)` 提供。

**崩溃与恢复（2026-09-16）**：`ledger/rounds.jsonl` 用 `phase: start|commit|abort` 行标记轮；入口若见 `start` 无 commit 即返回 `recovery_needed`，不续跑；`lore_work recover` 把未提交尾部原字节存入 `session/crashed/`、截断 facts 到该轮 `trigger_seq`、写 `ledger/repairs.jsonl`。真实中断已用该路径恢复（见 FINDINGS）。

## manifest（M1 实际字段）

```json
{"schema":"lore-harness/v1","entry":{"ref":"logic/main.py"},
 "facts":{"kinds":[{"kind":"...","producer":"runtime|harness|external","requires_relation":false,
                    "contract":{"ref":"contracts/x.json","digest":"sha256:..."}}],
          "triggers":[{"id":"...","on":["<declared kind>"]}]},
 "roles":{"projection":[{"id":"...","ref":"projection/main.py","digest":"sha256:..."}], "...":[]},
 "views":[], "extensions":[]}
```

解析规则：声明优先、默认路径兜底（兜底条目不盖章，由 `work.json.harness.digest` 整树覆盖）、缺席=关闭；`sys.*` 只能由 runtime 声明。**digest 严格校验（2026-09-17，落地 R2）**：登记时 `create_work` 对每个声明 ref（角色条目、kind 契约、trigger `when`、view resolver）计算并写入 digest（盖章幂等）；加载时缺失或不匹配即响亮拒绝。

**harness 共享基座（2026-09-17）**：`lore_harness_base.py`（仓库根）是框架随版本提供的标准库——
动作协议与解析前缀、事实折叠、轮门骨架、受理工厂、投影脚手架、file_digest/load_config 的唯一定义源；
harness 模块与 runtime 默认投影/解析共同使用它。它不进 harness digest（整树 digest 覆盖的是 harness
目录内文件），对它的依赖等价于对角色钩子签名所绑定的 runtime 版本的既有依赖。编写期复用路径见
[harness-catalog/README.md](harness-catalog/README.md) 末节。

## M1 已知缺口（未验证或未实现）

- **工具域只有 content/**：Userspace 域、双 Shell、沙箱（X）未接。
- **工具协议是 harness 自定的单 JSON 动作**：不是 function calling；未做探测与修订。
- **尚无**：信息项 views/presentation（声明已保留）、`derived/` 重建、崩溃注入、幂等重放、并发/单写者租约、Userspace 域。多实例角色：manifest 校验支持，runtime 尚不按实例选择。
- **已最小实现**：`sys.context.usage` 规范观测（P7）；跨轮触发（trigger_seq 水位）；`final` 提案 + harness 决定轮结束；archive 无损折叠（archive harness）。
- **工具执行已按修订实施（2026-09-17）**：默认是**到点发 `sys.tool.check`（只观测，不杀）**；
  `budget_ms` 是策略判定（到点整进程组 SIGTERM→宽限→SIGKILL，结果 `timeout`）；
  runtime 硬上限是资源安全网（结果 `unknown` + `sys.tool.abandoned`）；
  `sys.tool.result` 增加 `outcome`（权威）与 `side_effects`，`exit` 为兼容镜像。
  离线判据 VO37–VO42（`validation/work_runtime/offline_tool_liveness.py`）与既有套件全部通过；
  **独立复跑未做**，修订状态仍以 amendment 为准。
  记录：[amendment-task-tool-liveness-2026-09-17.md](amendment-task-tool-liveness-2026-09-17.md)；
  设计出处 [voice-assistant/execution-timeouts.md](voice-assistant/execution-timeouts.md)。
- **证据范围**：单机、单实现者；见 [validation/work_runtime/FINDINGS-2026-09-16.md](../../validation/work_runtime/FINDINGS-2026-09-16.md)。

## 修订记录（2026-09-17 重构）

1. **术语对齐（glossary v3.2）**：`ingest` → `admit`（Fact Admission）；`deliver` → `relay`
   （墓碑 delivery→Event+Fact Admission）；CLI 子命令 `admit`/`relay` 同步更名，
   `validation/work_runtime` 调用点同步。历史命令名出现在 2026-09-16 及更早的验收记录中，按原样保留。
2. **R2 digest 严格化**：登记时盖章（`stamp_manifest_digests`），加载时缺失/不匹配即拒。
   此前的"只记不算"缺口关闭；旧行为记录于上方历史版本（git 历史 66 行版）。
3. **工具存活**：`tool_timeout`（30 s 硬杀）移除。修订 D1–D4 的 M1 取舍：
   D1 参数改为 `--tool-check-interval`（默认 10 s）/`--tool-budget`（默认无，ms）/`--tool-hard-cap`
   （默认 600 s，runtime 保留，动作声明越界被拒并留痕）；
   D2 check 落**面事实**（`sys.tool.check`，声明启用；退避 ×2 封顶 60 s，数值待测 U26）；
   D3 硬上限目前是 runtime 级每调用上限（配置来源 X budget maxima vs `work.json.policy` 仍待裁决 U27）；
   D4 与租约的对齐未处理（M1 无租约机制）。
4. **U28（`sys.tool.finished` 是否与 result 合并）**：M1 取合并——`sys.tool.result` 增加
   `outcome/side_effects/duration_ms/call_id`，不另立 finished 事实；契约十份收敛为规范一份
   （此前 4 变体漂移，4 份缺 runtime 实际会写的 `target/cwd`）。
5. **U30（check 落库粒度）**：暂落面事实；频率影响待测量后复议。
6. `work.json.landing{boundary,last_round}` 死字段移除（创建后从未更新）；
   `provider.py` 文档中的 "ARC plan" 更正为 "Volcengine Ark plan"（env 变量名 `ARC_PLAN_API_KEY` 不变）。
7. **术语对齐（glossary v3.3，2026-09-17 用户裁决）**：**Task→Work**（task 的"可完成工作"
   与 agent 框架工作项双重读法歧义）、**Workspace→Userspace**（为 Work 让位近形词；
   实质本就是用户侧授权领地）。机械改名：包 `lore_work`、盘面 `work.json`、schema
   `lore-work/v1`、CLI `--work-id`/`--userspace`、事件命名空间 `work.*`、shell target
   `userspace[:id]`、验证目录 `validation/work_runtime`、角色钩子签名 `work=`。
   工作目录既称（含 DESIGN 文件名）随之；v1–v3.2 时代验收记录中的旧名照原样保留。


## 6b. 工具存活修订（原文）

# 修订记录：工具执行默认由"30s 硬杀"改为"check 先行"（2026-09-17）

状态：**已实施，独立复跑未做**（2026-09-17 当日实施；离线判据与既有套件已通过，见文末）。
不是验收结论；独立复跑前不得计入"check 先行"的通过。
依据：用户 2026-09-17 裁决"默认应是**提醒 check 事件**，runtime 负责避免死掉，但不是超时工具就不执行"；
设计见 [voice-assistant/execution-timeouts.md](voice-assistant/execution-timeouts.md)。
契约归属：本修订落在 **task runtime（`lore_task/`）**，不属语音专属。

## 1. 修订内容

| | 现状（2026-09-17 工作副本） | 目标 |
|---|---|---|
| 默认行为 | 工具调用到 `tool_timeout`（默认 **30 s**）**直接终止** | 到默认间隔**发 `sys.tool.check`**（存活提醒），**不自动终止**；怎么办由 harness 决定 |
| 终止时机 | 无条件（固定超时） | 仅当 harness 判定 `timeout`，或触发 runtime 资源安全网 |
| 终止范围 | `subprocess.run(timeout=)` 杀**直接子进程** | 终止时 SIGTERM→宽限→SIGKILL **整进程组** |
| 结果语义 | 落 `sys.tool.result{exit: 124}`（超时被塌缩成一个退出码） | 四分类 `ok / failed / timeout / unknown`，附 `side_effects`；`sys.tool.abandoned` 表示资源回收导致的**未知** |
| 存活观测 | 无 | `sys.tool.started` / `sys.tool.check` / `sys.tool.finished` / `sys.tool.abandoned` |

## 2. 现状事实（可复核）

源码位置（工作副本；`lore_task/` 当前**未入 git**，哈希为工作副本内容）：

| 文件 | 行 | 内容 | sha256（2026-09-17） |
|---|---|---|---|
| `lore_task/round.py` | 53–55 | `_run_shell` 用 `subprocess.run(["/bin/sh","-c",script], …, timeout=timeout)` | `e6649d5d2e923278d4b0d0282b65cf665d7c63326892d27e291d640d5cb45789` |
| `lore_task/round.py` | 371 | `def run_round(base, provider, *, max_steps=8, tool_timeout: float = 30.0)` | 同上 |
| `lore_task/round.py` | 488–490 | `except subprocess.TimeoutExpired: out = {"exit":124,"stdout":"","stderr":"timeout"}` | 同上 |
| `lore_task/round.py` | 491 | 落事实 `sys.tool.result`（含 `exit`） | 同上 |
| `lore_task/cli.py` | 58–59 | `--timeout 180.0`、`--tool-timeout 30.0` | `f47d6090e55fee72f3cb2bd7985c5c80bbe0340e10a58984c3066611d9eca13d` |
| `lore_task/cli.py` | 173 | `run_round(..., tool_timeout=args.tool_timeout)` | 同上 |

代码仓库 HEAD：`cfe7ce9eaca4101430bd67e2288694e8cb2705c8`（`lore_task/` 为未跟踪工作副本，故哈希只绑定当次工作副本）。

## 3. 为什么改（反例先行）

1. **误杀合法长任务**：安装/构建/大文件处理动辄几分钟，30 s 无条件终止是错的默认。
2. **塌缩语义**：`exit 124` 把一个"我们不知道结果"的状态写成了看起来像"失败/结束"的退出码；
   对可能有副作用的调用，这直接违反"不确定不重跑"（v5:332/336、X 合同）。
3. **终止不彻底**：`subprocess.run(timeout=)` 不保证**整进程组**终止；孙进程可能继续占资源。
4. **无存活观测**：卡住时系统没有任何"还在跑"的事实，等待方无从判断，只能等一个固定秒数被砍。

## 4. 影响面

- **产品代码**：`lore_task/round.py`、`lore_task/cli.py`（`tool_timeout` 参数语义要重新定义：从"硬截止"变为"软预算/check 间隔"或另立参数）。
- **事实契约**：新增 `sys.tool.*` 观测；`sys.tool.result` 的字段扩展（`outcome`、`side_effects`）。
- **既有校验器**：`validation/task_runtime/*` 经查**没有断言 `exit == 124`**（只断言 `exit 126` 未授权与 `exit 0`）→ 影响小；
  但**必须保留 `exit 126`（未授权目标）与 `exit 0`（成功）语义不变**。
- **文档**：[task-runtime-contract.md](task-runtime-contract.md) 的"M1 已知缺口"需标本条；
  [voice-assistant/execution-timeouts.md](voice-assistant/execution-timeouts.md) 是设计出处。
- **历史证据**：既有 task_runtime 证据绑定旧行为，**不迁移**为"check 先行"的通过。

## 5. 旧值保留

- 现状行为、源码位置与哈希记录于本文件，**不覆盖**；
- `exit 124` 作为"超时"的旧语义在兼容期可继续出现，但新实现应同时给出 `outcome`；
  两者并存不是双权威，`outcome` 为准、`exit` 为兼容镜像。

## 6. 实施顺序与门槛（不得跳步）

1. **先预登记用例**：VO37–VO42（[voice-assistant/validation-plan.md](voice-assistant/validation-plan.md) E4）落为可执行判据；
2. **再实现**：check 事件 + 结果四分类 + 进程组终止 + 资源安全网；
3. **独立复跑**：既有 `validation/task_runtime/` 套件 + 新用例，判据不放宽；
4. 未通过前，本修订状态保持"待实施"，且**不得**以"设计已定"声称行为已改。

## 7. 未决

- **D1** `tool_timeout` 参数的迁移：改名（`--tool-budget`）还是保名改语义（易误读）。
- **D2** `check` 落面事实还是观测域（频率待测）。
- **D3** 硬上限/并发上限的配置来源（X budget maxima vs `task.json.policy`）。
- **D4** 资源安全网与既有租约（M03/M04 的 ~30 s 租约）如何对齐，避免两套计时。

## 8. 实施记录（2026-09-17 当日补记；上方第 1–6 节原文保留）

- §6 顺序已执行：先落预登记可执行判据 `validation/task_runtime/offline_tool_liveness.py`
  （VO37–VO42 + exit 126/0 保持性），再改实现，再复跑。
- 实现：`lore_task/round.py`（托管执行 `_run_shell_managed`：select 增量读、check 退避、
  进程组 SIGTERM→宽限→SIGKILL、硬上限回收即 `abandoned/unknown`）、`lore_task/cli.py`
  （`--tool-timeout` 移除，新增 `--tool-check-interval/--tool-budget/--tool-hard-cap`，取舍见
  [task-runtime-contract.md](task-runtime-contract.md) 修订记录第 3 条）。
- 契约：`sys.tool.result` 增加 `outcome/side_effects/duration_ms/call_id`（U28 取合并），
  十个 harness 的契约副本收敛为规范一份。
- 结果：`offline_tool_liveness.py` 全部 PASS；既有 `validation/task_runtime/offline_*.py` 全部通过，
  判据未放宽（唯一断言文本更新：invariants 的拒绝消息动词随 deliver→relay 更名，判据本身不变）。
- **未做**：独立验收者复跑（AGENTS.md 门槛）；因此本修订在独立复跑前保持"已实施未独立复跑"状态。


---

# 7. 共享基座（源码全文）
> 来源：lore_harness_base.py 原文（187 行，stdlib-only，不进 harness digest）

```python
"""Framework-provided standard library for harness authoring (lore_harness_base).

This module is part of the framework, versioned with the runtime, and NOT part
of any harness digest: importing it is the same class of dependency as the role
hook signatures themselves (a harness always runs against the runtime version it
was registered with). It exists because the ten example harnesses duplicated the
same scaffolding (harness inventory 2026-09-17, items 1-12); the domain
semantics - which kinds mean what, which rules apply - stay in each harness.

Composition ruling (2026-09-17): harness reuse happens at authoring time via
this shared library plus reference-merge; there is no runtime composition
mechanism. Stdlib only; this module must never import lore_work.
"""
import hashlib
import json
from pathlib import Path

# -- action protocol ---------------------------------------------------------

ACTION_PREAMBLE = (
    "Reply with exactly one JSON object and no prose. One of:"
)


def action_protocol(examples) -> str:
    """The single-JSON action protocol, with the harness's domain examples."""
    return ACTION_PREAMBLE + "\n" + "\n".join(examples)


SHELL_EXAMPLE = '{"action":{"type":"shell","script":"<sh script>","budget_ms":30000}}   run a command (budget_ms optional: policy budget in ms)'
EMIT_EXAMPLE = '{"action":{"type":"emit","kind":"<declared kind>","payload":{...}}}   declare a state change'
FINAL_EXAMPLE = '{"action":{"type":"final","text":"<short reason>"}}   end this round'


def parse_action(text) -> dict:
    """Common action prefix shared by every harness parse (and the runtime default).

    Strips whitespace and code fences, parses one JSON object, extracts the
    inner action. Malformed output is never guessed into an action: it becomes a
    final proposal carrying the raw text. Empty input becomes {"type":"none"}.
    Domain-specific shape checks stay in the harness and may fall back to
    `final_fallback(text)`.
    """
    raw = (text or "").strip()
    if not raw:
        return {"type": "none"}
    candidate = raw
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return final_fallback(raw)
    action = value.get("action", value) if isinstance(value, dict) else None
    if not isinstance(action, dict) or "type" not in action:
        return final_fallback(raw)
    return action


def final_fallback(text) -> dict:
    return {"type": "final", "text": (text or "").strip()}


# -- fact folding ------------------------------------------------------------

def fold(facts, *, latest=(), collect=(), flags=(), since=0) -> dict:
    """Fold a fact stream into per-kind state (the shared half of every `_state`).

    Returns a dict keyed by kind: `latest` kinds map to their newest payload
    (None if absent), `collect` kinds to the list of payloads in stream order,
    `flags` kinds to True once seen. `since` restricts to seq > since.
    Which kinds mean what stays in the harness.
    """
    out = {kind: None for kind in latest}
    out.update({kind: [] for kind in collect})
    out.update({kind: False for kind in flags})
    for fact in facts:
        if fact["seq"] <= since:
            continue
        kind = fact["kind"]
        if kind in out:
            if kind in latest:
                out[kind] = fact["payload"]
            elif kind in collect:
                out[kind].append(fact["payload"])
            else:
                out[kind] = True
    return out


def facts_since(facts, kinds, since_seq) -> list:
    """Facts of the given kind(s) with seq > since_seq (round-scoped views)."""
    if isinstance(kinds, str):
        kinds = (kinds,)
    return [f for f in facts if f["kind"] in kinds and f["seq"] > since_seq]


# -- round gate skeletons ------------------------------------------------------

def continue_when(state, kinds, *, stop_on_final=True, since=None) -> bool:
    """Shared should_continue skeleton: final stops, then a watched-kind fact
    inside this Round stops it. `since=None` uses the round's started_at_seq
    watermark; pass 0 to watch the whole stream."""
    if stop_on_final and state.get("final") is not None:
        return False
    watermark = state.get("started_at_seq", 0) if since is None else since
    return not facts_since(state.get("facts", []), kinds, watermark)


def start_unless_completed(facts, kind="work.completed") -> bool:
    """Shared should_start guard: never start a new Round after completion was
    declared (completion is a claim, not a runtime terminal state)."""
    return not any(f["kind"] == kind for f in facts)


def make_accept(*kinds):
    """Admission rule factory: accept only the harness's declared external kinds."""
    def accept(*, kind, payload):
        return kind in kinds
    return accept


# -- projection scaffolding ----------------------------------------------------

def content_files(content_dir) -> list:
    """Sorted relative file list of the content directory."""
    return sorted(str(p.relative_to(content_dir)) for p in Path(content_dir).rglob("*") if p.is_file())


def budget_lines(step, max_steps) -> list:
    return [
        "# Budget",
        "step %d of %d   remaining steps: %d" % (step + 1, max_steps, max_steps - step - 1),
        "",
    ]


def tool_history_lines(facts, *, since_seq=0) -> list:
    """'scripts already run in this Round' block plus the last tool result."""
    results = facts_since(facts, "sys.tool.result", since_seq)
    lines = ["# Shell scripts already run in this Round (do NOT run any of these again)"]
    if results:
        for index, fact in enumerate(results, 1):
            payload = fact["payload"]
            lines.append("%d. outcome=%s exit=%s  %s"
                         % (index, payload.get("outcome", "?"), payload.get("exit", "?"),
                            payload.get("script", "").replace("\n", " ")[:200]))
    else:
        lines.append("(none yet)")
    if results:
        last = results[-1]["payload"]
        lines += [
            "",
            "# Last tool result (outcome=%s exit=%s)" % (last.get("outcome"), last.get("exit")),
            "stdout: %s" % (last.get("stdout") or "").replace("\n", "\\n")[:600],
            "stderr: %s" % (last.get("stderr") or "").replace("\n", "\\n")[:300],
        ]
    return lines


def rejected_final_lines(rejected_final, limit=200) -> list:
    if not rejected_final:
        return []
    return ["", "# Rejected final", rejected_final[:limit]]


# -- small shared utilities ------------------------------------------------------

def file_digest(path):
    """sha256 of a file's bytes, or None if unreadable (evidence, not trust)."""
    try:
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def load_config(defaults=None, *, config_path) -> dict:
    """Merge harness config.json over defaults; unreadable config = defaults."""
    config = dict(defaults or {})
    try:
        with open(config_path, encoding="utf-8") as fh:
            config.update(json.load(fh))
    except (OSError, json.JSONDecodeError):
        pass
    return config
```

---

# 8. harness 示例集（全部）
> 来源：design/g3/harness-catalog/ 全部 11 文件原文

## 8.1 示例集总纲

# harness 示例集（harness-catalog）

地位：**示例集，不是框架标准点**，不表示任何能力通过；全部 UNVERIFIED。
目的（用户 2026-09-16 提议）：一种 harness 一个文件，讨论它**如何只用框架通用原语定义**。定义不出来的地方，就是**通用原语缺口**——回补原语，**不加领域目录**（"宁缺毋滥"）。
相关：[../work-directory-landing.md](../work-directory-landing.md) §4.3–4.7（五件套、P1–P8 原语、manifest 解析、信息项/投影/呈现）。

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
| [coding.md](coding.md) | 改代码 / 跑测试 / 迭代 | 工具结果归 Session、双域、Userspace 版本 | `tools/` 落点（§4.1 待裁决） |
| [research.md](research.md) | 检索与素材沉淀 | recall 成本与"恢复不重放" | 模型辅助召回契约 |
| [delegation.md](delegation.md) | 跨工作委派 | 关系 + 授权 + 事件受理 | 跨工作授权查询语义 |
| [monitoring.md](monitoring.md) | 条件/定时监视 | 长等待、零驻留、触发 | 定时/时钟观测与等待责任 |
| [system-design.md](system-design.md) | 自顶向下系统设计 | 局部修改、冻结/修订、单调收敛 | 条件受理（base_rev）、冻结与修订、失效传播 |
| [voice-assistant.md](voice-assistant.md) | 实时语音助手（流式听/说、双工、可换语音模型） | 实时设施与事件工作面的接缝、流式产出、二进制 artifact | 对外投递、流式观测通道、媒体 artifact 通用化、实时会话设施归属 |

## 待写（宁缺毋滥，一次一个）

computer-use（浏览器/桌面）、review / critic（独立评审）、reflection / memory（记忆整理）、A/B shadow（多策略对比）、data-pipeline（批处理）、support-ticket（工单）、multimodal-input（图像输入）、verification-harness（验收执行）、retrieval-index（索引维护）。

## 派生一个新 harness 的编写期复用路径（2026-09-17）

组合裁决的落地方式（无 runtime 组合机制，全部在编写期完成）：

1. **共享基座**：`lore_harness_base.py`（仓库根，框架随版本提供的标准库，stdlib-only、不进
   harness digest、不 import runtime）。已收敛的公共件：单 JSON 动作协议与解析前缀
   （`action_protocol` / `parse_action` / `final_fallback`）、事实折叠（`fold` / `facts_since`）、
   轮门骨架（`continue_when` / `start_unless_completed`）、受理工厂（`make_accept`）、
   投影脚手架（`content_files` / `budget_lines` / `tool_history_lines` / `rejected_final_lines`）、
   证据与配置（`file_digest` / `load_config`）。十个示例 harness 已全部基于它（净 -328 行，
   parse 前缀 11 份 → 1 份，协议文本 11 份 → 1 份）。
2. **域语义留在 harness**：哪些 kind 意味什么、按 payload 字段建索引的域状态
   （如 system-design 的 unit_id 索引）、规则文本、拒绝条件——这些是"这个 harness 是谁"，
   不下沉。
3. **参考合并（参考既有 harness 派生）**：复制最接近的示例作起点 → 删掉不适用的域段 →
   manifest 五件套（词表+契约+产生者+触发+投影/逻辑）→ digest 由登记时盖章补齐。
4. **跨工作组合**：只用事件受理（`wants`+`grants`+host 权威 + `relay`），见 delegation 示例。

## 8.2 archive

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

## 8.3 ask-user

# harness 示例：ask-user（向人提问并等待）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

需要人拍板（选择、确认、补充信息）时提出问题，**工作进入等待**，人回答后继续。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `ask.requested{ask_id, question_ref, options?, deadline?}`；`ask.answered{ask_id, answer_ref, by}`；`ask.expired{ask_id, reason}` |
| 产生者 | `requested` = harness 声明；`answered` = **外部受理**（人/上游系统）；`expired` = runtime 观测（配置了截止时） |
| 触发与受理 | `answered` → 开轮继续；`expired` → harness 决定重问 / 降级 / 暂停；`ask_id` 幂等，重复答案冲突 |
| 投影 | 待答问题 + 选项（有界）+ 已答内容；**不把整段历史重灌** |
| 逻辑 | 超时策略、恢复（答案是被受理的事实）、追问次数上限 |

## 通用原语映射

P1 声明｜P2 受理（外部答案进门）｜P3 触发｜P4 投影｜P5 逻辑｜P6 身份（`ask_id`）｜P7 观测（截止）。

## 边界与反例

- **等待期零驻留**：不保留工作专属进程/长连接/沙箱（v5:90）；等待是数据 + 触发条件。
- 答案必须**经 Fact Admission**成为事实；不能靠读一个可变文件当答案。
- 不能期望 Step 中途动态注入（v5:42/149）；答案在**下一次约定输入**交付。
- 反例：阻塞进程等人回答；把 `ready/done` 当通用原语；答案直接写 `content/` 就算数。

## 框架缺口

**对外通知/投递原语**：问题如何**送达人**（以及回答入口）没有规范化定义——现有契约只覆盖**入站**事件与观测。可以是一个受控薄包装或普通工具，但归属与权限必须明确（否则每个 harness 各造一套通知通道）。

## 8.4 coding

# harness 示例：coding（改代码 / 跑测试 / 迭代）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

在授权的代码仓库里读代码、改文件、跑测试，按结果迭代直到目标达成。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `code.iteration.started{}`（可选）；`code.test.result.declared{command_ref, outcome, evidence_ref}`；`code.change.summary{change_ref}`；`code.review.requested{scope}`（可选） |
| 产生者 | harness 声明（**引用**局部事实）；原始工具/模型往返留在 Session／X，**不复制**进面 |
| 触发与受理 | 测试失败 / 评审结论 / 目标变更 → 下一轮；同一次测试结果只开一轮 |
| 投影 | 相关文件片段 + 最近一次测试结果 + 目标 + 指针；**不预展开整个仓库**（v5:250） |
| 逻辑 | 解析模型输出的执行意图（交互约定归 harness，不归 runtime）、双域分流（Surface 笔记 vs Userspace 代码）、失败重试上限与停止条件 |

## 通用原语映射

P1 声明｜P2 受理｜P3 触发｜P4 投影｜P5 逻辑｜P6 身份（`evidence_ref`）｜P7 观测（预算/截止/上下文）。

## 边界与反例

- **Userspace 在工作目录之外**：代码属于外部授权范围，不进工作目录（v5:38、G1:25）。
- **局部事实不复制**：工具结果属 Session/执行器观测域，通过引用进入面（§4.4 规则 2；r:7）。
- Surface 版本 ≠ Userspace 版本，恢复要分别选择并明确组合（G1:94）。
- 反例：把仓库放进 `surface/content/`；把工具 stdout 逐条写成面事件；用 git HEAD 冒充全部恢复依据。

## 框架缺口

**`tools/`（工具定义与交互解析的统一落点）**——已在 `../work-directory-landing.md` §4.1 列为待裁决标准点；coding 是最需要它的场景（也是"缺通用原语就补原语"的典型）。

## 8.5 delegation

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

## 8.6 goal

# harness 示例：goal（目标 + 完成 + 验收）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

外部给出目标与验收条件；harness 推进，直到给出"完成"声明；**验收由外部独立检查**。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `work.objective.set{objective_ref, acceptance_refs[]}`；`work.phase.changed{goal_id, from, to, rev}`；`work.completed{goal_id, evidence_refs[]}`；`work.blocked{reason_ref}` |
| 产生者 | `objective.set` = 外部受理；`phase.changed` / `completed` / `blocked` = harness 声明 |
| 触发与受理 | `objective.set` → 开第一轮；`completed` → `rounds` 不再开轮；`blocked` → 默认不开轮（等外部）；受理按契约校验、幂等去重 |
| 投影 | 当前 objective + phase + **验收清单** + 证据指针（给指针不灌全文） |
| 逻辑 | phase 状态机；验收引用解析；"完成"只做声明，不自行判定业务成功 |

## 通用原语映射

P1 声明（kinds/契约）｜P2 受理｜P3 触发｜P4 投影｜P5 逻辑｜P6 身份（`goal_id` + `rev`）｜P7 可选观测（预算/时间）。

## 边界与反例

- `work.completed` 是 **harness 声明的事件**，不是 runtime 通用终态（v5:161,208）。
- **"完成" ≠ 不活**：工作仍在册，直到管理动作 Archive。
- **完成声明 ≠ 业务验收**：验收在 V/外部（GOAL §4）。
- 反例：runtime 合成终态；把模型最终回答当完成；完成即自动 Archive；把 `goal_id` 编进目录名。

## 框架缺口

**无。** 这条本身就是结论：goal 不需要任何新框架目录，只需要声明 + 受理 + 触发 + 投影 + 逻辑。

## 8.7 monitoring

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

## 8.8 plan

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

## 8.9 research

# harness 示例：research（检索与素材沉淀）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

围绕一个问题持续检索、筛选、沉淀素材与结论，直到信息饱和或达到约束。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `research.question.set{question_ref, scope}`；`research.source.added{source_ref, digest}`；`research.finding.recorded{finding_ref, evidence_refs[]}`；`research.saturation.reached{reason}`（可选） |
| 产生者 | 问题 = 外部/模型经受理；素材与结论 = harness 声明（带来源引用） |
| 触发与受理 | 新素材 / 问题变更 / 模型请求下一轮 → 开轮；同素材重复入库幂等 |
| 投影 | 问题 + **素材目录（指针）** + 上次结论；按需召回（recall 引用，成本挂 Round） |
| 逻辑 | 检索计划、引用完整性要求、饱和度停止；召回是**模型辅助调用** |

## 通用原语映射

P1 声明｜P2 受理｜P3 触发｜P4 投影（含 recall 引用）｜P5 逻辑｜P6 身份（`source_ref`/digest）｜P7 观测（预算）。

## 边界与反例

- **恢复不重放召回调用**：重放只恢复已记录事实，不重做检索（glossary:111-112；v5:163）。
- 素材正文落 `content/` 或按引用存放；模型看到的是**指针**（给指针不灌全文）。
- 反例：把检索结果全量灌进上下文；用召回结果冒充新的因果事实；把索引放进演进史。

## 框架缺口

**模型辅助召回的契约**：Projection 声明 recall 引用、成本挂 Round、恢复不重放——目前只有语义，缺正式接口与观测方式。

## 8.10 system-design

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
- **实现**（可运行代码/仓库）在外部 Userspace，**不进工作目录**（v5:38、G1:25）；
- 单元验收条件可含"协议与实现一致"的 checker，但须独立证据。

## 框架缺口

- **条件受理（`base_rev` 比较交换）**：需要通用的"以某版本为基础，否则拒绝"受理语义（现在只是候选，未成契约）。
- **冻结与修订**：把"已接受即只读、改动走修订"做成通用原语，还是仅由 admission 规则表达？待更多示例判定。
- **失效传播 / 依赖**：改祖先 → 后代失效需要通用依赖表达，否则每个 harness 自造一套。

## 现实参照

本仓库（Loom）自身的开发流程就是这个 harness 的一个实例：门（gate）、修订（amendment）、反例先行、证据准入、已通过项不静默改、影响分析。**可作观察来源，但不是框架标准**。

## 8.11 voice-assistant

# harness 示例：voice-assistant（实时语音助手）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。
详设：[../voice-assistant/README.md](../voice-assistant/README.md)（架构、双工、风格预设、供应商、验证计划）。

## 场景

用户与助手**实时语音对话**：流式听（ASR）→ 按预设风格**只讲重点**地回答 → 流式说（TTS）；
随时可打断（全双工）。要点：**语音模型可替换**，实时音频不进事实流逐片落库。
**一个助手 = 一个长期 work**：一次会话是 work 内的 `session` 区间，`voice.session.ended` 不是 work 完成。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | 完整清单（产生者/触发/幂等键/最小闭环）见 [../voice-assistant/events.md](../voice-assistant/events.md)。最小闭环：`voice.session.started → voice.session.configured`、`voice.user.turn.final → voice.turn.completed`、`voice.user.barge_in`、`voice.reply.condensed`、`voice.session.ended`、`voice.style.set`；冷路径触发 `sys.memory.size`/`sys.idle`/`sys.userspace.changed` → 产物 `voice.memory.consolidated`/`voice.userspace.card.updated`；观测 `sys.voice.*` |
| 产生者 | `voice.user.*`、`voice.session.*`、`voice.turn.completed`、`sys.voice.*` = **会话层观测/外部受理**；`voice.session.configured`、`voice.reply.condensed` = **harness 声明**；`voice.style.set` = 外部（用户/上游）受理 |
| 触发与受理 | `voice.session.started` → 开轮（载记忆+风格，产出策略包）；`voice.user.turn.final` → 开轮（更新记忆、演进策略包）；受理按 `session_id + turn_id` 幂等；`style.set` 用 `base_rev` 条件受理 |
| 投影 | **当前轮 + 生效风格预设 + 有界记忆摘要（要点，非全文）+ 全文/音频指针**；不展开历史全文 |
| 逻辑 | **两套策略实例**（多实例角色 R4）：会话侧＝轮次状态机 + 口语预算守门（超预算 → 有损压缩 + `reply.condensed` 记 `from_ref/kept_ref`）+ 打断后续说；维护侧＝用户空间认知/记忆整理/索引重建（见 [../voice-assistant/latency-and-curation.md](../voice-assistant/latency-and-curation.md)）。策略包版本与生效边界（本轮不换） |

**语音机制属于本 harness**（`harness/ext/voice/`：端口、适配器、会话编排 runner），**不是框架设施**；
runtime 只按 `extensions[kind=session-runner]` 起停它，不理解音频
（[../voice-assistant/assistant-work.md](../voice-assistant/assistant-work.md)）。

## 通用原语映射

P1 声明（`voice.*` + 契约 + `extensions` 声明会话组件）｜P2 受理（轮次级事实、`base_rev` 条件）
｜P3 触发（`session.started`/`turn.final`）｜P4 投影（要点 + 指针）｜P5 逻辑（预算守门/状态机）
｜P6 身份（`session_id`/`turn_id`/`reply_id` + `spec_ref` 版本）｜P7 观测（`sys.voice.*` 延迟/打断）
｜P8 保留名（`sys.*` 归 runtime）。

## 边界与反例

- **长期 work，不因会话结束而完成**：`voice.session.ended` 只是事实；归档是管理动作。
- **实时音频不进事实流**：ASR partial、TTS chunk 属观测域/artifact；面事实只到轮次级（landing §4.4 情况 2）。
- **不是通用终态**：`voice.turn.completed` 只让本轮收尾；"说完了"不是业务完成（v5:161,208）。
- **裁剪不删依据**：口语压缩只改可见视图，完整答案仍版本化可达（v5:252）。
- **空闲零驻留**：会话活则 runner 在，`session.ended` 即释放；不把每个工作变成常驻 Agent（v5:90）。
- **会话层不写工作状态**：只发事件经受理落面（landing §4.4 E1/E2、§8）。
- 反例：把整段答案朗读出来（未压缩、未给指针）；用固定静音阈值冒充轮次检测；
  自己写 WebRTC/Opus/VAD；把模型/端点写死在一个供应商；把密钥写进工作目录；
  把"一次会话"当成一个 work 从而丢掉跨会话记忆。

## 框架缺口

只记"缺哪个**通用**原语"，不新增领域目录：

1. **harness 声明的长驻会话组件（session-runner）**：runtime 按事件起停/监督/释放一个 harness 自有组件
   （`extensions[kind=session-runner]`），不理解音频；在它落地前 runner 可由外部启动（降级路径存在）。
2. **出站投递/通知**：策略包如何**送达会话层/外部 runner**——与 ask-user 的"对外通知/投递原语"同题，尚无规范契约。
3. **流式观测通道**：有序分片（ASR partial / TTS chunk）需要"分片 + 引用"的通用观测形态，
   否则要么灌爆事实流，要么各 harness 自造。
4. **二进制 artifact 通用化**：把图像 artifact 通道（backend-seam §5a）泛化为任意媒体 artifact
   （音频/视频）：落盘 → 摘要 → 引用。
5. **runtime 调度机制**（标准 crontab + 事件定义 → `sys.schedule.fired`；另有 `sys.clock` 供谓词式时间）：
   **复用成熟调度工具、不自定义语法、不重新实现**；两条纪律是"权威在工作数据、crontab 是派生物"
   与"cron 只叫醒 runtime、不写事实"。承诺/提醒/monitoring/超时共用
   （[../voice-assistant/scheduling.md](../voice-assistant/scheduling.md)）；与 monitoring 示例同一个缺口。


---

# 9. 事件词表清单
> 来源：由 lore_harness/*/contracts 与 admission/main.py 机械生成

| harness | 契约声明的 kind（contracts/*.json） | admission 受理（ACCEPTED） |
|---|---|---|
| archive | `archive.performed`, `archive.requested`, `sys.context.usage`, `sys.tool.result` | archive.requested |
| ask_user | `ask.answered`, `ask.requested`, `sys.tool.result`, `work.completed`, `work.objective.set` | work.objective.set, ask.answered |
| coding | `code.change.declared`, `code.test.declared`, `sys.tool.result`, `work.completed`, `work.objective.set` | work.objective.set |
| delegation_child | `sys.tool.result`, `work.completed`, `work.delegated`, `work.reported` | work.delegated |
| delegation_parent | `sys.tool.result`, `work.completed`, `work.delegated`, `work.objective.set`, `work.reported` | work.objective.set, work.reported |
| goal | `sys.tool.result`, `user.message`, `work.completed`, `work.objective.set`, `work.phase.changed` | work.objective.set, user.message |
| monitoring | `monitor.condition.expired`, `monitor.condition.met`, `monitor.condition.set`, `monitor.signal`, `sys.tool.result` | monitor.condition.set, monitor.signal |
| plan | `plan.completed`, `plan.created`, `plan.revised`, `plan.stage.completed`, `plan.stage.started`, `sys.tool.result` | plan.created, plan.revised |
| research | `research.finding.recorded`, `research.question.set`, `research.saturation.reached`, `research.source.added`, `research.source.invalid`, `research.source.retracted`, `research.source.verified`, `sys.action.rejected`, `sys.recall.result`, `sys.tool.result`, `work.completed` | research.question.set |
| system_design | `design.amendment.accepted`, `design.amendment.requested`, `design.freeze.violation`, `design.objective.set`, `design.unit.accepted`, `design.unit.frozen`, `design.unit.stale`, `sys.action.rejected`, `sys.declaration.rejected`, `sys.tool.result`, `work.completed` | design.objective.set, design.amendment.requested, design.amendment.accepted |
| fixture_liveness（验证夹具） | `liveness.done`, `liveness.request`, `sys.action.rejected`, `sys.tool.abandoned`, `sys.tool.check`, `sys.tool.result`, `sys.tool.started` | — |

注：`sys.*` 为 Runtime 保留前缀（sys.tool.* / sys.action.rejected / sys.declaration.rejected / sys.schedule.fired 等见第 5、6 章）；业务 kind 由各 harness 契约声明，digest 内容寻址。

---

# 10. CLI 参考
> 来源：由 lore_work/cli.py 机械生成

- `lore_work create` — create a work directory from a harness template
- `lore_work admit` — admit an external fact through Fact Admission
- `lore_work run` — run one Round if a trigger condition is met
- `lore_work status` — print work status
- `lore_work facts` — print the fact stream
- `lore_work recover` — quarantine facts beyond the commit point (interrupted Round)
- `lore_work relate` — declare cross-work wants/grants (PEER:KIND[,KIND])
- `lore_work register` — (re-)register an existing work in this root's host authority (import/adopt)
- `lore_work relay` — relay one event through another work's Fact Admission (authorized by wants+grants)

参数（节选自源码 help）:
  - `--userspace` authorized file range outside the work dir (repeatable; path)
  - `--tool-check-interval` seconds between sys.tool.check observations (never kills)
  - `--tool-budget` default policy budget in ms for calls without budget_ms (ends the wait -> timeout)
  - `--tool-hard-cap` runtime resource safety net in seconds (-> abandoned, unknown)

---

# 11. 前瞻设计：语音助手 Work（B16，全部 UNVERIFIED 设计稿）
> 来源：design/g3/voice-assistant/ 全部 13 文件原文——作为通用原语充分性的压力测试来评审

## 11.1 README

# 语音助手 Work：实时语音能力的抽象与工作定义

状态：**设计稿（UNVERIFIED）**。只做设计、调研与预登记用例；未实现、未验收，不声称任何能力通过。
来源：用户 2026-09-17 要求——"再设计一个语音助手 work；语音这里做好抽象（可替换模型）；
流式语音输入、语音输出（按用户预设风格，可回答重点而非朗读全部）；语音双工交流
（做好抽象，开源有成熟方案的，别乱造轮子）"。

**已完成的探索性观测（不是验收证据，单机少量样本）**：Ark plan `glm-5.3-flash` 流式可用
（`reasoning_effort:minimal` 显著降低首字延迟）；豆包 plan TTS 单向流式出声（首音频 ≈0.35 s）；
豆包 plan ASR 用序列帧跑通一次 **TTS→ASR 真实往返**（部分结果逐字增长，末帧 `definite:true`）；
plan 语音网关用 `X-Api-Key` 单一 Key 鉴权。细节与边界见 [providers.md](providers.md)。

相关：[harness-catalog/voice-assistant.md](../harness-catalog/voice-assistant.md)、
[work-directory-landing.md](../work-directory-landing.md) §4.3–4.7（五件套、P1–P8、信息项/投影/呈现）、
[../../backlog.md](../../backlog.md) B16、[docs/validation-status.md](../../../docs/validation-status.md)。

## 已确认的定义（用户 2026-09-17 裁决）

1. **长期关系 = 一个 work**：助手是**长期 work**；一次会话是 work 内的 `session` 区间，
   `voice.session.ended` 不等于 work 完成（像 monitoring 一样长期在册、空闲不驻留）。
2. **语音只属于助手 harness**：端口/适配器/会话编排放在 `harness/ext/voice/`，
   **不新增框架设施**；代价是语音能力不可被其他 harness 直接复用（有意的隔离换简单）。
3. **要落在工作目录里**：具体实例形态见 [assistant-work.md](assistant-work.md)
   （目录解剖、会话事件流、与 runtime 的唯一通用机制、生命周期）。

> 三层"定义"要分清：**Assistant Profile**（人格/风格/策略/语音绑定，用户可改）→
> **Assistant Harness**（推进策略 + 语音机制，登记后只读）→ **Assistant Work 实例**（状态与记忆）。

## 这个工作要治的病

1. **语音能力绑死一家模型**：ASR/TTS/LLM 直接写死在编排代码里，换供应商要动业务逻辑。
2. **把整段答案朗读出来**：语音是线性、不可跳读的通道；把文档全量转成语音既慢又没用，
   用户要的是**结论与要点**，细节按需展开。
3. **只会"你说完我再答"（半双工）**：不能打断、不能插话、不能边听边说。
4. **重造音频轮子**：自己写 WebRTC/Opus/抖动缓冲/VAD/端点检测，既难验证又违背成熟复用。

## 范围

**做**：

- 语音能力端口抽象（ASR / TTS / 轮次检测 / 对话模型 / 音频传输）与**可替换模型**的换装纪律；
- 流式语音输入（partial → final）与流式语音输出（首音频尽早、可取消）；
- 用户预设**说话风格**（风格预设）与"**只讲重点、细节按需展开**"的口语化渲染链路；
- **全双工**会话：打断（barge-in）、轮次检测、回退与重连，抽象到可替换的实时编排后端；
- **对话记录**：目录化的原始音频 + 元数据，按端点切成片段，语音/文本同构，预留语气/情绪/人物识别扩展位；
- 与 Loom 工作目录/runtime 的接缝（事件、事实、投影、权限、凭据），以及可执行的验证计划。

**不做**（非目标，防止把设计变成平台）：

- 不自研音频传输、编解码、抖动缓冲、回声消除、VAD 模型（复用成熟开源方案）；
- 会话组件（runner）不直接写工作状态：只经事件入口落事实，不绕开受理与单写者；
- 不把语音做成框架级通用设施（本轮裁决②）；也不定义通用"语音终态"、不把"说完了"当业务完成（v5:161,208）；
- 不在工作目录、证据或日志里放密钥（对齐 glossary:100-102）；
- 不在本稿确定具体容量/SLA 数字；延迟目标先测量再定（对齐 v5:349 "毫秒级 SLA 不冻结"）。

## 文件索引

| 文件 | 内容 |
|---|---|
| [events.md](events.md) | **词表 + 契约**：该定义哪些事件、哪些根本不是事实、产生者/触发/幂等键、最小闭环集合 |
| [scheduling.md](scheduling.md) | **定时与日程**：日程归助手、机制归 runtime；runtime **复用标准 crontab + 事件定义**（不自定义、不重实现）；两条纪律（权威在工作数据 / cron 只叫醒不写事实）；`sys.clock` 谓词式时间；`adapter.error` 归属；§3.1 调度后端选型 |
| [execution-timeouts.md](execution-timeouts.md) | **执行存活检查**：默认到点发 `sys.tool.check`（**不自动杀**），怎么办归 harness；runtime 保留硬上限与资源安全网（回收即 `abandoned/unknown`）；超时≠未执行；为什么不做逐次提醒；in-band `timeout` 只是纵深 |
| [conversation-record.md](conversation-record.md) | **对话记录**：目录化的原始音频 + 元数据、双工端点切片、文本/语音同构、语气/情绪/人物识别扩展位；**权威在事件、目录是物化**（§6） |
| [assistant-work.md](assistant-work.md) | **实例形态**：一个助手 = 一个长期 work 的目录解剖、会话事件流、语音在 `harness/ext/voice/`、生命周期、归属问题 |
| [latency-and-curation.md](latency-and-curation.md) | **及时响应 vs 知识维护**：同一 work 内两个策略实例（会话循环/维护循环）、延迟预算与削减手段、用户空间认知、维护时机（会话边界/变更/阈值/空闲）、一致性边界 |
| [architecture.md](architecture.md) | 助手 harness 内的会话层/工作层、端口与适配器、注册与能力协商、"谁生成要说的文本"三案对比 |
| [duplex.md](duplex.md) | 双工状态机、打断语义、轮次检测、实时编排后端的接缝与选型、会话资源零驻留 |
| [style-profiles.md](style-profiles.md) | 风格预设 schema、"回答重点"的三层链路（信息项/投影/呈现）+ 守门与无损引用 |
| [providers.md](providers.md) | 具体适配规范：Ark `glm-5.3-flash`、豆包 ASR/TTS 2.0（含 2026-09-17 实测观测，不含密钥） |
| [validation-plan.md](validation-plan.md) | 预登记验证用例与证据要求（未执行） |
| [research-notes.md](research-notes.md) | 开源实时语音框架与协议调研来源、结论与未决 |
| [probe_plan_endpoints.py](probe_plan_endpoints.py) | **探索性**探针（非证据）：实测 plan LLM / 豆包 TTS 单向 / ASR；只打印变量名不打印密钥 |

## 核心判断（一句话版）

**助手 = 一个长期工作（harness 拥有策略与语音）+ 若干会话区间 + 一层可替换的语音模型端口；
runtime 只按通用机制起停 harness 声明的长驻会话组件。** 音频不进事实流逐片落库；进工作面的是
**轮次级**语义事件与软引用。"回答重点"是**投影/呈现策略**，不是删内容——被压缩的是可见视图，
完整答案仍有版本化依据（v5:252）。

## 追溯

| 本稿判断 | 来源 |
|---|---|
| **长期关系 = 一个 work；语音只属于助手 harness；落在工作目录** | **用户 2026-09-17 裁决** |
| 会话组件（runner）由 runtime 按通用机制起停、空闲释放 | v5:90（等待期零驻留）；[assistant-work.md](assistant-work.md) §5–6 |
| 音频不进事实流逐片落库 | v5:131/149（事件可作输入视图、输入边界固定）；landing §4.4 情况 2 |
| 端口化换模型、能力协商、响亮拒绝 | `lore_provider` 既有换基线纪律（design/g3/provider/amendment-model-baseline-*.md）；glossary:43（harness 登记后只读） |
| "只讲重点"是投影/呈现而非删内容 | work-directory-landing §4.6 示例 3（archive 只缩视图）、§4.7（信息项/投影/呈现三层）、v5:252 |
| 用户配置与模型产物分家（风格/边界 vs 记忆/表达） | [assistant-work.md](assistant-work.md) §7；landing §4.4 E5（内容不是侧信道） |
| 风格预设/策略不在一轮中途静默替换 | v5:204、v5:349；landing §4.5 R2/R3 |
| 凭据在仓库外、进程内 | glossary:100-102；`~/.env` 变量名 `ARC_PLAN_API_KEY`（值不落库） |
| 二进制 artifact 走摘要+引用 | design/g3/x/backend-seam.md §5a（图像 artifact 模式的泛化） |

## 11.2 assistant-work

# 助手 Work 实例形态（一个助手 = 一个长期 work）

状态：UNVERIFIED 设计稿。本文件按用户 2026-09-17 的三项裁决落地：
① **长期关系 = 一个 work**（会话是 work 内的 session 区间，不是新 work）；
② **语音只属于助手 harness**（端口/适配器/会话编排都在 `harness/ext/voice/`，不新增框架设施）；
③ **要落在工作目录里**（本文件给出一个具体实例的目录解剖、会话模型与事件流）。
相关：[README.md](README.md)、[architecture.md](architecture.md)、[duplex.md](duplex.md)、
[style-profiles.md](style-profiles.md)、[providers.md](providers.md)、
[../work-directory-landing.md](../work-directory-landing.md) §4–§8。

## 1. 定义收敛（三层，一层都不能少）

| 层 | 定义 | 归属 | 可变性 |
|---|---|---|---|
| **① 助手档案 Assistant Profile** | 人格、默认风格、能力/工具白名单、安全边界、记忆策略、语音/音色绑定 | 助手 harness 自带的模板 + 每 work 的用户配置 | 用户/管理面改 = 新 revision；模型只能**提案** |
| **② 助手 harness** | 推进策略（何时开轮/看什么/怎么守门）**+ 语音机制**（端口/适配器/会话编排） | `harness/`（登记后只读） | 改一字节 = 新 harness 版本 = 新绑定 |
| **③ 助手 work 实例** | 一个具体助手的存在：目录、事实、记忆、会话史、授权 | 工作目录 | 由事件推进；关系结束才归档 |

**关键判据**：一次会话的结束**不是** work 的结束。`voice.session.ended` 只是事实；
work 的 `state.lifecycle` 仍为 `active`（像 monitoring 一样长期在册，但**空闲期不驻留进程**）。

## 2. 一个实例的目录解剖

```
<works-root>/<assistant-work-id>/
├── work.json                       # 身份与绑定（runtime/管理面写）
│   ├─ identity        : {assistant_id, display_name, owner_ref}
│   ├─ harness         : {ref:"voice-assistant", digest:"sha256:…"}
│   ├─ assistant       : {                                           # ← 用户可改的配置（非模型可写）
│   │     persona_ref  : "content/persona.md@<rev>",                 #   指向 content 的版本
│   │     style_default: "cfg:brief-professional-zh",
│   │     style_refs   : ["cfg:brief-professional-zh", "cfg:warm-zh"],
│   │     memory_policy: {max_summary_tokens, recall_k, retention},
│   │     session_policy:{idle_timeout_s, max_session_s, barge_in:true}
│   │   }
│   ├─ voice_refs      : {asr:"doubao-seed-asr-2.0@ver", tts:"doubao-seed-tts-2.0@ver",
│   │                     llm:"ark-glm-5.3-flash@ver", turn:"silero+smart-turn@ver"}
│   ├─ relations/grants: {…}
│   └─ state           : {lifecycle:"active", last_session_id, last_active_at}
├── harness/                        # 推进定义 + 语音机制（登记后只读，模型不可写）
│   ├── manifest.json               # voice.* kinds + triggers + roles + extensions
│   ├── conventions/                # content/ 内部约定（persona/style/memory/conversations 形状）
│   ├── projection/main.py          # 看到什么：当前轮 + 生效风格 + 有界记忆要点 + 指针
│   ├── presentation/main.py        # 口语化呈现：把风格预设编成 system prompt/请求形式
│   ├── rounds/main.py              # 何时开轮：session.started / turn.final / turn.completed / session.ended
│   ├── admission/main.py           # 收什么：turn/session/style，幂等；style 带 base_rev 条件受理
│   ├── logic/main.py               # 轮次状态机、预算守门、记忆更新、打断后续说
│   └── ext/voice/                  # ★ 语音机制——只属于本 harness（裁决②）
│       ├── ports.py                # SpeechToText/TextToSpeech/TurnDetector/ConversationModel 端口
│       ├── adapters/doubao_asr.py  # 豆包 plan ASR（序列帧，见 providers.md §3）
│       ├── adapters/doubao_tts.py  # 豆包 plan TTS（事件帧，见 providers.md §2）
│       ├── adapters/ark_llm.py     # Ark plan glm-5.3-flash（SSE，reasoning_effort）
│       ├── adapters/fake.py        # 离线适配器（一致性套件锚点）
│       ├── registry.json           # 能力描述 + 音色目录 + credential_ref（只记变量名）
│       └── runner.py               # 长驻会话进程入口（T2；按 session 起停）
├── surface/
│   ├── content/                    # ★ 模型唯一可写区（助手记忆本体）
│   │   ├── persona.md              # 人格与边界（模型可演进；用户配置只**引用**其版本）
│   │   ├── style/<style-id>.json   # 模型提案落草稿；用户接受后成为 cfg 条目
│   │   ├── memory/index.md         # 长期记忆索引（主题 → 文件 + 摘要）
│   │   ├── memory/<topic>.md       # 主题记忆（要点/摘要，不是全文流水）
│   │   ├── userspaces/index.md     # 用户用户空间清单：id·用途·指针·最近观测 revision（见 latency-and-curation.md §3）
│   │   ├── userspaces/<ws-id>.md   # 用户空间卡片：用途/结构/入口/注意事项（认知 ≠ 授权）
│   │   └── conversations/<session-id>.md   # 每次会话的摘要与要点
│   ├── head                        # 唯一提交点（runtime 原子推进）
│   └── facts.jsonl                 # voice.* 事实流（runtime 单写者）
├── session/                        # 观测域（runtime/runner 写）：事件时间线、时延
│   ├── sessions/<session-id>/events.jsonl
│   └── records/<session-id>/       # ★ 对话记录：原始音频 + 元数据，按端点片段目录化
│       ├── session.json · timeline.jsonl · manifest.json
│       └── segments/<seg-id>/{audio.*, meta.json, text.txt, words.jsonl, analysis/…}
│                                   # 见 conversation-record.md（含语气/情绪/人物识别扩展位）
├── ledger/                         # admission 去重账、round 记录
└── derived/                        # 投影缓存、recall 索引（可删重建）
```

**与框架的关系**：新增的一切都在 `harness/ext/voice/`（扩展命名空间，landing §4.5 允许），
**没有新增框架目录**；`content/` 内部结构由本 harness 的 `conventions/` 决定。

## 3. 会话模型与事件流

一次会话 = work 内的一段区间（`session_id`），不是新 work。

```
voice.session.started{session_id, transport, style_id}          ← 媒体侧观测/外部受理
        │  触发轮：载入记忆+风格 → 产出
        ▼
voice.session.configured{session_id, bundle_ref, style_rev}     ← harness 声明（策略包）
        │
        │  媒体 runner（harness/ext/voice/runner.py）在 bundle 约束下跑：
        │  ASR 流式 → 轮次检测 → 流式 LLM → 流式 TTS
        │
voice.user.turn.final{turn_id, transcript, lang, audio_ref}     ← 观测
        │  （runner 同时进行流式回复；用上一份已提交 bundle）
        ▼
voice.turn.completed{turn_id, reply_ref, tool_calls, timings, interrupted}  ← 观测
        │  触发轮：写 conversations/<session-id>.md，必要时更新 memory/
        ▼
voice.user.barge_in{turn_id, at_ms, transcript_so_far?}         ← 观测（打断，是事实不是取消）
voice.style.set{style_id, spec_ref, base_rev}                   ← 外部受理（用户改风格；陈旧基线拒绝）
voice.session.ended{session_id, duration_ms, turn_count}        ← 观测 → 触发轮：会话收尾
```

**"谁生成要说的文本"**（与 [architecture.md](architecture.md) §3 的 R3 一致，但现在是 harness 内部）：
回复由 **harness 自己的 runner** 流式生成，约束来自 harness 的 `presentation/projection` 产出的策略包；
工作轮负责持久化与记忆演进。**本轮不换策略**（v5:204），新 bundle 下一轮生效。

**音频不进事实流**：ASR partial / TTS chunk 落 `session/sessions/<id>/`（观测域）与 artifact 引用；
面事实只到轮次级。

## 4. 语音机制在 harness 内的布局（裁决②）

- **端口与适配器**（[architecture.md](architecture.md) §2 的 Protocol）放在 `harness/ext/voice/`，
  是 harness 的普通代码；换模型 = 换 `voice_refs` 绑定 + 复跑同一套一致性用例。
- **会话编排**（双工状态机、barge-in、重连）在 `ext/voice/runner.py` 与 `session.py`；
  复用开源编排后端（LiveKit Agents / Pipecat）时，它同样被包在 `ext/voice/` 里，**不进 runtime**。
- **凭据**：`registry.json` 只写 `credential_ref:"env:ARC_PLAN_API_KEY"`，值只在 runner 进程内读；
  不落工作目录、证据、日志。
- **代价（诚实记录）**：语音能力因此**不可被其他 harness 直接复用**；若将来要复用，
  再把它提升为框架设施或共享库——这是一次**有意的隔离换简单**，不是能力缺失。

## 5. 与 runtime 的交互：唯一需要补的通用机制

harness 的常规角色（`projection/presentation/rounds/logic/admission`）都由 runtime 按 manifest 调用，
够用。缺的是：**一个 harness 声明的长驻会话组件，由 runtime 起停与监督**。

```json
// harness/manifest.json 片段（候选）
"extensions": [
  { "id": "voice", "kind": "session-runner", "ref": "ext/voice/runner.py",
    "digest": "sha256:…", "lifecycle": { "start_on": ["voice.session.started"],
    "stop_on": ["voice.session.ended"], "idle_timeout_s": 60 } }
]
```

- 这是**通用**机制（不是语音专属）：任何需要长驻会话的 harness 都能声明组件；
  runtime 只做"按事件起停 + 释放 + 崩溃不重放已确认输出"，不理解音频。
- 在它落地前，runner 只能由外部（操作者/独立服务）启动，harness 仍能处理轮次级事件——
  即**降级路径存在**，不阻塞其余设计。
- **登记为通用原语缺口**（见 [../harness-catalog/voice-assistant.md](../harness-catalog/voice-assistant.md)），
  不新增领域目录。

## 6. 生命周期与零驻留

| 阶段 | 动作 |
|---|---|
| create | 实例化 harness 模板 + `content/` 骨架（persona 空稿、style 默认、memory 空索引）+ `work.json` |
| register | host 侧登记/授权；绑定 harness digest、voice_refs、Userspace（若有） |
| session | `voice.session.started` → runtime 起 runner（T2）→ 轮次级事件驱动 work 轮 |
| idle | `voice.session.ended` → **释放 runner 与工作专属媒体资源**；work 仍在册、`lifecycle=active`（v5:90） |
| archive | 关系结束 → 管理动作 Archive：停止求值/受理；**不是** `voice.session.ended` 的自动结果 |
| export/import | quiesce 后拷贝目录即导出；新宿主须重授权；`derived/` 可删重建 |

## 7. 归属问题（本文件新增，需留意）

- **用户配置 vs 模型产物**：`work.json.assistant` 是**用户/管理面**可写（风格列表、策略、绑定），
  模型不可写；`content/` 是**模型**可写（人格演进、记忆、会话摘要）。
  模型想改风格 → 提案（`voice.style.proposed`）→ 用户接受 → 配置新 revision（带 `base_rev`）。
  这样"用户预设的风格"与"模型学到的表达"不会互相覆盖。
- **persona 的边界**：安全边界在配置（`assistant.persona_ref` 指向的版本 + `session_policy`），
  表达风格在 content。边界不允许模型单方面放宽。
- **记忆**：只存**要点/摘要 + 指针**，不存全文流水（v5:250/252）；recall 索引在 `derived/`。

## 8. 未决

- **U1 session runner 生命周期**：runtime 通用机制（推荐）vs 外部服务 vs 借用 `shell` 长驻。
- **U2 记忆策略**：摘要粒度、何时合并、保留期（隐私：语音是生物特征，默认策略需单独裁决）。
- **U3 回复生成位置**：runner 流式（推荐，低延迟）vs 工作轮生成（事件权威更强、延迟高）。
- **U4 多会话并发**：同一助手同时多个会话是否允许；允许则 runner 实例与 `session_id` 的对应关系。
- **U5 音频 artifact**：`session/` 引用 vs 版本化 artifact（F 通道泛化，仍属框架缺口）。

## 11.3 architecture

# 语音助手：架构与语音能力抽象

状态：UNVERIFIED 设计稿。接口签名为**候选契约**，进组件合同时逐项裁决并经独立用例。
按用户 2026-09-17 裁决，语音**只属于助手 harness**：下面的"会话层/工作层"是**同一个 harness 内部**的
两层，不是 runtime 的两套设施；实例形态见 [assistant-work.md](assistant-work.md)。
相关：[README.md](README.md)、[assistant-work.md](assistant-work.md)、[duplex.md](duplex.md)、
[style-profiles.md](style-profiles.md)、[providers.md](providers.md)。

## 1. 助手 harness 内的两层

```
┌───────────────────────────────────────────────────────────────────┐
│ 助手 harness · 工作层（事件驱动、持久、策略；runtime 按 manifest 调用）│
│   词表 voice.* ｜ 受理 ｜ 触发 ｜ 投影/呈现 ｜ 逻辑/守卫             │
│   持：会话事实、风格预设引用、记忆、工具与安全策略、口语化渲染策略     │
│   不持：音频缓冲、连接、解码器、TTS 会话（都在会话层）              │
└───────────────▲───────────────────────────────┬───────────────────┘
       轮次级语义事件 / 软引用             策略包（system prompt、
   （transcript、reply 文本、时延、打断）    风格预设、工具 schema）
                │                               ▼
┌───────────────┴───────────────────────────────────────────────────┐
│ 助手 harness · 会话层 `harness/ext/voice/`（长驻实时，复用开源编排）│
│   runner.py：transport(WebRTC/WS) · Opus · 抖动缓冲 · VAD · 轮次检测│
│   · 流式 ASR · 流式 LLM · 流式 TTS · 打断/回退 · 重连              │
│   由 runtime 按通用机制起停（session-runner）；不写工作状态，只发事件│
└───────────────▲───────────────────────────────────────────────────┘
                │  统一端口（本稿定义的抽象）
┌───────────────┴───────────────────────────────────────────────────┐
│ 语音模型端口 Voice Provider Ports（可替换模型）                     │
│   SpeechToText · TextToSpeech · TurnDetector · ConversationModel   │
│   · AudioTransport ；适配器：doubao / ark / fake（离线）           │
│   实现位于 `harness/ext/voice/adapters/`（harness 自有，非框架设施）│
└───────────────────────────────────────────────────────────────────┘
```

**为什么 harness 内还要分两层**：runtime 的单位是有界 Round + 单写者提交 + 等待期零驻留
（v5:90、landing §6）。实时语音是连续音频流、亚秒级时序、随时打断——放进 Round 提交模型就要求
每个会话常驻一个进程。所以**实时在会话层（长驻、harness 自有），语义在工作层（按轮次）**；
两层都在助手 harness 内，runtime 只提供"起停 harness 声明的长驻会话组件"这一通用机制
（[assistant-work.md](assistant-work.md) §5）。会话层不直接改工作状态，只发事件经受理落面
（landing §4.4 E1/E2）。

## 2. 语音能力端口（可替换模型的关键）

端口是**本系统自己的窄接口**，不是某个开源框架的类型。编排框架（见 [duplex.md](duplex.md) §4）
是被适配的对象；换框架不改工作面，换模型不改编排。全部为异步、流式、可取消。

```python
# 候选契约（Protocol 为结构声明，运行期实现由适配器提供）

class AsrConfig(TypedDict):
    provider: str            # 例 "doubao-seed-asr-2.0"
    model: str               # 例 "volc.seedasr.sauc.duration"
    sample_rate: int         # 16000
    channels: int            # 1
    language: str            # "zh-CN"
    interim: bool            # 是否要 partial

class AsrEvent(TypedDict):
    kind: Literal["partial", "final", "error"]
    text: str
    definite: bool           # final 才算 definite
    seq: int                 # 单调，用于排序/去重
    ts_ms: int               # 相对会话起点
    words: list | None       # 可选词级时间戳（用于打断定位）

class SpeechToText(Protocol):
    async def open(self, cfg: AsrConfig) -> "AsrStream": ...

class AsrStream(Protocol):
    async def push(self, pcm: bytes, *, ts_ms: int) -> None: ...
    async def finish(self) -> None: ...           # 显式结束一轮
    async def cancel(self) -> None: ...            # 打断/放弃当前轮
    def events(self) -> AsyncIterator[AsrEvent]: ...

class TtsConfig(TypedDict):
    provider: str            # "doubao-seed-tts-2.0"
    model: str               # "seed-tts-2.0"
    voice: str               # 供应商音色 id（由能力描述校验）
    format: Literal["pcm", "mp3", "ogg_opus"]
    sample_rate: int
    style: "StyleParams"      # 见 style-profiles.md

class TtsEvent(TypedDict):
    kind: Literal["audio", "sentence_start", "sentence_end", "end", "error"]
    seq: int
    audio: bytes | None      # kind == "audio"
    text: str | None         # sentence_* 携带该句原文，便于字幕/对齐
    ts_ms: int

class TextToSpeech(Protocol):
    async def open(self, cfg: TtsConfig) -> "TtsStream": ...

class TtsStream(Protocol):
    async def push_text(self, text: str) -> None: ...   # 可多次，增量喂句
    async def finish(self) -> None: ...
    async def cancel(self) -> None: ...                 # 打断：立即停止出声
    def events(self) -> AsyncIterator[TtsEvent]: ...

class TurnEvent(TypedDict):
    kind: Literal["speech_start", "speech_end", "turn_end", "backchannel"]
    ts_ms: int
    confidence: float

class TurnDetector(Protocol):
    """VAD + 语义端点判定。实现可组合 VAD 模型与 turn-detector 模型。"""
    def push(self, pcm: bytes, *, ts_ms: int) -> list[TurnEvent]: ...
    def reset(self) -> None: ...

class ConversationModel(Protocol):
    """OpenAI 兼容流式补全（含 function calling），与 lore_work.provider 同族但必须支持流式。"""
    async def stream(self, messages, *, tools=None, style: "StyleParams", **kw) -> AsyncIterator[dict]: ...
```

### 2.1 能力描述与注册

端口实现者在注册表登记一条**能力描述**（capability descriptor）；会话开始时按声明做能力协商，
不匹配就**响亮拒绝**，不降级、不猜（对齐 landing §4.5 R2）：

```json
{
  "id": "doubao-seed-tts-2.0",
  "port": "tts",
  "adapter": "voice_doubao.tts",
  "models": ["seed-tts-2.0"],
  "formats": ["pcm", "mp3", "ogg_opus"],
  "sample_rates": [8000, 16000, 24000],
  "languages": ["zh-CN", "en-US"],
  "streaming": {"input": "incremental_text", "output": "chunked_audio", "cancel": true},
  "styles": {"emotion": ["neutral", "happy", "sad"], "speech_rate": [-50, 100]},
  "voice_catalog_ref": "artifact:sha256:…",
  "limits": {"max_concurrent_streams": 1},          // 实测填写，不预设
  "credential_ref": "env:ARC_PLAN_API_KEY"           // 只记名字，不记值
}
```

绑定落在 `work.json` 的引用里（`voice_refs`），与 `model_refs` 同族：**绑定 = 能力 id + 固定版本 +
能力描述 digest**。换模型 = 换绑定 = 新版本，走修订记录，一轮进行中不静默替换（v5:204、v5:349）。

### 2.2 换装纪律（可替换不是"接口存在"就算数）

可替换必须**可验证**，否则只是宣称。约定：

1. **一致性套件（conformance kit）**：同一套端口用例对每个适配器复跑——流式顺序、partial/final
   语义、取消后不再出声、错误分类、能力协商拒绝路径。离线用 `fake` 适配器做判据锚点。
2. **不透明标识钉定**：适配器把实测的供应商模型/音色回显钉成常量并校验；别名轮换**响亮失败**，
   不做前缀放行（沿用 `lore_provider` 的 `MODEL_ALIAS` 先例）。
3. **换模型留修订记录**：含独立理由、旧值保留、影响面与重跑范围（沿用
   `design/g3/provider/amendment-model-baseline-2026-09-*.md` 的格式）。
4. **"同套用例跨适配器产出同一组合同事实"作为通过判据**，而不是"两个都能跑"。

## 3. "谁生成要说的文本"：三案对比

语音的延迟预算把这个问题顶到台前。工作 runtime 的 Round 是"投影 → 模型 → 工具 → 提交"，
**提交点在轮末**；token 级流式产出若强行走事实流，会把原子提交模型捅穿（landing §6）。

| 案 | 谁生成回复文本 | 优点 | 代价 / 反例 |
|---|---|---|---|
| **R1 会话层生成** | 会话层 LLM 流式生成 | 首音频最快；工具调用由编排框架原生处理 | 工作面只当配置器，持久策略与回复内容脱节；回答"重点与否"靠 prompt 自觉 |
| **R2 工作面生成** | 工作 Round 生成完整回复后交会话层合成 | 事件权威最干净；策略在工作面 | 首音频要等整段生成；推理模型下不可接受（见 providers.md 实测） |
| **R3 混合（推荐）** | 会话层流式生成，**在一个工作下发的"策略包"约束下**；工作面在每轮后持久化并演进策略包 | 低延迟 + 策略在工作面 + 回复内容成为持久事实 | 需要"策略包"版本与生效边界；本轮产生的新上下文下一轮才生效 |

**R3 的边界规则（候选）**：

- 会话开始（`voice.session.started`）触发工作轮 → 产出 **`voice.session.configured`**：
  策略包引用（system prompt、风格预设 revision、工具 schema、记忆摘要、允许的行动集合）。
- 用户轮结束（`voice.user.turn.final`）→ 会话层在策略包约束下流式生成并播放；
  结束后落 **`voice.turn.completed`**（transcript、reply 文本引用、工具调用集、时延、是否被打断）。
- `voice.turn.completed` 触发工作轮 → 更新记忆/摘要，产出**新的策略包 revision**。
  **本轮不换策略**；新一轮生效（对齐 v5:204 "不在一次已开始的推进中静默换用新策略"）。
- 打断（`voice.user.barge_in`）是事实，不是取消工作推进；被打断的回复保留其引用与截断位置。
- 风格/身份等策略变更走 `voice.style.set{..., base_rev}` 条件受理，陈旧基线拒绝。

> **未决（需测量/裁决）**：R3 的"策略包一轮滞后"是否可接受，取决于工作轮时延与用户感知；
> 若不可接受，退化到 R1 并把策略包的生成放在会话开始 + 空闲期（不逐轮）。见
> [validation-plan.md](validation-plan.md) VO07/VO10。

## 4. 与 Loom runtime / 工作目录的接缝

| 关注点 | 归属 | 规则 |
|---|---|---|
| 音频分片（ASR partial、TTS chunk） | 会话层 + 观测域 | **不逐片进事实流**（流水爆炸）；按会话聚合，分片原件落 `session/` 或 artifact（软引用） |
| 轮次语义（transcript、reply 文本、时延、打断） | 工作层 | 经 Fact Admission 成为 `voice.*` 事实；幂等键 = `session_id + turn_id` |
| 策略包（prompt/风格/工具） | 工作层 `surface/content/` | 版本化产物，由事件引用 revision |
| 音频 artifact | F/artifact（摘要+引用） | 泛化 backend-seam §5a 的图像 artifact：落盘 → sha256 → 引用；不在事实里塞大字节 |
| 凭据 | 进程内存 + 仓库外 env | 只在适配器进程内读 `env:ARC_PLAN_API_KEY`；不落工作目录/证据/日志（glossary:100-102） |
| 会话进程 | harness 自有（T2，目录外） | 会话活则 runner 在，`voice.session.ended` 即释放；由 runtime 按通用机制起停；**工作不常驻专属进程**（v5:90） |
| 执行存活 | 机制在 runtime、策略在 harness | **默认到点发 `sys.tool.check`（不自动杀）**，harness 决定继续/取消/降级；runtime 保留硬上限与资源安全网（回收即 `abandoned/unknown`，不冒充未执行）；harness 声明分级默认与上限（[execution-timeouts.md](execution-timeouts.md)） |
| 业务时钟 | 机制在 runtime、策略在 harness | 日程用标准 crontab + 事件定义、谓词式时间用 `sys.clock`（[scheduling.md](scheduling.md)） |

## 5. 框架原语映射（详见 harness-catalog）

助手只用现有 P1–P8 通用原语即可表达；但暴露**五个**通用原语缺口（只登记，不新增领域目录）：

1. **harness 声明的长驻会话组件**（session-runner）：runtime 按事件起停/监督/释放一个 harness 自有组件，
   不理解音频。这是本设计唯一实际需要的框架新增机制（[assistant-work.md](assistant-work.md) §5）；
   在它落地前，runner 可由外部启动，harness 仍处理轮次级事件（降级路径存在）。
2. **出站投递/通知**：`voice.session.configured`（策略包）如何送达会话层/外部 runner
   （与 ask-user 的"对外通知/投递原语"同题）；若选 R2 方案，还需回复文本的投递。
3. **流式观测通道**：有序分片（ASR partial、TTS chunk）需要一个"分片+引用"的通用观测形态，
   否则只能各 harness 自造或把流水灌进事实流。
4. **二进制 artifact 通用化**：把图像 artifact 通道泛化为任意媒体 artifact（音频/视频）。
5. **runtime 调度机制**：接受标准 **crontab + 事件定义**（复用 bash 环境里的成熟调度工具，
   **不自定义语法、不重新实现**），到点落 `sys.schedule.fired`；另有 `sys.clock` 供谓词式时间。
   两条纪律：权威在工作数据（crontab 是派生物）、cron 只叫醒 runtime 不写事实
   （[scheduling.md](scheduling.md)）；monitoring、plan 截止、ask-user 超时共用。

（完整五件套与本工作的映射见 [../harness-catalog/voice-assistant.md](../harness-catalog/voice-assistant.md)。）

## 6. 开放问题

- **Q-V1**：策略包一轮滞后 vs 每轮重算的时延/质量权衡（需 VO07/VO10 测量）。
- **Q-V2**：部分 ASR（barge-in 时用户只说了半句）算不算一个用户轮？半句是否入记忆？
- **Q-V3**：多模态同时（用户边说边发图/文件）如何与双工会话合流。
- **Q-V4**：会话编排后端选型（Pipecat / LiveKit Agents / 其他）——见 [duplex.md](duplex.md) §4 与
  [research-notes.md](research-notes.md)；它被包在 `harness/ext/voice/`，选型须独立用例后再定。
- **Q-V5**：音频 artifact 的保留期与隐私（语音是生物特征，默认保留策略需单独裁决）。

## 11.4 events

# 助手需要定义哪些事件（词表 + 契约）

状态：UNVERIFIED 设计稿。本文件是五件套①（词表 + 契约）的完整清单，供事件声明与 Fact Contract 使用。
相关：[assistant-work.md](assistant-work.md)、[latency-and-curation.md](latency-and-curation.md)、
[architecture.md](architecture.md)、[../harness-catalog/voice-assistant.md](../harness-catalog/voice-assistant.md)。

## 1. 先立三条规矩（否则词表会失控）

1. **有产生者、有触发或消费者、有稳定身份**：三者缺一就不该定义（没有消费者的声明是死信）。
2. **只有"语义声明"与"轮次级观测"进事实流**：分片、音频、逐 token、VAD 抖动**不是事实**（见 §3）。
3. **`sys.*` 只能由 runtime 声明**（landing §4.5 R5）；助手自有事件一律落在 `voice.*` 命名空间。

另外一条本工作特有的判定：**runner 观测到的现实（用户说了什么、何时打断、时延多少）按 `external` 受理**，
不是 `harness` 声明——runner 是本 harness 的代码，但它报告的是外部世界，必须过 Fact Admission 的契约校验，
一个坏 runner 不能靠"我是 harness"就改写状态。**策略性结论**（配置好什么、压缩了什么、卡片更新了）才按 `harness` 声明。

## 2. 产生者三类 + 触发分流

| 产生者 | 含义 | 本工作里是谁 |
|---|---|---|
| `runtime`（`sys.*`） | runtime 的规范观测 | 上下文用量、空闲、用户空间变更、时延 |
| `harness`（`voice.*`） | 助手的策略性声明 | 策略包、压缩、记忆合并、用户空间卡片 |
| `external`（`voice.*`） | 外来事实，经受理 | 用户轮次、打断、会话起止、风格/偏好设置 |

触发分流（对应 [latency-and-curation.md](latency-and-curation.md) 的两个循环）：

- **会话循环（热）**：`voice.session.started`、`voice.user.turn.final`
- **维护循环（冷）**：`voice.session.ended`、`sys.userspace.changed`、`sys.memory.size`、`sys.idle`、
  `voice.style.set`（配置变更后重建策略包）

## 3. 明确**不是**事实的东西（观测域，落 `session/`）

| 东西 | 为什么不是事实 | 去哪 |
|---|---|---|
| ASR 部分结果（每次刷新） | 流水，不改变任何语义 | `session/records/<id>/timeline.jsonl`（观测） |
| TTS 音频分片 | 大字节 + 流水 | 记录区片段 `segments/<seg>/audio.*`；面事实只带 `seg_id`/`record_ref` |
| VAD / 轮次检测的每次抖动 | 机制噪声 | 观测；只有**切好的片段**（[conversation-record.md](conversation-record.md)）才是记录单位 |
| 投机生成的草稿（被丢弃） | 从未成为已确认输出 | 观测；**留痕但不入面**（v5:332） |
| 工具调用的原始往返 | 局部执行事实 | Session/观测域，经**引用**进面（landing §4.4 情况 2） |
| 逐 token | 流水 | Session |

## 4. 事件清单

标记：**M** = 最小闭环必需；**O** = 扩展。幂等键给出去重口径。

### 4.1 会话

| 事件 | 产生者 | 关键 payload | 触发/消费 | 幂等键 | |
|---|---|---|---|---|---|
| `voice.session.started` | external | `session_id, transport, style_id, started_at, client_ref?` | 热：载记忆+风格 → `session.configured` | `session_id` | M |
| `voice.session.configured` | harness | `session_id, bundle_ref, style_rev, voice_bindings_rev` | 消费：runner 拿到策略包 | `session_id + style_rev` | M |
| `voice.session.ended` | external | `session_id, reason(normal\|hangup\|error), duration_ms, turn_count, record_ref` | 冷：写会话摘要、更新卡片 | `session_id` | M |
| `voice.session.reconnected` | external | `session_id, at_ms, gap_ms` | 消费：判定是否重放/标 INCOMPLETE | `session_id + at_ms` | O |
| `voice.session.degraded` | harness | `session_id, reason, fallback_ref?` | 消费：投影/告警 | `session_id + reason` | O |
| `voice.segment.sealed` | external | `seg_id, session_id, role, modality, t_start_ms, t_end_ms, audio_ref, meta_ref, meta_digest` | **记录的事件权威**：目录项由它确定（[conversation-record.md](conversation-record.md) §6）；消费：完整性对账、冷路径索引 | `seg_id` | M |

### 4.2 用户输入（轮次）

| 事件 | 产生者 | 关键 payload | 触发/消费 | 幂等键 | |
|---|---|---|---|---|---|
| `voice.user.turn.final` | external | `session_id, turn_id, transcript, lang, modality(voice\|text), user_seg_id, audio_ref?, words_ref?, confidence?` | 热：本轮回复 | `session_id + turn_id` | M |
| `voice.user.barge_in` | external | `session_id, turn_id, reply_id, at_ms, user_seg_id, transcript_so_far?` | 消费：取消 TTS、记录截断 | `reply_id + at_ms` | M |
| `voice.user.turn.abandoned` | external | `turn_id, reason(no_speech\|too_short\|error)` | 消费：状态机回 LISTENING | `turn_id` | O |
| `voice.user.backchannel` | external | `turn_id, text, at_ms` | 消费：**不打断**，可选自然感回放 | `turn_id + at_ms` | O |

### 4.3 助手回复

| 事件 | 产生者 | 关键 payload | 触发/消费 | 幂等键 | |
|---|---|---|---|---|---|
| `voice.turn.completed` | external | `turn_id, reply_id, reply_ref, assistant_seg_ids[], tool_calls[], first_audio_ms, total_ms, interrupted, record_ref` | 冷：更新记忆/会话摘要 | `turn_id` | M |
| `voice.reply.condensed` | harness | `reply_id, from_ref, kept_ref, reason, budget` | 消费：投影/审计（无损依据） | `reply_id` | M |
| `voice.reply.started` | external | `reply_id, turn_id, style_rev, model, first_token_ms?` | 观测/投影 | `reply_id` | O |
| `voice.reply.interrupted` | external | `reply_id, at_ms, spoken_sentences, resume_ref?` | 消费：支持"继续" | `reply_id` | O |
| `voice.reply.resumed` | external | `reply_id, from_ref` | 消费：投影 | `reply_id + from_ref` | O |
| `voice.reply.degraded` | harness | `reply_id, reason(model_error\|budget\|policy)` | 消费：投影/告警 | `reply_id + reason` | O |
| `voice.utterance` | harness | `reply_id, text, style_id, prosody` | **仅 R2 方案**（工作面生成文本）才需要 | `reply_id` | O |

### 4.4 风格 / 人格 / 偏好（用户配置侧）

| 事件 | 产生者 | 关键 payload | 触发/消费 | 幂等键 | |
|---|---|---|---|---|---|
| `voice.style.set` | external | `style_id, spec_ref, base_rev, by` | 条件受理；**陈旧基线拒绝** | `style_id + rev` | M |
| `voice.style.proposed` | harness | `style_id, spec_ref, rationale_ref` | 消费：待用户接受 | `proposal_id` | O |
| `voice.persona.revised` | harness | `persona_ref, prev_ref, reason_ref` | 消费：投影；**不得放宽安全边界** | `persona_ref` | O |
| `voice.preference.set` | external | `key, value_ref, base_rev` | 消费：投影（称呼/语言/时区） | `key + rev` | O |

### 4.5 行动确认（有副作用的操作）

| 事件 | 产生者 | 关键 payload | 触发/消费 | 幂等键 | |
|---|---|---|---|---|---|
| `voice.action.confirm.requested` | harness | `action_id, summary, risk, expires_at?` | 消费：向用户确认 | `action_id` | O |
| `voice.action.confirmed` | external | `action_id, by` | 消费：放行执行 | `action_id` | O |
| `voice.action.rejected` | external | `action_id, reason?` | 消费：不执行 | `action_id` | O |

### 4.6 记忆维护（冷路径）

| 事件 | 产生者 | 关键 payload | 触发/消费 | 幂等键 | |
|---|---|---|---|---|---|
| `sys.memory.size` | runtime | `bytes, items, threshold, crossed` | 冷触发：organization | `observed_at` | M |
| `voice.memory.consolidated` | harness | `consolidation_id, from_refs[], to_ref, mode(lossless\|lossy), fold_digest` | 消费：投影；**有损必留指针** | `consolidation_id` | M |
| `voice.memory.recall.missed` | external | `query_ref, reason` | 观测：召回质量 | `query_ref` | O |

### 4.7 用户空间认知（冷路径）

| 事件 | 产生者 | 关键 payload | 触发/消费 | 幂等键 | |
|---|---|---|---|---|---|
| `sys.userspace.changed` | runtime | `ws_id, revision, source, observed_at` | 冷触发：刷新卡片 | `ws_id + revision` | M |
| `voice.userspace.card.updated` | harness | `ws_id, card_ref, observed_revision, prev_ref?` | 消费：投影（**带新鲜度**） | `ws_id + observed_revision` | M |
| `voice.userspace.access.denied` | external | `ws_id, op, reason` | 观测：**认知≠授权**留痕 | `ws_id + op + observed_at` | O |

### 4.8 时钟 / 空闲 / 承诺（见 [scheduling.md](scheduling.md)）

| 事件 | 产生者 | 关键 payload | 触发/消费 | 幂等键 | |
|---|---|---|---|---|---|
| `sys.clock` | runtime | `now, monotonic_ms, tz_offset_min, tick` | **时钟观测**：时钟推进即求值各工作触发条件（`should_start(now=)`） | `tick` | M |
| `sys.schedule.fired` | runtime | `schedule_id, occurrence, fired_at, lateness_ms, event_kind` | **日程到点**：runtime 按标准 crontab/一次性时刻 materialize 后触发；再求值开轮 | `schedule_id + occurrence` | O |
| `sys.idle` | runtime | `idle_since, idle_for_ms` | 冷触发：深整理 | `idle_since` | M |
| `voice.commitment.made` | harness | `commitment_id, what_ref, due_at?, tz?, cron?, source_turn_id?` | 投影未结承诺；**日程内容归助手**；runtime 据此 materialize | `commitment_id` | O |
| `voice.commitment.due` | harness | `commitment_id, due_at, fired_at, lateness_ms` | 到期后助手自行声明（其谓词/日程触发） | `commitment_id + due_at` | O |
| `voice.commitment.notified` | harness | `commitment_id, channel, at` | 消费：标记**已送达**；等用户回应 | `commitment_id + at` | O |
| `voice.commitment.acknowledged` | external | `commitment_id, by, at` | 消费：会话中接续（"那个提醒…"） | `commitment_id` | O |
| `voice.commitment.fulfilled` | external | `commitment_id, evidence_ref` | 消费：关闭 | `commitment_id` | O |
| `voice.commitment.cancelled` | external | `commitment_id, reason?` | 消费：关闭；日程随之撤销 | `commitment_id` | O |
| `voice.commitment.expired` | harness | `commitment_id, reason(no_response\|superseded)` | 消费：关闭 | `commitment_id` | O |

承诺**归助手自己定义**（用户 2026-09-17 裁决）：提醒不是"发完就完"——用户会追问、会改时间、会取消，
这些都得在对话里接得上；**日程内容也是助手自己的事情**（`due_at`/`cron` 是它的事实数据）。
**机制归 runtime**：接受标准 **crontab + 事件定义**、materialize 到其 bash 环境的调度工具、到点落事件
（`sys.schedule.fired`）；crontab 是**派生物**（权威在工作数据）、**只叫醒 runtime 不写事实**
——两条纪律见 [scheduling.md](scheduling.md) §4。谓词式时间（空闲/超时）用 `sys.clock`。

### 4.9 质量观测（P7）

| 事件 | 产生者 | 关键 payload | 用途 | |
|---|---|---|---|---|
| `sys.voice.latency` | runtime | `turn_id, asr_first_partial_ms, endpoint_ms, first_token_ms, first_audio_ms, total_ms` | 验证及时性（VO19） | M |
| `sys.voice.underrun` | runtime | `reply_id, count` | 播放质量 | O |
| `sys.voice.barge_in.count` | runtime | `session_id, count` | 打断频率 | O |
| `voice.adapter.error` | **harness** | `port, provider, code, window, count, first_at, last_at, retryable` | 降级/换模型决策 | O |

**`voice.adapter.error` 归 harness**（用户 2026-09-17 裁决）：runner 是本 harness 的代码，选哪个供应商、
要不要重试、降级到哪个适配器都是**harness 策略**，runtime 不该知道豆包/方舟。两条纪律：
① **按窗口聚合**（`window + count`），不为每个包/每次重试落一条，避免错误刷屏；
② **脱敏**——不得带密钥、Authorization、完整 URL；错误文本进面之前先做替换（对齐 glossary:100-102）。

### 4.10 工具执行与存活检查（[execution-timeouts.md](execution-timeouts.md)）

| 事件 | 产生者 | 关键 payload | 语义 | |
|---|---|---|---|---|
| `sys.tool.started` | runtime | `call_id, tool, target, started_at, budget_ms?` | 调用开始（输入边界固定，v5:149） | O |
| `sys.tool.check` | runtime | `call_id, check_seq, elapsed_ms, silent_for_ms, last_output_at?, budget_left_ms?` | **存活检查提醒**（默认间隔、退避）；**不代表要杀** | O |
| `sys.tool.finished` | runtime | `call_id, outcome(ok\|failed\|timeout\|unknown), exit, side_effects(none\|possible\|unknown), duration_ms` | 收束；`timeout` 是**策略判定** | O |
| `sys.tool.abandoned` | runtime | `call_id, reason(resource_limit\|lease\|shutdown), last_known_state` | 资源安全网：**结果未知**，不是失败也不是没执行 | O |

要点：默认是**发 check**（runtime 负责不让系统静默卡死），**怎么办由 harness 定**；
"超时"≠"工具没执行"；有副作用而无确认结果时落 `unknown` 并**先查询再决定**。
反例：runtime 为某个语音供应商定义错误码（把领域知识写进机制）；或每个失败包一条事实。

## 5. 最小闭环集合（先只做这些）

```
voice.session.started → voice.session.configured
voice.segment.sealed                                        （对话记录的事件权威，目录由它确定）
voice.user.turn.final → voice.turn.completed
voice.user.barge_in
voice.reply.condensed
voice.session.ended
voice.style.set
sys.memory.size / sys.idle / sys.userspace.changed        （冷路径三个触发）
sys.clock                                                   （时钟观测，定时场景共用）
voice.memory.consolidated / voice.userspace.card.updated  （冷路径两个产物）
sys.voice.latency                                          （可观测性）
```

其余（确认、承诺、偏好、投机、重连等）**按能力出现再加**——宁缺毋滥，不加没有消费者的事件。

## 6. 幂等与冲突（受理规则要点）

- 轮次类以 `session_id + turn_id` 去重；重复交付回到同一身份，**不产生第二次副作用**。
- `reply_id` 天然幂等键；`barge_in` 可能连续到达，用 `reply_id + at_ms` 区分而非"最新覆盖"。
- 配置类（`style.set`/`preference.set`）带 `base_rev` 条件受理，**陈旧基线拒绝**（landing §4.5）。
- 观测类（`sys.*`）以 `observed_at`/`revision` 去重；同一观测只触发一次冷路径。
- **冲突不静默覆盖**：同 `turn_id` 不同 transcript → 受理拒绝并留痕，不取"最后一次"。

## 7. 与框架原语的对应与缺口

- 用到：P1 声明、P2 受理（含 `base_rev`）、P3 触发、P4 投影、P5 逻辑、P6 身份、P7 观测、P8 保留名。
- 缺口（已登记）：**runtime 调度机制**（接受标准 **crontab + 事件定义**、materialize 到 bash 环境的调度工具、
  到点落 `sys.schedule.fired`；外加 `sys.clock` 供谓词式时间；见 [scheduling.md](scheduling.md)，
  与 monitoring 同题，一次实现多处复用）、`sys.idle`（空闲观测）、
  `sys.userspace.changed`（用户空间变更观测）、流式观测通道（分片+引用）、session-runner（谁发这些观测）、
  出站投递（`session.configured` 怎么送达 runner；提醒怎么送达用户）、
  **媒体 artifact 通用化**（对话记录的字节存储，见 [conversation-record.md](conversation-record.md) §6，仅存储策略）。

## 8. 未决

- **U10** `sys.userspace.changed` 的来源：外部事件源 / 会话边界抽查 / 空闲重扫（成本与新鲜度权衡）。
- ~~U11 `voice.adapter.error` 归 harness 还是 runtime~~ → **已裁决：harness（`voice.*`）**；runtime 侧设施错误仍走 `sys.*`。
- ~~U12 承诺/提醒是否交给独立 monitoring harness~~ → **已裁决：助手自己定义**（用户要能追问/改期/取消），
  只把**唤醒**委托给 runtime 的通用定时观测。
- **U13** 多会话并发下的 `session_id` 与 `reply_id` 命名空间（同一助手两个会话同时说话）。

## 11.5 conversation-record

# 对话记录：目录化的原始音频 + 元数据

状态：UNVERIFIED 设计稿。按用户 2026-09-17 要求：
① **必须有音频记录，也要有元数据**；② 非语音输入（文本/其他语言）**同样**进这套结构；
③ 双工音频要能**识别端点并切成音频片段**；④ 对话记录**目录形式**组织，目录下放原始内容 + 元数据，
并预留**语气/情绪/人物识别**等后续分析位。
相关：[events.md](events.md)、[assistant-work.md](assistant-work.md)、[latency-and-curation.md](latency-and-curation.md)、
[architecture.md](architecture.md)、[duplex.md](duplex.md)。

## 1. 组织原则（谁可写、什么不可变）

| 原则 | 内容 |
|---|---|
| **片段是单位** | 记录按 **会话 → 片段（segment）** 组织；一个片段 = 一次端点切分出的说话单元（用户一句 / 助手一句） |
| **权威在事件** | 片段的**身份、顺序、归属**由事件给出（`voice.segment.sealed` / `voice.user.turn.final` / `voice.turn.completed`）；事件是契约，目录不是 |
| **目录是物化** | 目录树是事件流的**物理组织**：路径 = 事件身份的确定性映射；`timeline.jsonl` / `manifest.json` 是事件流的**投影**，可重建、不构成第二权威 |
| **原始不可变** | `audio.*` 与采集时的元数据写一次；后续分析**不得改写**原始（对齐 v5:252 裁剪只改视图不删依据） |
| **分析可重算** | 情绪/语气/说话人分析带 `analyzer + version`，可从原始重算；与原始**物理分目录** |
| **文本与语音同构** | 无论输入是语音还是文本、无论什么语言，都产生同结构的片段；用 `modality` / `lang` 区分 |
| **双声道** | 麦克风（用户）与播放（助手）分别记录，另有可选"回声消除后"声道；重叠（barge-in）在时间轴上真实保留 |
| **元数据是 sidecar** | 每个片段一个 `meta.json`；会话一个 `session.json`。它是**事件 payload 的物化副本**（带 `meta_digest` 与事件对账），让数据集自包含、外部工具不必重放事件 |

## 2. 目录布局

```
<work>/session/records/<session-id>/          # 记录区（观测域；二进制不进 git）
├── session.json                 # 会话级元数据（见 §3.1）
├── timeline.jsonl               # 全局有序时间线：segment / 事件 → 引用（一行一条，append-only）
├── manifest.json                # 完整性清单：片段数、每个音频的 sha256/bytes/时长、record_schema_version
├── segments/
│   ├── seg-000001/
│   │   ├── audio.opus           # 原始音频（用户声道，mic；保留采集编码）
│   │   ├── audio.playback.opus  # （助手片段）原始 TTS 播放音频
│   │   ├── audio.aec.opus       # （可选）回声消除后的用户声道
│   │   ├── meta.json            # 采集时元数据（见 §3.2）
│   │   ├── text.txt             # 文本（ASR 结果 / 用户键入 / TTS 原文）
│   │   ├── words.jsonl          # （可选）词级时间戳
│   │   └── analysis/            # 派生分析（可重算；永不覆盖原始）
│   │       ├── emotion/1.json
│   │       ├── prosody/1.json
│   │       └── speaker/1.json
│   └── seg-000002/ …
└── artifacts.json               # 大对象外置时的 content-addressed 引用（sha256 → 位置）
```

**为什么放 `session/records/` 而不是 `surface/content/`**：原始音频是**观测原件**，不是模型写出来的记忆；
`content/` 是模型可写、进 git 的产物区，塞音频既胀 git 又混淆"记忆 vs 证据"。记忆摘要仍写
`content/conversations/<session-id>.md`，通过 `record_ref` 指回本目录（landing §4.4 情况 2：局部执行事实经引用进面）。

## 3. 元数据 schema（候选）

### 3.1 `session.json`（会话级）

```json
{
  "record_schema_version": 1,
  "session_id": "…", "work_id": "…",
  "started_at": "2026-09-17T10:00:00+08:00", "ended_at": "…", "duration_ms": 0,
  "transport": "webrtc|websocket|local",
  "codec_profile": {"mic": {"codec":"opus","sample_rate":48000,"channels":1},
                    "playback": {"codec":"opus","sample_rate":48000,"channels":1}},
  "participants": [{"participant_id":"u1","role":"user","display_name":null,"identity_ref":null},
                   {"participant_id":"a1","role":"assistant","display_name":"…"}],
  "bindings": {"asr":"doubao-seed-asr-2.0@ver","tts":"doubao-seed-tts-2.0@ver",
               "llm":"ark-glm-5.3-flash@ver","turn":"silero+smart-turn@ver"},
  "style_rev": "…", "policy_bundle_revs": ["…"],
  "segment_count": 0, "turn_count": 0,
  "privacy": {"retention_class":"default", "consent_ref": null}
}
```

### 3.2 `segments/<seg>/meta.json`（片段级）

```json
{
  "seg_id": "seg-000001", "session_id": "…", "seq": 1,
  "role": "user|assistant",
  "modality": "voice|text",              // 文本输入同样有片段（无音频文件时 audio=null）
  "turn_id": "t-0003", "reply_id": null, // 助手片段填 reply_id
  "t_start_ms": 12345, "t_end_ms": 15678, "duration_ms": 3333,   // 相对会话起点
  "wall_start": "2026-09-17T10:00:12.345+08:00",
  "lang": "zh-CN", "lang_confidence": 0.98,
  "audio": {"ref":"audio.opus","channel":"mic|playback|aec","codec":"opus",
            "sample_rate":48000,"channels":1,"bytes":0,"sha256":"…"},
  "content": {"text_ref":"text.txt","words_ref":"words.jsonl","source":"asr|typed|tts"},
  "endpoint": {"detector":"silero+smart-turn@ver",
               "reason":"speech_end|max_duration|barge_in|session_end","confidence":0.0},
  "interaction": {"interrupted": false, "interrupted_by": null, "overlap_with": []},
  "asr": {"provider":"doubao-seed-asr-2.0","model":"bigmodel","definite":true,"revisions":2,"confidence":null},
  "tts": {"provider":"doubao-seed-tts-2.0","voice":"…","style_rev":"…","model":"seed-tts-2.0"},
  "provenance": {"runner_version":"…","harness_digest":"sha256:…","policy_bundle_rev":"…"},
  "analysis_refs": []                     // 形如 "analysis/emotion/1.json"；派生、可重算
}
```

**字段要点**：`t_start_ms/t_end_ms` 是相对时间（便于拼接与对齐），`wall_start` 是绝对时间（便于与外部日志对齐）；
`lang` 是"对应的语言"；`analysis_refs` 是后续语气/情绪/人物识别的挂载点。

### 3.3 派生分析格式（统一外壳，便于任意分析器接入）

```json
// segments/seg-000001/analysis/emotion/1.json
{"analyzer":"emotion","version":1,"input_ref":"audio.opus","input_sha256":"…",
 "computed_at":"…","result":{"labels":[{"name":"neutral","score":0.8}],"segments":[]}}
```

规则：**输入必须有 `input_sha256`**（否则无法判断分析是否对应原始）；`version` 递增不覆盖旧版；
分析器换模型 = 新 version；原始音频或文本被删 → 分析标记失效（可重算或显式缺失）。

## 4. 双工端点切分：片段怎么来

| 片段 | 起 | 止 | 备注 |
|---|---|---|---|
| 用户片段 | VAD `speech_start` | 端点判定 `speech_end` + 尾窗 | 端点参数来自风格预设（[duplex.md](duplex.md) §3） |
| 用户片段（被打断） | `speech_start` | `barge_in` 时刻 | 记 `interaction.overlap_with` 指向被打断的助手片段 |
| 助手片段 | TTS 首个音频帧（或按句） | 播放完 / `barge_in` 截断 | 按句切便于字幕与"继续播" |
| backchannel | VAD 起 | 短促结束 | `role=user`，`modality=voice`，不构成 turn（[events.md](events.md) §4.2） |
| 静音/无语音 | — | — | **不产生片段**；会话级 `session.json` 保留总时长 |

边界要求：

- **重叠要保留**：barge-in 时用户片段与助手被截断片段在时间轴上真实重叠，不能只留"谁赢"。
- **切分可复算**：端点参数与检测器版本进 `endpoint.detector`；换检测器 → 重新切片是**新记录版本**，不就地改写。
- **文本输入的"片段"**：`modality="text"`，`audio=null`，`t_start_ms=t_end_ms=键入时刻`；结构与语音一致。
- **多语言**：逐片段 `lang`；ASR 支持的语言与 `enable_lid` 可在适配器配置（[providers.md](providers.md) §3.2）。

## 5. 与事件、记忆、隐私的关系

- **事件引用片段**：`voice.user.turn.final.audio_ref = "record://<session>/segments/seg-000001"`；
  `voice.user.barge_in`、`voice.reply.interrupted` 同样带 `seg_id`；`voice.segment.sealed`（O）用于记录完整性对账。
- **记忆是投影，不是副本**：`content/conversations/<session-id>.md` 存摘要 + `record_ref`，
  **不复制音频**；热路径投影只给摘要与指针（v5:250/252）。
- **完整性**：`manifest.json` 给出片段数 + 每个音频的 sha256/bytes；缺片段**显式报告**，不静默跳过
  （对齐 landing "观测区缺失显式"）。
- **隐私**：`retention_class` / `consent_ref` 进 `session.json`；语音是生物特征，默认保留策略与删除入口
  必须单独裁决（[assistant-work.md](assistant-work.md) U2、[validation-plan.md](validation-plan.md) Q-V5）。

## 6. 权威与物理组织：与事件模型不冲突

记录**同时是事件、也是目录**，两者分工不同层：

| 层 | 是什么 | 谁定 |
|---|---|---|
| **语义/契约** | 有哪些片段、身份、顺序、归属、时延 | **事件**（`voice.segment.sealed`、`turn.final`、`turn.completed`） |
| **物理组织** | 字节放哪、怎么分目录、文件叫什么 | **目录约定**（`seg_id` → 路径的确定性映射） |

推论：

- **目录不是第二权威**：`timeline.jsonl` / `manifest.json` 是事件流的投影，可从事件 + 扫描重建；
  `meta.json` 是事件 payload 的物化副本，靠 `meta_digest` 与事件对账。
- **路径是身份的确定性函数**：给定事件里的 `session_id`/`seg_id` 就能算出路径，不需要额外索引；
  换布局（本地目录 → 对象存储/分区）只换**约定版本**（`record_schema_version`），不动事件契约。
- **字节不能从事件重算**，所以音频是**原始料**而非 `derived/` 缓存；它的保留/迁移是**存储策略**问题
  （`retention_class`、可选的媒体 artifact 引用），**不是**"事件 vs 目录"的取舍。
- 用户 2026-09-17 裁决："也是事件；数据组织为目录**暂时**最好，不冲突"——"暂时"落在这里：
  目录是当前最合适的物化方式，可替换，契约不变。

【撤回上一稿的判断】上一稿把这件事写成"观测域可省 vs 升为可移植记录"的二选一，是假分叉：可移植性属于
存储/保留策略，与"记录由事件表达"无关。以下替换原 A/B 裁决项。

## 7. 未决

- **U14** 目录布局版本与迁移：`record_schema_version` 升级时旧记录是就地保留、还是并行新布局（对齐 landing §10 布局版本）。
- **U15** 编码选择：原始 opus（省空间、有损）vs 同时留 pcm（可重算分析，占空间）；分析用哪一路。
- **U16** 助手播放音频的采集方式：TTS 输出 tee（干净）vs 扬声器回采（真实但含环境）；是否两只都留。
- **U17** 切片策略：按端点一句（实时）vs 按更长时间窗批处理；两者是否都需要（实时用 + 归档用）。
- **U18** 人物识别（说话人分离）的多方场景：`participants` 与 `speaker` 的对应、未注册说话人的处理。
- **U19** 分析结果的保留与失效：分析器升级后旧 version 是否保留、失效如何标记。
- **U20** 记录的存储策略：留在 `session/records/` 按 `retention_class` 管理，还是引用媒体 artifact（sha256+manifest）；
  这只影响**字节怎么存/怎么迁**，不影响事件契约（§6）。

## 11.6 scheduling

# 定时与日程：runtime 提供调度机制（复用 cron），日程归助手

状态：UNVERIFIED 设计稿（第 3 稿，含对上一稿"不许用 cron"的修正）。
用户 2026-09-17 裁决：**runtime 可以接受 crontab 以及事件定义；不需要自定义、不需要重新实现，
自己的 bash 环境装上工具就行；日程是助手自己的事情。**
相关：[events.md](events.md) §4.8–4.9、[assistant-work.md](assistant-work.md)、
[latency-and-curation.md](latency-and-curation.md)、[../harness-catalog/monitoring.md](../harness-catalog/monitoring.md)。

## 1. 结论

1. **分工**：**日程内容归助手**（提醒谁、提醒什么、什么时候、逾期怎么办——都是它的数据）；
   **按时的机制归 runtime**（把到点变成事件）。
2. **复用成熟工具，不重新实现**：runtime 的 bash 环境里可以装调度工具（cron/launchd/systemd timer/
   一个随环境安装的调度器）；runtime **接受标准 crontab 表达式 + 事件定义**，到点落事件。
   **不发明自定义定时语法**——用标准 crontab 就够。
3. **两条纪律让"用 cron"不破坏框架不变量**（§4）：
   - **权威在工作数据，crontab 是派生物**：日程存工作目录；条目在启动/导入时按数据重新生成，
     换宿主只需重新 materialize（与对话记录"权威在事件、目录是物化"同一模式）。
   - **cron 只叫醒 runtime，不写事实**：条目调用 runtime 自己的入口，事实仍由 runtime 单写者落。
4. **`sys.clock` 仍然要有**：谓词式时间（"空闲 10 分钟""过期未发补齐"）读时钟观测；
   显式日程（"每天 9 点"）走 crontab+事件定义。两者并存，不互相替代。
5. **仍然不行的做法**（§5）：轮内起 `sleep` 后台进程、放开任意 bash、工作直接写宿主 crontab。
6. **`voice.adapter.error` 归 harness**（用户裁决），窗口聚合 + 脱敏。
7. **承诺归助手**（用户裁决）：`voice.commitment.*`；提醒不是"发完就完"，用户会追问/改期/取消。

## 2. 分工

| | 归谁 | 内容 |
|---|---|---|
| **策略/数据** | 助手 harness | 有哪些日程、什么时刻、提醒什么、到期怎么处理、逾期怎么补、取消/改期 |
| **机制** | runtime | 接受标准日程定义 + 事件定义；materialize 到宿主调度工具；到点落事件；迟到补齐；跨宿主重生成 |

runtime **不认识"承诺""提醒""截止"**：它只认识"某时刻发某个已声明的事件"。

## 3. runtime 的调度机制（复用，不自造）

- **输入形态**：标准 **crontab 表达式**（周期）与**一次性时刻**（`at` 风格）；每条附一个
  **事件定义**（已声明 kind + payload）。这是标准语法，不是我们发明的 DSL。
- **执行形态**：调度后端到点调用 **runtime 自己的入口**（如 `lore clock fire <work> <schedule-id>`），
  入口经 Fact Admission 落事件（如 `sys.schedule.fired{schedule_id, occurrence, at, lateness_ms}`），
  再求值触发条件开轮。
- **落事件**：见上；事实仍由 runtime 单写者落。
- **平台**：目标是 Unix（macOS/Linux）。cron / launchd / systemd timer 语义不同 →
  调度后端是**可替换的一个薄适配**（与语音端口同一套路），runtime 只依赖"到点回调"这一件事。
- **粒度**：crontab 分钟级；提醒/监视够用；不承诺毫秒精度（v5:349 不冻结 SLA）。

### 3.1 选型（U21 已定）

**默认：调度跑在 runtime 自己的常驻循环里，crontab 语义用成熟库解析（如 Python `croniter`），
不引入宿主 cron 守护进程。**

| 选项 | 判断 |
|---|---|
| **runtime 内建循环 + 成熟解析库**（选它） | runtime/事件服务本来就常驻（v5:90 允许共享设施常驻）；到点就是"睡到下一个时刻再落事件"；**跨 macOS/Linux 语义一致**；没有第二个守护进程、没有 materialize 同步 |
| 宿主 cron | Linux 常见，但 macOS 语义/可靠性不一致，环境最小化，跨平台要分叉 |
| 宿主 launchd / systemd timer | 各自平台原生，但两套实现、两套测试 |
| supercronic 等随环境装的调度器 | 仍要多一个二进制与它自己的 crontab 管理，收益不抵复杂度 |

**不强制的备选**：若某些部署里 runtime **不常驻**（按需启动），才需要宿主调度器**唤醒**它；
此时才做 materialize，并仍守 §4 两条纪律（权威在数据、只叫醒不写事实）。这一层做成后端端口，默认关。

**依赖代价**：引入一个纯 Python 的 crontab 解析库（如 `croniter`，Airflow/RQ 同款）。
若项目不接受新依赖，退化方案是**显式受限子集**（一次性时刻 + 每日/每周 HH:MM + 固定间隔），
并在文档与拒绝信息里说清"不支持完整 crontab"——**不允许静默算错**。

## 4. 两条纪律（这是关键，不是"能不能用 cron"）

### 4.1 权威在工作数据，crontab 是派生物

- 日程是**助手的数据**（如 `content/schedules.json`，或由 `voice.commitment.*` 事实派生的视图），
  随工作目录走；
- 若使用宿主调度后端，条目是 runtime 在**启动/导入/日程变更时重新生成**的派生物，**不是权威**；
  使用默认（runtime 内建循环）时根本不产生宿主条目，纪律自动满足；
- 换宿主：目录拷过去 → runtime 重新装载/生成 → 日程继续生效；
- 这条把上一稿"cron 不可移植"的反对**消掉了**：不可移植的是**宿主条目**，不是日程。

### 4.2 cron 只"叫醒"，不写事实

- 条目只调用 runtime 入口；**事实流仍只有 runtime 一个写者**（landing §6）；
- 于是"bash 到点自己 append facts"的单写者问题也不存在了；
- 工作/模型**不能**直接写宿主 crontab；写 crontab 的是 runtime，日程数据来自助手的受控入口。

> **修正记录**：上一稿写"禁止 cron/launchd/at"，理由是单写者、零驻留、可移植、审计四条。
> 其中**单写者**与**可移植**由上面两条纪律解决；**零驻留**本就不受影响（cron 是共享守护进程或
> 随环境安装的调度器，不是每工作进程）；**审计**由"日程存工作目录 + runtime 记录 materialize/fire"解决。
> 因此"用 crontab"是**可以接受**的——问题不在工具，在有没有这两条纪律。仍被禁止的见 §5。

## 5. 仍然不行的做法

| 形态 | 为什么仍不行 |
|---|---|
| 轮内 `nohup sh -c 'sleep 86400; …' &` | 工作专属常驻进程（v5:90）；Round 结束该回收的没收；重启后重复/丢失不可判定 |
| 放开 runtime 执行工作/模型给的**任意 bash** | 安全与授权边界（v5:190 同源）；调度的输入应是**数据 + 事件定义**，不是脚本 |
| 工作/模型**直接写宿主 crontab** | 越过 runtime 的单写者与授权；日程必须经 runtime materialize |
| 自定义定时 DSL / `due_field` 契约字段 / 日程表另立权威 | 不必要的发明（用户明确不要） |

## 6. 迟到、漏触发与时区

- **迟到/漏触发**：runtime 启动或换宿主后，对"已过点但未触发"的日程**立即补发并记 `lateness_ms`**；
  已触发过的不重复（按 `schedule_id + occurrence` 幂等）——**不静默丢，也不当没发生**。
- **时区**：日程存 UTC + 用户 `tz`；"明天九点"按用户时区解析；宿主时区变化不改已存日程语义。
- **改期/取消**：追加事实（`cancelled` + 新 `made`，或带 `supersedes`），不原地改写；runtime 据此重生成条目。

## 7. 与 `sys.clock`、与 monitoring 的关系

- **显式日程**（"每天 9 点""明天 15:00 提醒"）→ crontab + 事件定义。
- **谓词式时间**（"空闲十分钟""超过 24 小时未回应"）→ `sys.clock` 观测 + harness 自己的谓词
  （`rounds.should_start(now=)` 已有该入口）。
- 两者都只是"时间怎么变成事件"的形态，runtime 都不认识业务含义。
- monitoring 的条件监视、plan 的截止、ask-user 的超时、助手的提醒**共用**这套机制（一次实现，多处复用）。

## 8. 预登记用例（接 [validation-plan.md](validation-plan.md)）

| ID | 判据 | 相关反例 |
|---|---|---|
| VO29 | **日程到点触发恰一次**：crontab/一次性日程到点落事件并开轮；取消后不再触发 | 到点不发；重复发；取消无效 |
| VO30 | **零驻留**：两次触发之间无工作专属常驻进程/长连接；调度工具是共享设施 | 轮内 `sleep` 常驻；每工作一个调度器进程 |
| VO31 | **权威在数据、crontab 是派生物**：日程存工作目录；换宿主后重新 materialize 并继续生效；旧宿主条目无需迁移 | 日程只存在宿主 crontab 里；换宿主丢失 |
| VO32 | **延迟补齐与时区**：过期未发**带 `lateness_ms` 补发**、已发不重发；用户时区解析正确；改期=追加事实 | 静默丢过期日程；按宿主时区算错；原地覆盖 |
| VO33 | **送达≠到点**：无活跃会话时未送达不得落 `notified`；重试有上限并最终 `expired` 留痕 | 把"到点"当"已提醒" |
| VO34 | **错误归属与聚合**：供应商错误落 `voice.adapter.error`（harness）且窗口聚合、脱敏；runtime 设施错误落 `sys.*` | 每包一条；错误里带密钥/URL |
| VO35 | **标准语法、无自定义**：新增一个需要定时的 harness 只用标准 crontab/一次性时刻 + 已声明事件定义，runtime 产品代码零改动 | 必须给 runtime 加自定义字段/DSL 才能定时 |
| VO36 | **cron 不写事实**：调度条目只调用 runtime 入口；工作/模型无法直接改宿主 crontab；事实流写者唯一 | 条目直接 append facts；工作写 crontab |

## 9. 未决

- ~~U21 调度后端选型~~ → **已定（§3.1）**：runtime 内建循环 + 成熟 crontab 解析库；
  宿主调度器只作为"runtime 不常驻"时的可选唤醒后端。
- **U22** 宿主后端（若启用）的 materialize 粒度：日程一改就重写整份条目，还是增量；与并发/多工作的关系。
- **U23** 送达渠道与重试上限（属对外投递缺口，需单独设计）。
- **U24** 无时间承诺的触发（如"下次用户上线时提醒"= 需要"用户上线"这一观测，而不是时间）。
- **U25** `sys.clock` 的推进节奏与落库粒度（每 tick 一条 vs 只在需要时求值）。
- **U26** 若项目不接受新依赖，受限子集的边界（见 §3.1）与其拒绝信息的口径。

## 11.7 execution-timeouts

# 执行超时与存活检查：默认是"到点发 check 事件"，不是"到点杀"

状态：UNVERIFIED 设计稿（第 2 稿，按用户 2026-09-17 修正）。
用户修正："可以是一个**提醒 check 的事件**发出来，默认有个时间；runtime 负责**避免死掉**的情况；
但不是超时工具就不执行之类的。"——即默认不是硬杀，而是**可观测 + 由 harness 决策**；
杀只是最后的资源安全网。
相关：[scheduling.md](scheduling.md)（业务时钟）、[events.md](events.md)、[architecture.md](architecture.md)。

## 1. 结论（修正上一稿）

1. **默认语义：到点发 `sys.tool.check` 事件**（runtime 观测，默认间隔 `check_interval`），
   让等待方知道"这个调用还在跑、多久没动静了"——**runtime 负责不让系统静默卡死**。
2. **怎么办归 harness**（策略）：继续等 / 追加预算 / 主动取消 / 降级 / 标记未知。
   **超时是 harness 的策略判定，不是一个自动的机制动作。**
3. **超时 ≠ 工具没执行，也 ≠ 失败**：调用**已经执行过**。结果只有四类：
   `ok` / `failed` / `timeout`（策略判定）/ `unknown`（无确认结果）。不得把"没结果"写成"没执行"。
4. **资源安全网仍然必须有**（runtime 职责）：硬上限 + 并发/资源上限；到限时
   **回收资源并落 `unknown`/`abandoned`**，明确"结果未知"，不冒充成功或失败。
5. **harness 声明默认与上限**：按工具类别给默认 `check_interval` 与预算，schema 可见、可调低、不得越上限。
6. **不做逐次"请设置超时"提醒**：默认即兜底；长/危险类可在**执行前**要求显式预算（guard），
   而不是在对话里唠叨。
7. **in-band `timeout` 是纵深防御**，不是权威（§7）。

## 2. 为什么默认不杀

- **合法长工作会被误杀**：安装、构建、大文件处理动辄几分钟；30 s 硬杀是错的默认。
- **"无响应"不等于"该放弃"**：连接卡住、远端慢，先要**看见**，再决定。
- **杀会把"未知"伪装成"结束"**：一旦杀掉，副作用可能已发生但结果未确认——
  这是 v5:332/336 与 X 合同明确禁止的（"不确定不重跑"）。
- 所以：**观测优先（check）→ 策略判定（harness）→ 资源安全网（runtime）**。

## 3. 事件

| 事件 | 产生者 | 关键 payload | 语义 |
|---|---|---|---|
| `sys.tool.started` | runtime | `call_id, tool, target, started_at, budget_ms?` | 调用开始（输入边界固定，对齐 v5:149） |
| `sys.tool.check` | runtime | `call_id, check_seq, elapsed_ms, silent_for_ms, last_output_at?, budget_left_ms?` | **存活检查提醒**：默认间隔发出；**不代表要杀** |
| `sys.tool.finished` | runtime | `call_id, outcome(ok\|failed\|timeout\|unknown), exit, side_effects(none\|possible\|unknown), duration_ms` | 调用收束；`timeout` 是**策略判定**的结果 |
| `sys.tool.abandoned` | runtime | `call_id, reason(resource_limit\|lease\|shutdown), last_known_state` | 资源安全网触发：**结果未知**，不是失败也不是没执行 |

- `check` 的**间隔退避**（如默认 10 s → 30 s → 60 s），避免长工作刷爆事实流；
  同一调用同一 `check_seq` 幂等。
- `timeout` 与 `unknown` 的区分很重要：前者是"我们决定不等了"，后者是"我们不知道结果"。
  有副作用的调用即使判定 `timeout`，也要带上 `side_effects: possible|unknown`，恢复时**先查询**。

## 4. 分工

| 谁 | 负责 |
|---|---|
| **runtime** | 执行；存活观测（`check`）；资源安全网（上限/回收 → `abandoned/unknown`）；**绝不**把"无结果"写成"失败/没执行" |
| **harness** | 默认 `check_interval` 与各类预算（写进 conventions/manifest、schema 可见）；收到 `check` 后的策略（继续/追问/取消/降级）；判定何时算 `timeout` |

**收到 `check` 的典型策略**（harness 逻辑，可配）：

- 正常：更新投影里的"进行中"状态，继续等；
- 超过软预算：给用户/上游一句进度（语音场景尤其自然："这个还在跑，稍等"）；
- 超过硬预算或长时间零输出：主动 `cancel`（这时才终止进程组），或降级到替代方案；
- 有副作用且无确认：标 `unknown`，把"先查询再决定"写进后续步骤。

## 5. 与"工具调前提醒设置超时"

- **默认兜底**：不给预算也有默认 `check_interval`，不会静默卡死；
- **schema 可见**：`budget_ms` 有默认值且出现在工具定义里，模型需要时能调；
- **长/危险类显式**：安装/出网/有副作用的工具，harness 的 `guard` **执行前要求**显式预算——
  这是可测的拒绝规则，不是聊天里的提醒。

反例：每次调用都提示"请设置超时"；或只在 prompt 里写"记得设超时"。

## 6. 资源安全网（runtime 职责，"避免死掉"）

"runtime 负责避免死掉"落成三条：

1. **硬上限**（每调用/每 Round/每工作）：超过即回收资源；
2. **并发与总量上限**：防止大量挂起调用耗尽资源；
3. **回收即未知**：回收一个没有确认结果的调用 → `sys.tool.abandoned{reason:resource_limit}` +
   `side_effects: possible|unknown`，恢复路径**先查询**，不重跑冒充接续（v5:332/336、X 合同）。

租约到期属于第 1 条的实现手段之一，但**租约到期不是 stopped proof**（X 合同明文），
必须转成 `abandoned/unknown` 而不是"失败"。

## 7. in-band `timeout` 的价值与局限（不变）

| 它能做什么 | 它不能做什么 |
|---|---|
| 让命令自己早退，给出干净退出码（124） | **忘写就没有**；默认值才可靠 |
| 缩短"到达策略判定"的窗口 | **连接层无响应**时根本没机会执行——只有 runtime 的 `check`/安全网能兜 |
| 对已知长命令做局部收紧 | 只杀**直接子进程**；需 `--kill-after` + 进程组 |
| 在脚本里表达意图 | 命令可 `trap` 信号 |

结论：可以做成 harness 生成脚本时的**默认包装**（可关），但**不是权威**。

## 8. 预登记用例（接 [validation-plan.md](validation-plan.md)）

| ID | 判据 | 相关反例 |
|---|---|---|
| VO37 | **默认可观测**：长调用按默认间隔发 `sys.tool.check`；两次 check 之间系统不静默卡死 | 无任何观测，永久挂起无迹 |
| VO38 | **到点不自动杀**：到达默认/软预算时**不杀**，harness 可选择继续；只有 harness 判定或资源上限才终止 | 30 s 无条件杀，误杀长工作 |
| VO39 | **结果四分类**：`ok/failed/timeout/unknown` 可区分；`timeout` 不写成"没执行"；有副作用带 `side_effects` | 把无结果记成失败或"未执行" |
| VO40 | **资源安全网**：超过硬上限/并发上限时回收资源并落 `abandoned/unknown`；恢复先查询不重跑 | 回收后当失败重试，产生第二次副作用 |
| VO41 | **默认与上限**：harness 默认按类别生效；显式值不得越 runtime 上限，越界被拒且留痕 | 模型设无限预算绕过 |
| VO42 | **in-band 是纵深**：命令级 `timeout` 存在时仍由 runtime 兜底；连接层无响应由 `check`/安全网处理 | 依赖脚本里的 `timeout` 作为唯一保障 |

## 9. 未决

- **U26** 默认 `check_interval` 与退避曲线的数值（先测量再定，v5:349）。
- **U27** 硬上限/并发上限的归属与配置位置（X budget maxima vs work.json policy）。
- **U28** `sys.tool.*` 的正式字段与是否与既有 `sys.tool.result` 合并（进组件合同定 schema）。
- **U29** 命令级 `timeout` 包装是否设为 harness 生成脚本的默认（可关）。
- **U30** `check` 落库粒度：面事实 vs 观测域（长工作少，倾向面事实；但需测量频率）。

## 10. 与现有实现的关系（差异在案）

**现状与本节设计冲突，已登记为待实施修订**：

- 现状：`lore_work/round.py` 的 `_run_shell` 用 `subprocess.run(..., timeout=tool_timeout)`，
  默认 **30 s 硬杀**，超时塌缩成 `sys.tool.result{exit:124}`；无存活观测、不保证整进程组终止。
- 目标：本节 §1–§6（check 先行、不自动杀、四分类结果、资源安全网）。
- 记录：[../amendment-task-tool-liveness-2026-09-17.md](../amendment-task-tool-liveness-2026-09-17.md)
  （含源码位置、工作副本哈希、影响面、实施顺序与门槛）；
  同时登记在 [../work-runtime-contract.md](../work-runtime-contract.md) 的"M1 已知缺口"。
- **未实施前不得声称行为已改**；改后须独立复跑既有 `validation/work_runtime/` 套件 + VO37–VO42。

## 11.8 latency-and-curation

# 及时响应与知识维护：两个工作重心，一个 work

状态：UNVERIFIED 设计稿。回答用户 2026-09-17 的问题：
**助手既要"马上答"，又要维护对用户用户空间的认知，该怎么安排？空闲做还是怎么做？**
前提（用户已裁决）：上下文**都是同一个助手 work 的上下文**，只是**工作重心不同**。
相关：[assistant-work.md](assistant-work.md)、[architecture.md](architecture.md)、
[style-profiles.md](style-profiles.md)、[providers.md](providers.md)、[validation-plan.md](validation-plan.md)。

## 1. 结论先行

**不拆 work，拆"策略实例"。** 同一个助手 work 里声明两套 `projection/rounds/logic` 实例
（框架已支持多实例角色，landing §4.5 R4）：

| | **会话循环（热）** | **维护循环（冷）** |
|---|---|---|
| 触发 | `voice.user.turn.final`（以及 `session.started`） | `session.ended` / 用户空间变更 / 阈值 / 空闲 |
| 目标 | 首个音频尽早 | 认知新鲜、记忆不腐、索引可用 |
| 延迟预算 | 首音频 ≈1.5–2.5 s（实测下限） | 秒级到分钟级都行 |
| 看什么 | **有界投影**：当前轮 + 生效风格 + 少量记忆/用户空间要点 + 指针 | 全量清单/变更集/日志（只在冷路径展开） |
| 模型档 | 快档（`reasoning_effort:minimal`，或换非推理模型） | 慢档（推理模型可以慢慢想） |
| 写什么 | 只写"轮次级事实"；**回复前不写** | 重写 `content/`（记忆、用户空间认知）+ 重建 `derived/` 索引 |

一句话：**热路径只读已备好的知识、绝不现查；冷路径负责把知识备好。**

## 2. 及时响应：把延迟拆开看，逐段砍

实测数字（[providers.md](providers.md)，单机少量样本，非基线）：

| 段 | 观测 | 能怎么砍 |
|---|---|---|
| ASR 部分结果 | 200 ms 分片即出 | — |
| 端点判定（"说完了吗"） | 静音窗口决定（默认 0.3–0.8 s） | 短句/明确指令用更短窗口；靠语义端点而非纯静音 |
| **上下文装配** | 未测，但必须 **<50 ms 且本地** | **预热**：`session.started` 时就把 session bundle 组好；热路径只做选择，不做发现 |
| LLM 首 token | `minimal` ≈0.9–1.3 s；默认 ≈4.3–5.5 s | 热路径用 `minimal`／换快模型；**把重推理赶去冷路径** |
| TTS 首音频 | ≈0.35 s（单向）／官方称双向 ≈0.3 s | 用双向流式；边生成边合成 |

六个具体手段：

1. **预热（warm-up）**：`session.started` 轮把"这一场大概要什么"备好（最近记忆要点、常用用户空间卡片）。
2. **并行预取（prefetch）**：用户还在说时，用 ASR partial 的关键词预取候选片段（有界），说完即可用。
3. **投机生成（speculative）**：对短回合可先猜着生成、用户继续说就丢弃——Pipecat `EagerUserTurnStrategies` /
   LiveKit `PreemptiveGeneration` 已有成熟实现，**别自己造**。丢弃的投机结果不算已确认输出。
4. **有界投影**：热路径**看不到全文**（v5:250/252），只看到要点 + 指针；细节用工具按需取。
5. **懒工具**：用户空间只给"卡片 + 指针"，不灌文件树；要看再读。
6. **写不阻塞说**：记忆落盘、索引更新一律放轮后/冷路径；**先出声，再记账**。

> 反例：热路径上"先扫一遍用户空间再回答"、把整份记忆塞进上下文、用推理档模型答寒暄——
> 这三件事本身就把延迟吃光了。

## 3. 维护什么：先有"用户空间认知"，才答得上"我有哪些用户空间、都干嘛的"

用户问题需要一张**随时可读的认知地图**。它放助手自己的 `content/`（是**记忆**，不是外部 Userspace 本体）：

```
surface/content/userspaces/
├── index.md            # 清单：id · 一句话用途 · 指针 · 最近观测 revision · 可访问性
└── <ws-id>.md          # 卡片：用途 / 结构 / 入口 / 常用命令 / 注意事项 / 何时看过哪个版本
```

要点：

- **认知 ≠ 授权**：`index.md` 说"这是干嘛的"不需要访问权；**读它的文件要 `work.json.userspaces`/grants**。
  答"有哪些用户空间、都干嘛的"用认知；答"这个函数在哪"必须走授权 + 工具。
- **新鲜度显式**：每张卡片带 `observed_revision`（如 git HEAD / 目录摘要）。热路径拿认知时做一次**廉价陈旧检查**；
  过期就**明说"可能已过期"**并触发一次有界刷新或把刷新排进冷路径——**绝不假装是新的**。
- **冷路径写、热路径读**：卡片由维护循环更新（见 §4），会话循环只引用其版本（landing §4.4 E5）。

同样要维护的还有：**记忆本体**（`memory/`：会话摘要 → 主题要点，去重合并）、**召回索引**（`derived/`，可删重建）、
**风格/人格提案**（模型提案、用户接受，见 [assistant-work.md](assistant-work.md) §7）。

## 4. 什么时候维护：四类触发，空闲只是其中一类

| 触发 | 触发源 | 做什么 | 为什么放这里 |
|---|---|---|---|
| **会话边界** | `voice.session.ended` | 写本次会话摘要、更新相关卡片/记忆 | 便宜、一定有、天然在"说完之后" |
| **变更事件** | `userspace.changed`（外部观测） | 标记卡片 stale，排队刷新 | 有事才做，不空转 |
| **阈值** | `sys.memory.size` / `sys.context.threshold.crossed` | 折叠/压缩/去重（organization 策略） | 对齐 archive 示例，**只缩视图不删依据**（v5:252） |
| **空闲** | `sys.idle`（一段时间无会话） | 深整理：重扫用户空间、重建索引、合并重复记忆 | 便宜时做重活；**空闲不常驻进程** |

**空闲到底怎么做**（回答"是空闲时呢还是怎么做"）：

- 空闲是**补充**，不是唯一：会话边界 + 变更事件已经覆盖大部分；空闲用来做"重但不急"的整理。
- **空闲 = 等一个定时/空闲观测事实，不是起一个常驻循环**（v5:90）：等待期工作专属进程归零，
  `rounds.should_start(now=...)` 拿时间判断即可。
- 需要一个**通用的定时/空闲观测原语**（`sys.clock` / `sys.idle`）——这与 monitoring 示例登记的是同一个缺口
  （[../harness-catalog/monitoring.md](../harness-catalog/monitoring.md)"定时/时钟观测与等待责任"）。
- 空闲整理必须**可中断、可重入、有界**：用户随时可能开口，冷路径不能占着资源挡热路径；
  做不完就提交已完成部分（每轮一个 revision），下次接着做。

## 5. 两个循环怎么在同一个 harness 里表达

```json
// harness/manifest.json 片段（候选，示意多实例角色 + 触发分流）
"facts": { "triggers": [
  { "id": "conversation", "on": ["voice.user.turn.final", "voice.session.started"] },
  { "id": "curation",     "on": ["voice.session.ended", "userspace.changed",
                                "sys.memory.size", "sys.idle"] } ] },
"roles": {
  "rounds":     [ {"id":"conversation","ref":"rounds/conversation.py"},
                  {"id":"curation",    "ref":"rounds/curation.py"} ],
  "projection": [ {"id":"conversation","ref":"projection/conversation.py"},
                  {"id":"curation",    "ref":"projection/curation.py"} ],
  "logic":      [ {"id":"conversation","ref":"logic/conversation.py"},
                  {"id":"curation",    "ref":"logic/curation.py"} ],
  "organization": [ {"id":"memory","ref":"organization/memory.py"} ]
}
```

- **同一 work、同一 `content/`、同一事实流**；差别只在"哪套策略被哪个触发调用"——正是"上下文是 work 的、
  工作重心不同"的落法。
- 冷路径改 `content/` 走 organization 策略（landing：组织策略改写 content 本体，产物是记忆本身、不进 `derived/`）；
  索引等可重建物放 `derived/`。
- 冷路径**不碰**热路径正在用的 session bundle；新版本下一轮/下个会话生效（v5:204 同理）。

## 6. 一致性边界（必须诚实的地方）

- 热路径读到的是**上一次冷路径整理的结果**，存在**陈旧窗口**。设计上要：① 窗口有上界（可配）；
  ② 过期**显式**（回答里带"截至 X"或"可能已过期"）；③ 关键问题可**同步做一次有界刷新**（一次工具/一次扫描），
  但要有超时与降级。
- 冷路径失败/被中断：不产生半成品事实；已提交的 revision 保留，未完成的下次继续。
- 不做"热路径顺手把大整理做了"——那是延迟杀手，也是"工作重心混淆"。

## 7. 预登记用例（新增，接 [validation-plan.md](validation-plan.md)）

| ID | 判据 | 相关反例 |
|---|---|---|
| VO19 | **热路径装配本地且有界**：`turn.final` → 发起模型调用之间无第二次模型调用、无全量用户空间扫描；装配耗时与上下文字节有上界 | 回答前先扫 repo；把整份记忆灌进上下文 |
| VO20 | **冷路径不侵入热路径**：维护轮运行中用户开口，首音频延迟不劣于无维护轮基线的给定比例；维护可中断且状态一致 | 维护占满 CPU/锁，用户等整理完 |
| VO21 | **陈旧显式**：卡片 `observed_revision` 落后时，回答标明可能过期或先做有界刷新；不得把旧认知当新事实 | 静默用旧卡片；或每次回答都全量重扫 |
| VO22 | **认知 ≠ 授权**：无 grant 时可描述用户空间用途，读取其内容被拒且留痕 | 用"知道路径"绕过授权 |
| VO23 | **空闲零驻留 + 触发正确**：空闲整理由 `sys.idle`/定时观测触发，等待期无工作专属常驻进程；同一观测只触发一次 | 常驻 while 轮询；空闲事件重复触发副作用 |

## 8. 未决

- **U6** 陈旧窗口上界与"同步有界刷新"的时机/超时（需 VO19/VO21 测量后定）。
- **U7** 冷路径模型档与预算（维护轮用推理档是否划算；是否与热路径分开计费/配额）。
- **U8** `userspace.changed` 的观测来源：外部事件源 vs 会话边界抽查 vs 空闲重扫——先用哪种，成本多少。
- **U9** 投机生成（speculative）在"助手"语义下的边界：丢弃的投机是否留痕、是否算一次模型开销。

## 11.9 duplex

# 语音助手：全双工会话设计

状态：UNVERIFIED 设计稿。框架选型待定向调研与独立用例后裁决（[research-notes.md](research-notes.md)）。
相关：[architecture.md](architecture.md)、[style-profiles.md](style-profiles.md)、[validation-plan.md](validation-plan.md)。

## 1. 真实性问题（为什么不能只做"按一下说一句"）

半双工（walkie-talkie）在真实对话里会立刻露馅：

- 用户想在助手说话时插一句"不是这个，是上一个"——半双工要么听不见，要么把助手的话当噪声；
- 用户说到一半停顿思考——固定静音阈值要么抢话，要么等太久；
- 助手说了一长段，用户已经知道答案——不能打断就只能等它念完。

全双工 = **边听边说 + 可打断 + 语义端点判定**。这三件事都有成熟开源实现，本设计只做"接缝与抽象"，
不自研音频算法。

## 2. 会话状态机（会话层持有，工作面只收事件）

```
        ┌──────────────────────────── reconnect ────────────────────────────┐
        ▼                                                                   │
   ┌─────────┐  speech_start   ┌───────────┐  turn_end   ┌──────────┐  first_audio  ┌──────────┐
   │ IDLE    │────────────────▶│ LISTENING │────────────▶│ THINKING │──────────────▶│ SPEAKING │
   └─────────┘                 └───────────┘             └──────────┘               └────┬─────┘
        ▲                            ▲                                                  │
        │ session_end                │ speech_start（barge-in）                          │
        │                            └─────────────── cancel TTS + flush playback ◀──────┘
        │                                                  （发 voice.user.barge_in）
        └──────────────────────────── session_end ───────────────────────────────────────┘
```

- **IDLE → LISTENING**：`speech_start`（VAD 触发，能量 + 模型双判）。
- **LISTENING → THINKING**：`turn_end`（语义端点判定，不是单纯静音计时）。
- **THINKING → SPEAKING**：TTS 首个音频帧可用即进入（不等整段生成）。
- **SPEAKING → LISTENING（barge-in）**：说话期间检测到用户语音 → `TtsStream.cancel()` +
  丢弃未播音频 + 落 `voice.user.barge_in{turn_id, at_ms, transcript_so_far?}`。
- **回退抑制（false barge-in）**：短促"嗯/对/好"等 backchannel 走 `TurnEvent.kind = "backchannel"`，
  默认**不打断**（阈值可配）；能量过低的瞬态噪声不打断。这条是"能打断"与"别太敏感"的平衡点。
- **重连**：transport 断开 → 保留会话事实、重建会话层连接；**不重放已播音频**（对齐 v5:332/336
  "未确认的结果不能靠猜测补齐"；已确认的已播音是事实）。

打断之后被截断的回复**不丢**：保留 `reply_id`、已播句子序号、完整文本引用与音频 artifact 引用，
用户说"继续"时可从断点续说（策略可配）。

## 3. 轮次检测（端点判定）

推荐组合（复用，不自研）：

| 组件 | 作用 | 候选实现 |
|---|---|---|
| VAD | 语音/非语音分段 | Silero VAD（`snakers4/silero-vad`，MIT）等 |
| 语义端点检测 | "这句说完了吗" | LiveKit turn-detector、Pipecat `smart-turn` 等 |
| 可选：语义 VAD | 用模型判断是否在思考 | LiveKit semantic VAD 一类 |

端点判定的**参数不是常量**：语言、语速、场景（免提/近讲）、是否允许抢话——这些归**风格预设**
（[style-profiles.md](style-profiles.md)）与会话层配置，不改工作策略。

## 4. 实时编排后端：接缝与选型

### 4.1 接缝（无论选谁都不变）

**编排框架**（被包进 `harness/ext/voice/`）通过一个**适配器**实现 [architecture.md](architecture.md) §2 的端口：

```python
class RealtimeOrchestrator(Protocol):
    async def start_session(self, cfg: "SessionConfig", ports: "PortBundle") -> "SessionHandle": ...
    async def stop_session(self, handle: "SessionHandle") -> None: ...
    def events(self) -> AsyncIterator["MediaEvent"]: ...

class SessionConfig(TypedDict):
    transport: dict          # webrtc | websocket | local_mic
    asr: AsrConfig
    tts: TtsConfig
    turn: dict               # VAD/turn 检测配置（来自风格预设）
    policy_bundle_ref: str   # 工作面下发的策略包（system prompt/工具/风格）
```

- **换编排后端 = 换 `RealtimeOrchestrator` 适配器**；换模型 = 换端口适配器。两者正交。
- 工作面只认 `voice.*` 事件与策略包，不 import 任何编排框架类型。

### 4.2 候选框架（调研已于 2026-09-17 完成，详见 [research-notes.md](research-notes.md) §2）

- **LiveKit Agents 1.8.2（主选）**：Apache-2.0（turn-detector 权重另有 Model License）；
  `STT._recognize_impl`/`TTS.ChunkedStream._run`/`LLM._run` 抽象；`SpeechHandle.interrupt()` +
  false-interruption resume + adaptive interruption；**已有豆包插件 `livekit-plugins-volcengine`**。
  坑：插件走经典 `app_id`+`access_token` 与 `/api/v3`，与 plan Key/plan 端点不匹配 → 需窄适配器。
- **Pipecat 1.10.0（备选，许可最干净）**：BSD-2-Clause；`STTService.run_stt`/`TTSService.run_tts`
  各只需一个抽象方法，`WebsocketSTTService`/`InterruptibleTTSService` 自带重连与打断；
  无豆包适配器，需自写 ~2 文件。
- **TEN 0.11.71（不采纳）**：中文供应商最全，但 Apache-2.0 **附加 Agora 非竞争条款**，且是需要
  Docker/TMAN 的多语言运行时，不是可嵌入 Python 库。
- **Vocode 0.1.113（不采纳）**：最后提交 2024-11-15，事实停更。

构建块：VAD = Silero VAD v6.2.1（MIT）；端点检测 = `pipecat-ai/smart-turn` v3.2（BSD-2，支持中文）
或 LiveKit `inference.TurnDetector`（权重受 Model License 限制）；传输 = WebRTC（barge-in 依赖 AEC）。

选型判据（预登记）：能否只用一个适配器接入本稿端口；打断/取消语义是否可观测且可测；
许可是否商用无碍（含模型许可与附加条款）；中文 ASR/TTS 适配成本；与本仓库 Python 栈和凭据纪律的兼容性。
**未完成独立用例（VO01–VO03）前不选定、不写入产品依赖。**

## 5. 会话层生命周期与零驻留

- 会话层是**助手 harness 自有的长驻组件**（`harness/ext/voice/runner.py`），由 runtime 按
  `extensions[kind=session-runner]` 声明起停（[assistant-work.md](assistant-work.md) §5）；
  它不写工作状态，只发事件。
- 会话活则 runner 在，`voice.session.ended` 即释放；**不是**"每个等待工作常驻一个 Agent"
  （v5:90 的反面）。共享媒体服务（如 WebRTC SFU、模型网关）可常驻，但不属本 work。
- 崩溃语义：runner 崩溃不回滚工作事实；未确认的轮次标为 `INCOMPLETE`/重连，不重放已播音
  （重放会把已确认的已播音当"未发生"，违反 v5:332/336）。
- 音频原件默认不常驻：按策略落 artifact（sha256）或只留文本与摘要；保留期单独裁决（Q-V5）。

## 6. 与"回答重点"的衔接

双工让"用户随时打断"成为常态，"回答重点"因此更重要：说太长会被打断，且打断成本高。
风格预设中的 `max_spoken_seconds`、`key_points_only`、`expand_on_request` 直接喂给：
① 端点/打断阈值（说多久开始允许抢话），② 口语化渲染守卫（见 [style-profiles.md](style-profiles.md) §3）。

## 11.10 providers

# 语音助手：供应商适配规范（Ark + 豆包语音 2.0）

状态：UNVERIFIED。本文件区分**实测观测（2026-09-17，单机探测）**、**文档推断**与**未决**。
所有探测只记录协议事实，**不记录密钥值**；凭据只在进程内从 `~/.env` 读取变量名 `ARC_PLAN_API_KEY`。
相关：[architecture.md](architecture.md) §2（端口与注册）、[research-notes.md](research-notes.md)。

> 用户明确约束：语音模型**不走** `https://ark.cn-beijing.volces.com/api/v3`（会产生额外费用）；
> 一律使用上面的 plan Base URL 与 Resource-Id。语音模型**不支持**通过 Auto 及控制台切换使用。

## 1. 三个适配器

| 端口 | 适配器 id | 供应商 | 端点 / 标识 | 凭据 |
|---|---|---|---|---|
| ConversationModel | `ark-glm-5.3-flash` | 火山方舟 Agent Plan | `https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions`，model `glm-5.3-flash` | `Authorization: Bearer $ARC_PLAN_API_KEY` |
| SpeechToText | `doubao-seed-asr-2.0` | 豆包流式语音识别 2.0 | plan 端点（见 §3），Resource-Id `volc.seedasr.sauc.duration` | `X-Api-Key: $ARC_PLAN_API_KEY` + `X-Api-Resource-Id` |
| TextToSpeech | `doubao-seed-tts-2.0` | 豆包语音合成 2.0 | plan 端点（见 §2），Resource-Id `seed-tts-2.0` | `X-Api-Key: $ARC_PLAN_API_KEY` + `X-Api-Resource-Id` |

实测（握手）：

- 语音 plan 端点用 `Authorization: Bearer …` → **HTTP 400**；用 `X-Api-Key: $ARC_PLAN_API_KEY`
  → **HTTP 101 Switching Protocols**（TTS 双向/单向、ASR 双向/单向四个端点一致）。
  即：**plan 语音网关用单一 API Key 头**，不是经典 `X-Api-App-Key`/`X-Api-Access-Key` 组合。
  每次连接另带 `X-Api-Connect-Id: <uuid>`。

## 2. TTS：`doubao-seed-tts-2.0`

### 2.1 端点

| 端点 | 用途 |
|---|---|
| `wss://openspeech.bytedance.com/api/v3/plan/tts/bidirection` | 双向流式（可多次喂文本、打断取消） |
| `wss://openspeech.bytedance.com/api/v3/plan/tts/unidirectional/stream` | 流式输出（一次请求，流式返回音频） |
| `https://openspeech.bytedance.com/api/v3/plan/tts/unidirectional` | HTTP（未探测） |

### 2.2 单向流式（实测，可跑通出音频）

**帧格式（"V1"）**：`4 字节头 + u32(BE) body 长度 + JSON body`

```
header = 0x11 0x10 0x10 0x00
          │    │    │    └ reserved
          │    │    └ serialization=JSON(0x1) << 4 | compression=none(0x0)
          │    └ message_type=FullClientRequest(0x1) << 4 | flags=0
          └ protocol_version=0x1 << 4 | header_size=0x1
```

请求 JSON（实测最小可用形状）：

```json
{"user": {"uid": "<opaque>"},
 "req_params": {"text": "…",
                "speaker": "zh_female_vv_uranus_bigtts",
                "audio_params": {"format": "mp3", "sample_rate": 24000}}}
```

**响应**：`header + [i32 event（事件帧）] + u32 session_id 长度 + ASCII session_id + u32 payload 长度 + payload`；事件码（flags 含 `0x4` 时）：

| 事件 | 含义 |
|---|---|
| 350 | `TTSSentenceStart` |
| 352 | `TTSResponse`（音频，亦见 `mt=11` AudioOnlyServerResponse 纯音频帧） |
| 351 | `TTSSentenceEnd` |
| 152 | `SessionFinished` |

实测观测（2026-09-17，两次探测，约 25 字中文；脚本 [probe_plan_endpoints.py](probe_plan_endpoints.py)）：

- 首个音频帧 **0.356 s / 0.349 s**，整个会话 **0.962 s / 0.803 s**，9–14 个音频帧、约 42.6 KB。
- 事件序列含 `350 → 352… → 351 → 152`；音频既出现在 `352 (TTSResponse)`，也见
  `mt=11 (AudioOnlyServerResponse)` 纯音频帧。
- 音色 `zh_female_vv_uranus_bigtts` 等 `*_uranus_bigtts` 被接受；
  `zh_female_cancan_mars_bigtts` 等 `*_mars_bigtts` 被拒：
  `resource ID is mismatched with speaker related resource`。
  → **音色与 Resource-Id 强绑定**，适配器必须用能力描述里的音色目录做校验，不能凭字符串猜。
  （独立佐证：`livekit-plugins-volcengine` 默认音色同为 `zh_female_xiaohe_uranus_bigtts`，
  见 [research-notes.md](research-notes.md) §2。）

> 观测边界：两次探测，未测并发/配额/长文本/不同 format；数字是**观测值不是 SLA**。

### 2.3 双向流式（协议依官方样例；建连实测）

事件协议：`header(4) + i32 event + [session_id: u32 长度 + UTF-8] + [connect_id（仅 ConnectionStarted/Failed/Finished）] + u32 payload 长度 + payload`；
带事件的消息 flags 含 `0b0100`（WithEvent）；连接级事件**不带 session_id**。

- `StartConnection=1` → `ConnectionStarted=50`（**实测**）。
- `StartSession=100`（`{event:100, namespace:"BidirectionalTTS", req_params:{speaker, audio_params, additions}}`）
  → `SessionStarted=150`（**实测**）。**服务参数只在 StartSession 生效**。
- `TaskRequest=200`：**文本在这里携带**（`{event:200, req_params:{text:"<chunk>"}}`），可多次发；
  `session_id` 是客户端生成的 UUID，同一会话内不变。
- `FinishSession=102` → `SessionFinished=152`；`FinishConnection=2` → `ConnectionFinished=52`。
- **音频走 `mt=0b1011`（AudioOnlyServer）帧**（事件 352 `TTSResponse`），不是 FullServerResponse；
  另有 `350 TTSSentenceStart`、`351 TTSSentenceEnd`、`364 TTSSubtitle`（词级时间戳，单位**秒**）。

> 上一版"发 `TaskRequest` 无响应"的观测是本稿探测器的帧解析缺陷（把含连字符的 UUID 当长度）所致，
> 不是端点行为；此处已纠正。

### 2.4 音色与风格参数（seed-tts-2.0）

- **无 `emotion` 参数**：2.0 文档中零次出现；`emotion`/`emotion_scale` 属 TTS-1.0 的
  `*_mars_*` 多情感音色。2.0 的风格表达走 `additions.context_texts`（自然语言风格指令）、
  `model:"seed-tts-2.0-expressive"`、`use_tag_parser` 内联标签，以及
  `speech_rate`/`loudness_rate`/`post_process.pitch`。
- `additions` 是 **JSON 字符串**（不是嵌套对象）；`disable_markdown_filter`、`disable_emoji_filter`
  可在 TTS 侧过滤 markdown/emoji。
- 音色与 Resource-Id 强绑定（§2.2）；部分 2.0 音色**仅支持单向流**，双向流调用会报错。
- 风格预设到参数的映射归**适配器**：[style-profiles.md](style-profiles.md) §3.2。

## 3. ASR：`doubao-seed-asr-2.0`

| 端点 | 用途 |
|---|---|
| `wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_async` | 双向流式 |
| `wss://openspeech.bytedance.com/api/v3/plan/sauc/bigmodel_nostream` | 流式输出 |

### 3.1 协议（官方样例 + 实测）

**会话用序列帧，不是事件帧**；ASR **没有 session id**，状态由连接 + 序列号维护。

```
头 4 字节 [ver<<4|hdrSize, msgType<<4|flags, ser<<4|comp, 0]
  msgType: 0b0001 FullClientRequest | 0b0010 AudioOnlyClientRequest | 0b1001 FullServerResponse | 0b1111 Error
  flags:   0b0000 无序列 | 0b0001 POS_SEQUENCE | 0b0010 末包无序列 | 0b0011 末包负序列
请求帧: 头 + i32 seq + u32 payload_size + payload
响应帧: 头 + i32 seq + u32 payload_size + JSON
错误帧: 头 + u32 code + u32 msgLen + UTF-8 msg
```

**实测（2026-09-17，完整语音往返）**：

- 连接头 `X-Api-Key` + `X-Api-Resource-Id: volc.seedasr.sauc.duration` + `X-Api-Connect-Id` + `X-Api-Sequence: -1`。
- 会话 JSON（**实测可用**）：`{"user":{"uid":…},"audio":{"format":"pcm","rate":16000,"bits":16,"channel":1},"request":{"model_name":"bigmodel","enable_punc":true,"enable_itn":true,"enable_nonstream":false,"show_utterances":true}}`。
- 音频按 200 ms 分片（16 kHz s16le），末片用负序列 + `flags=0b0011`。
- **payload 不压缩**：实测 gzip（comp 位=1）会被服务端当 JSON 解析并报
  `unmarshal request: invalid character '\x1f'`。
- **结果**：TTS 合成一句 → ffmpeg 转 16 kHz PCM → ASR，得到逐字增长的部分结果：
  `今天` → `今天天气` → … → 末帧 `definite:true` 的 `今天天气不错，我们下午3点开会。`
  （`enable_itn:true` 把"三点"写作"3点"）；响应含 `audio_info.duration` 与词级时间戳。

> 官方 `/plan` 样例里 `audio.format` 写 `"wav"`+`codec:"raw"`；本稿实测 `"pcm"`（不传 codec）也可用。
> 早先"`pcm` 被拒 `[Invalid audio format]`"是**事件帧误用**导致的会话错乱，不是格式值问题。

### 3.2 语义与参数（官方文档核对）

- `request.model_name` 必填且仅 `"bigmodel"`；`audio`/`request` 必填。
- `enable_nonstream` 两遍识别：**仅 `bigmodel_async` 可用**；官方文档称两遍的最终结果携带
  `definite:true`。**本稿实测**：`enable_nonstream:false` 时中间结果均 `definite:false`，
  末帧（负序列）`definite:true` → `AsrEvent.definite` 可由"末帧/两遍终稿"实现；
  端点检测（何时算说完）必须另行判定，不能只等 `definite`。
- `end_window_size`（ASR 2.0 范围 [300,5000]，默认 800）、`force_to_speech_time`（建议 1000）、
  `vad_segment_duration`（3000）、`show_utterances`、`enable_ddc`、`enable_lid/emotion/gender/age`、
  `result_type: full|single`。
- `additions` 可带 `lid_lang`、`emotion`、`gender`、`age`、`speaker_id`（**这是 ASR 侧的情感/性别/年龄**，
  与 TTS 发音风格无关）。
- 常用错误码：`45000001` 参数错、`45000002` 空音频、`45000081` 等包超时、`45000151` 音频格式错、
  `45000131` 超限、`45000132 >512MB`、`20000003` 静音、`55000031` 繁忙。

**判据边界**：已完成一次真实 TTS→ASR 往返（单次、单句）；并发/长音频/多说话人/`bigmodel_nostream` 未测。

## 4. LLM：`glm-5.3-flash`（实测）

- `POST https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions`，`Authorization: Bearer $ARC_PLAN_API_KEY`，
  `stream:true` → `text/event-stream`，`data: {...}` 分片，以 `data: [DONE]` 结束（**实测**）。
- 分片 delta 含 `content` 与 `reasoning_content`；`choices[0].delta`（**实测**）。
- `thinking.type = "disabled"` → **HTTP 400 InvalidParameter**："not supported by this model"
  （glm-5.3-flash 思考**始终开启**，**实测**）。
- `reasoning_effort: "minimal"` 被接受（**实测**）。

延迟观测（2026-09-17，同一 prompt，两次探测，**观测值非基线**；脚本 [probe_plan_endpoints.py](probe_plan_endpoints.py)）：

| 配置 | 首个 content token | 结束 | 说明 |
|---|---|---|---|
| 默认（reasoning 全开，max_tokens=2048） | **4.313 s / 5.502 s** | 5.003 / 6.130 s | 124–134 字回答（第二次测的是 `first_content`） |
| `reasoning_effort: "minimal"` | **1.289 s / 0.907 s** | 2.418 / 1.891 s | 124–128 字回答 |
| 默认 + max_tokens=256 | 从未出现 content（全被 reasoning 吃掉，finish=length） | — | 复证 2026-09-14 的推理预算教训 |

> 两次差异（4.3→5.5 s；1.29→0.91 s）说明**单次数字不可当基线**；须按 VO07 做多次采样再定阈值。

**对语音的直接结论**：语音实时路径若用 glm-5.3-flash，必须走 `reasoning_effort: minimal`（或 low）
并给足 `max_tokens`（否则正文永远不出现）；把"首 token 延迟"作为**必测项**而非假设
（[validation-plan.md](validation-plan.md) VO07）。若仍不达标，退化方案是引入一个非推理/更小模型
专用于实时口语路径，并把"策略/记忆/工具"仍留在工作面——换模型正是本设计要支持的。

## 5. 凭据与安全

- 变量：`ARC_PLAN_API_KEY`（用户 `~/.env`，仓库外）。适配器只接受 `credential_ref`，**不落值**。
- 工作目录、证据、日志、错误消息中不得出现密钥（错误打印前先脱敏）。
- 模型/工作不能指定端点、Header、预算（沿用 `lore_provider` 的"端点是可信构造参数"边界）。

## 11.11 style-profiles

# 语音助手：风格预设与"回答重点"的口语化渲染

状态：UNVERIFIED 设计稿。schema 为候选契约。
相关：[architecture.md](architecture.md)、[duplex.md](duplex.md)、
[work-directory-landing.md](../work-directory-landing.md) §4.6 示例 3 / §4.7（信息项 / 投影 / 呈现）。

## 1. 目标

用户要的不是"把答案念出来"，而是"**像人一样，先给结论和要点，细节按需展开**"。
语音是线性、不可跳读、打断成本高的通道：一次说 10 分钟等于交互失败。

因此"回答重点"必须是**结构造成的**，而不是靠模型自觉：
每轮给模型的上下文里**本来就没有全文**，只有要点 + 指针；要细节时靠工具按需取回
（对齐 v5:250 "不预先展开全量目录与全文"、v5:252 "裁剪只改可见视图，不删恢复依据"）。

## 2. 风格预设（Style Profile）

预设是**版本化产物**，当前生效的是**事实**（`voice.style.set{style_id, spec_ref, base_rev}`）。

```json
{
  "style_id": "brief-professional-zh",
  "label": "简短专业（中文）",
  "language": "zh-CN",
  "answer_mode": "key_points",          // key_points | full | adaptive
  "verbosity": {
    "max_spoken_seconds": 20,           // 口语时长预算（守卫用）
    "max_sentences": 4,
    "target_points": 3,                 // 目标要点数
    "detail_on_request": true           // "展开第二点"时再讲细节
  },
  "tone": "concise_professional",       // 口吻：专业/亲和/简短/活泼/严肃
  "spoken_form": {
    "markdown": "strip",                // 不念 ** / # / 表格
    "urls": "skip",                     // 不逐字符念链接
    "code": "summarize",                // 代码只说作用，不朗读符号
    "numbers": "normalize",             // 数字/单位口语化
    "lists": "prose"                    // 列表转成口语连接词
  },
  "expansion": {
    "offer": true,                      // 结尾给"要不要展开"的选项
    "granularity": "point"              // point | section | full
  },
  "prosody": {                          // → TTS 参数（见 §3.2 映射）
    "speech_rate": 0,                   // [-50,100]，100 = 2x
    "loudness_rate": 0,                 // 豆包 loudness_rate
    "pitch": 0,                         // 豆包 post_process.pitch，[-12,12]
    "style_instructions": ["用简洁、自然的语气说话"]   // 豆包 context_texts（自然语言风格指令）
  },
  "turn_taking": {                      // → 会话层端点/打断阈值
    "barge_in": true,
    "backchannel_min_ms": 200,
    "endpoint_silence_ms": 500
  },
  "provider_bindings": {
    "tts_provider": "doubao-seed-tts-2.0",
    "tts_voice": "zh_female_vv_uranus_bigtts"
  }
}
```

> **注意（供应商事实）**：`seed-tts-2.0` **没有 `emotion` 参数**（`emotion`/`emotion_scale` 属 TTS-1.0
> `*_mars_*` 多情感音色）。2.0 的风格走 `context_texts`（自然语言指令，不计费）、
> `model:"seed-tts-2.0-expressive"`、`use_tag_parser`（内联 COT 标签）与
> `speech_rate`/`loudness_rate`/`post_process.pitch`。见 [providers.md](providers.md) §2.4。
> 因此风格预设 schema **不固化 `emotion` 字段**——能力描述未声明该参数时不得下发。

预设的**边界**：

- 预设是**呈现/风格**，不改事实本身；同一事实可用不同预设渲染多次，各自留 revision。
- 预设变更**不从本轮中途生效**：带 `base_rev` 的条件受理，陈旧基线拒绝（landing §4.5）；
  正在说话的一轮用旧预设说完（v5:204 "不静默换策略"）。
- 预设里的 `provider_bindings` 必须与能力描述协商通过，否则会话开始即拒绝（不降级）。

## 3. 三层链路：全文 → 要点 → 口语

对齐 landing §4.7 的三层，逐层收窄，任何一层都不删依据：

| 层 | 落点 | 本工作里做什么 |
|---|---|---|
| **① 信息项（views）** | manifest `views` | 声明"全文/检索结果/工具输出/记忆摘要/当前轮状态"等可供展示项；有稳定 id、来源可定位、缺失显式 |
| **② 投影（projection）** | `roles.projection` | **选**最相关的 top-k 片段 + 给全文指针；注入"口语简报帧"；**不灌全文** |
| **③ 呈现（presentation）** | `roles.presentation` | 把风格预设编成 system prompt / 请求形式：只讲结论与 N 个要点、列表转口语、给展开选项 |

**呈现层的指令模板（候选，要点在约束而非修辞）**：

```
你是语音助手，正在与用户实时通话。
- 先给结论，再给最多 {target_points} 个要点；总时长不超过 {max_spoken_seconds} 秒。
- 只使用本轮提供的要点与事实；不得编造未提供的细节。
- 用户要求细节时，用提供的指针/工具取回后再讲。
- 输出是可朗读文本：不要 markdown、不要念链接、代码只说作用。
```

### 3.2 风格预设 → TTS 参数映射（豆包 seed-tts-2.0）

风格预设是**供应商无关**的意图；适配器把它翻译成具体参数，能力描述未声明的字段**不下发**：

| 预设意图 | 豆包 2.0 参数 | 备注 |
|---|---|---|
| 语气/表达风格 | `additions.context_texts: ["用…的语气说话"]` | 自然语言指令；2.0 音色可用、官方称不计费 |
| 更强表达力 | `model: "seed-tts-2.0-expressive"` | 与克隆音色/`context_texts` 搭配 |
| 内联风格标记 | `additions.use_tag_parser: true` + `<cot text=…>…</cot>` | 文本内嵌风格标签 |
| 语速 | `audio_params.speech_rate` `[-50,100]` | 100 = 2x |
| 音量 | `audio_params.loudness_rate` `[-50,100]` | |
| 音高 | `additions.post_process.pitch` `[-12,12]` | |
| 去 markdown/emoji | `additions.disable_markdown_filter` / `disable_emoji_filter` | TTS 侧再兜一层（呈现层仍应清洗） |
| 词级时间戳 | `audio_params.enable_subtitle` | 中文/英文；用于字幕与打断定位 |
| 方言 | `additions.explicit_dialect`（如 `beijing`/`sichuan`） | |
| **情感** | **不支持**（2.0 无 `emotion`） | 属 1.0 `*_mars_*` 多情感音色；不要下发 |

> 该映射属**适配器职责**，不属风格预设 schema；换 TTS 供应商只改适配器，预设与工作面不变。

## 4. 守门（guard）：预算超了就压缩，不是截断了事

模型仍可能超预算。`roles.logic` 在提交前做**有界**度量与收敛：

```
candidate = 模型候选口语文本
estimate  = 字符数 / 语言语速  → 预估秒数
if estimate <= max_spoken_seconds: 通过
else:
    pass2 = 一次"压缩为要点"的有界再生成（同一预算，最多 N 次）
    if pass2 仍超: 只播前 max_sentences 句 + 明确提示"细节随时展开"
    落 voice.reply.condensed{reply_id, from_ref, reason, budget, kept_ref}
```

规则：

- **压缩是有损渲染，不是删内容**：完整答案仍在 `content/`/artifact（版本化），
  `voice.reply.condensed` 记 `from_ref` + `kept_ref`，用户展开时可达（v5:252）。
- 预算与最大压缩次数是**配置**，不是硬编码常量；阈值不预设 SLA（v5:349）。
- 压缩失败（模型不可用等）→ 显式 `voice.reply.degraded{reason}`，不静默念全文。

## 5. 与双工的衔接

- 长回答 → 更容易被打断 → 预算约束同时服务"别念太长"和"打断点可控"。
- 用户打断后说"继续"：从 `kept_ref` 的断点续说，而不是从头念（[duplex.md](duplex.md) §2）。
- backchannel 不打断，但可用于"边听边嗯"的自然感（会话层回放，不入工作事实）。

## 6. 反例（不得变成什么）

- 把整篇文档塞进上下文再让模型"只讲重点"（没省 token，也没省时间，且容易漏）。
- 用截断代替压缩且不留引用（信息静默丢失）。
- 风格预设写死成 prompt 常量，用户改不了、换不了、无版本。
- 用"说完了"事件当业务完成（v5:161,208：没有通用终态）。

## 11.12 research-notes

# 语音助手：调研记录（开源实时语音框架与协议）

状态：**调研中（主要来源已核对，框架定版与 ASR 音频格式未决）**。本文件不是验收证据；
引用外部资料标注来源与观察日期，未经独立用例不写入产品依赖（对齐 [GOAL.md](../../../GOAL.md) G2）。
相关：[duplex.md](duplex.md) §4、[providers.md](providers.md)。

## 1. 待检验问题（先有问题，再收资料）

| 问题 | 观测/判据 | 停止条件 |
|---|---|---|
| Q1 用哪个开源框架承载实时会话层？ | 能否用一个适配器接入本稿端口；打断/取消是否可观测可测；许可；中文 ASR/TTS 适配成本 | 候选缩到 1 主 1 备并列出理由 |
| Q2 豆包/方舟在开源生态里有没有现成适配？ | 现成插件/适配器的接口、许可、维护活跃度、支持的端点与鉴权 | 至少一条可复用路径 + 其与 plan 端点的差距 |
| Q3 双工与打断有哪些成熟实现可直接用？ | VAD / 轮次检测 / 打断策略的库与默认行为 | 去重后的构件清单，标注"复用/自研" |
| Q4 plan 语音端点的真实协议 | 实测握手/帧/事件/音频格式（[providers.md](providers.md)） | 关键路径跑通或明确未决 |

## 2. 框架对比（版本/许可为 2026-09-17 快照；**引用前须复核**）

| 框架 | 版本 | 许可 | 抽象形态 | 双工/打断 | 豆包适配 | 结论 |
|---|---|---|---|---|---|---|
| **LiveKit Agents**（`livekit/agents`） | `livekit-agents` 1.8.2 | Apache-2.0；**turn-detector 模型权重另有 LiveKit Model License**（仅限配合本框架用） | `STT._recognize_impl` / `TTS.ChunkedStream._run` / `LLM._run` / `VAD` | `SpeechHandle.interrupt()` + false-interruption resume + adaptive interruption + preemptive generation | **有**：`livekit-plugins-volcengine`（社区） | **主选** |
| **Pipecat**（`pipecat-ai/pipecat`） | `pipecat-ai` 1.10.0 | **BSD-2-Clause**（最宽松，无模型许可附加） | `STTService.run_stt` / `TTSService.run_tts`（各只需 1 个抽象方法）；`WebsocketSTTService`、`InterruptibleTTSService` | `InterruptionFrame` + TTS 聚合器/序列队列 flush；保留 `UninterruptibleFrame`（工具结果不丢） | **无**（需自写 ~2 文件） | **备选（许可最干净）** |
| **TEN Framework** | 0.11.71 | Apache-2.0 **+ Agora 非竞争附加条款**（不是纯 Apache） | Extension + manifest/property + `ten_ai_base` 基类 | 全双工 realtime 示例 + TEN turn detection | **有**（`bytedance_asr`/`bytedance_tts_duplex`/`bytedance_llm_based_asr`，走 `/api/v2/asr` 等） | **不采纳**：许可附加条款 + 多语言运行时（非可嵌入 Python 库） |
| **Vocode** | `vocode` 0.1.113 | MIT | `StreamingConversation(transcriber, agent, synthesizer, output_device)` | 基础打断 | 无 | **不采纳**：最后提交 2024-11-15，事实停更 |

### 2.1 关键发现：已有面向本供应商的开源插件

**`livekit-plugins-volcengine`**（LiveKit Agents 插件，社区 `di-osc/livekit-plugins-chinese` 出品；
PyPI 最新 `1.8.1.post0`，2026-09-14；`requires_dist: livekit-agents>=1.8.1,<1.9`，Python ≥3.10）：

- STT：豆包流式识别，`resource_id="volc.seedasr.sauc.duration"`，
  默认 `base_url=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel`，支持
  `interim_results`、`enable_punc`、`enable_itn`、`vad_segment_duration`、`end_window_size`、
  `force_to_speech_time`。
- TTS：Seed TTS 1.0/2.0，`resource_id="seed-tts-2.0"`，音色示例
  `zh_female_xiaohe_uranus_bigtts`，`sample_rate ∈ {8000,16000,24000}`；音色/格式/采样率会发送，
  **语速/音量/音调当前版本未转发**。
- LLM：方舟文本模型（OpenAI 兼容，默认 `https://ark.cn-beijing.volces.com/api/v3/`）。
- Realtime：豆包端到端实时语音（`O`/`SC`），全双工
  `wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue`，16 kHz PCM 入 / 24 kHz
  `pcm_s16le` 出；支持 `speaking_style`（"说话简洁、自然，语速适中"）。

**与本设计的差距（必须诚实记录）**：

1. **plan 鉴权/端点不匹配**：插件的 STT 走经典 `/api/v3/sauc/bigmodel`，用**经典控制台
   `app_id`+`access_token`**；LLM 默认走 `/api/v3`（用户明确禁止，会产生额外费用）。
   本用户只有 plan 单一 Key（`ARC_PLAN_API_KEY`）且要求走 `/api/v3/plan/...`。
   → **即使选 LiveKit，也大概率要自写/改写一个窄适配器指向 plan 端点**（本稿已实测出 plan 帧与鉴权，
   见 [providers.md](providers.md)）；或先确认插件是否接受 plan Key。
2. **TTS prosody 缺口**：语速/音量/音调未转发，风格预设的 prosody 需要自己补。
3. **Realtime 是另一条路线**：端到端模型自做 ASR+LLM+TTS，与本稿"工作面管策略、会话层管编排"不同；
   可作**独立备选**评估，不默认采用。
4. **供应链**：插件为社区维护、单一维护者、许可元数据缺失（PyPI `license: None`）→ 采用前须审源码许可；
   PyPI 存在**仿冒名** `livekit-plugins-volcenginee`（多一个 `e`），不得安装；版本须钉死并 vendor 审计。

### 2.2 抽象纯度对照（"可替换模型"）

- **Pipecat 最纯**：一个新供应商 = 实现 `run_stt()` 或 `run_tts()` 两个生成器方法之一；
  WS 断线重连/keepalive/打断管线由 `WebsocketSTTService`/`InterruptibleTTSService` 提供。
- **LiveKit 接近**：实现 `_recognize_impl` + `RecognizeStream._run` / `ChunkedStream._run`；
  已有豆包实现可直接用/改写。
- **结论**：若"可替换 + 少造轮子"压过许可纯度 → **LiveKit Agents（主选）**；
  若"许可无附加 + 完全自有适配器"压过时间 → **Pipecat（备选）**。
  两条路都必须先过 [validation-plan.md](validation-plan.md) VO01–VO03（同一端口套件跨适配器）。

### 2.3 plan 变体的官方依据与"别造轮子"

- 官方页：[Agent Plan 接入语音模型（企业版）](https://docs.volcengine.com/docs/82379/2516290) /
  [个人版](https://docs.volcengine.com/docs/82379/2516286)。鉴权为**单一"专属 API Key"放 `X-Api-Key`**
  + `X-Api-Resource-Id`（`seed-tts-2.0` / `volc.seedasr.sauc.duration`）+ `X-Api-Connect-Id`；
  ASR 另带 `X-Api-Sequence: -1`。**没有** `X-Api-App-Id/Access-Key`。
  与标准端点的差异只有**路径前缀与鉴权**；Resource-Id、二进制帧、JSON 负载一致；计费改 AFP。
- **官方样例即完整 Python 客户端**（含 `protocols.py`、双向 TTS、单向流 TTS、HTTP NDJSON、
  aiohttp ASR 客户端）——内嵌在上述 plan 文档页里；另有官方 TTS 双向协议 zip
  （`protocols_.py`）。**结论：适配器应移植官方样例，不自行发明帧格式。**
- **没有**面向这些 WS 端点的官方 pip SDK（`volcengine-python-sdk` 是 Ark LLM SDK；语音 SDK 仅移动端）。
- 社区：Pipecat **无**豆包支持；LiveKit 有社区插件（`Decent9967/livekit-plugins-volcengine` 等），
  目标是 `bigmodel_async` + `tts/bidirection` 的**标准**端点，**均不指向 `/plan`**。
  TEN 的豆包扩展支持**未核实**（文档站 JS-only，勿据此宣称）。

## 3. 可复用的构建块（去重清单）

| 构件 | 选型 | 版本/许可 | 备注 |
|---|---|---|---|
| **VAD** | Silero VAD（`snakers4/silero-vad`） | v6.2.1 / **MIT** | 事实标准；PyTorch + ONNX；16 kHz/8 kHz |
| | webrtcvad | 2.0.10 / MIT | 冻结、C 扩展，仅作基线 |
| | TEN VAD | v1.0-ONNX / Apache-2.0+条款 | 更小更快，16 kHz only；许可有附加条款 |
| **轮次/端点检测** | LiveKit `inference.TurnDetector` | 随 `livekit-agents`；**权重另有 Model License** | 已是 `AgentSession` 默认；旧 `livekit-plugins-turn-detector` **已废弃** |
| | `pipecat-ai/smart-turn` v3.2 | **BSD-2-Clause** | 音频原生（含韵律）、**支持中文**、可 CPU；许可最干净 |
| | TEN Turn Detection | Apache-2.0+条款 | Qwen2.5-7B 文本分类，含 wait 态；较重 |
| **传输** | WebRTC（LiveKit SFU / Pipecat SmallWebRTC） | Apache-2.0 / BSD | **barge-in 依赖 AEC**，WebRTC 原生自带；WS+Opus 仅原型，需自担抖动/丢包 |
| **打断策略** | 复用框架内建 | 见 §2 | 不自己写音频级打断 |
| **前处理** | 框架/平台 AEC/降噪 | — | 不自研 |

## 4. 推荐（倾向，非裁决）

- **主选：LiveKit Agents + `livekit-plugins-volcengine`**（"别乱造轮子"；已有豆包插件），
  但**必须先解决 plan 鉴权/端点差距**（§2.1 差距 1），并规避 Model License 锁定
  （可改用 Silero VAD + smart-turn 作为端点检测）。
- **备选：Pipecat**（BSD-2、抽象最纯，自写豆包适配器 ~2 文件）。
- **端到端 Realtime 路线**：单独评估，不默认采用。
- 选型须过 VO01–VO03 后才写入产品依赖；框架 commit/tag 与许可须固定记录（G2 要求）。

## 5. 来源（观察日期 2026-09-17；版本为快照，引用前复核）

| 编号 | 来源 | 用途 | 状态 |
|---|---|---|---|
| S1 | [livekit-plugins-volcengine · PyPI](https://pypi.org/project/livekit-plugins-volcengine/) | 插件版本/许可/Python/依赖范围 | 已核对 |
| S2 | [livekit-plugins-chinese · 火山引擎插件文档](https://di-osc.github.io/livekit-plugins-chinese/plugins/volcengine) | STT/TTS/LLM/Realtime 参数与默认端点 | 已核对 |
| S3 | [di-osc/livekit-plugins-chinese · GitHub](https://github.com/di-osc/livekit-plugins-chinese) | 插件源码/许可审计 | 待做（GitHub API 限流） |
| S4 | [livekit/agents](https://github.com/livekit/agents)（`stt.py`/`tts.py`/`llm.py`/`voice/turn.py`/`voice/speech_handle.py`） | 基类、打断、turn detection、preemptive generation | 已核对（源码） |
| S5 | [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat)（`services/stt_service.py`/`tts_service.py`/`frames/frames.py`） | `run_stt`/`run_tts`、`InterruptionFrame`、`COMMUNITY_INTEGRATIONS.md` | 已核对（源码） |
| S6 | [pipecat-ai/smart-turn](https://github.com/pipecat-ai/smart-turn) | 端点检测模型与许可 | 已核对 |
| S7 | [snakers4/silero-vad](https://github.com/snakers4/silero-vad) | VAD 版本/许可 | 已核对 |
| S8 | [TEN-framework/ten-framework](https://github.com/TEN-framework/ten-framework) + `bytedance_asr` 扩展 | 中文供应商矩阵、许可附加条款 | 已核对（许可需法务复核） |
| S9 | [volcengine/rtc-aigc-demo](https://github.com/volcengine/rtc-aigc-demo)、[volcengine/veadk-python](https://github.com/volcengine/veadk-python) | 官方 demo/工具链参照 | 待定版核对 |
| S10 | 本仓库实测探测（[providers.md](providers.md)、[probe_plan_endpoints.py](probe_plan_endpoints.py)） | Ark plan LLM、豆包 plan ASR/TTS 帧与鉴权、TTS→ASR 往返 | 已观测（少量样本） |
| S11 | [Agent Plan 接入语音模型（企业版）82379/2516290](https://docs.volcengine.com/docs/82379/2516290) / [个人版 82379/2516286](https://docs.volcengine.com/docs/82379/2516286) | plan 鉴权、五个 plan 端点、完整官方 Python 样例 | 已核对（官方文档内容 API） |
| S12 | 官方 ASR 协议文档 6561/1354869、ASR 2.0 文档 6561/2630027、6561/2628951、TTS 2.0 文档 6561/2532486、6561/2534913、6561/2528925、错误码 6561/2611432、6561/2534853 | 序列帧、字段、错误码、`context_texts`（无 `emotion`） | 已核对 |

## 6. 未决清单

- U1 plan 语音端点官方文档核对（尤其 ASR `audio.format` 合法取值、双向 TTS `TaskRequest` 语义）。
- U2 `livekit-plugins-volcengine` 是否支持 plan Key/plan Base URL；不支持时的自研适配器工作量与许可审计。
- U3 框架定版（固定 commit/tag）、许可记录与供应链（仿冒包、单一维护者）评估。
- U4 端到端 Realtime 路线 vs 两面编排路线的对照实验。
- U5 LiveKit turn-detector 的 Model License 锁定是否可接受；不接受则用 Silero + smart-turn 组合。

## 11.13 validation-plan

# 语音助手：验证计划（预登记，未执行）

状态：**全部 UNVERIFIED，未执行、无实现**。本文件是 G4 前的预登记输入，不表示任何能力通过。
规则：每条必须有独立判据、能拒绝相关错误、明确观测、匹配范围；组件通过不等于组合/系统通过
（AGENTS.md、[docs/validation-status.md](../../../docs/validation-status.md)）。
相关：[architecture.md](architecture.md)、[duplex.md](duplex.md)、[style-profiles.md](style-profiles.md)、
[providers.md](providers.md)。

## A. 语音能力抽象（换模型）

| ID | 判据 | 相关反例 | 观测 | 独立性备注 |
|---|---|---|---|---|
| VO01 | **同一端口一致性套件对 ≥2 个适配器复跑**：`fake`（离线）与 `doubao` 产出同一组合同事实（事件类型、顺序、取消语义、错误分类） | 只有接口、没有共用判据；"两个都能跑"冒充可替换 | 两适配器的套件结果矩阵 | 判据来自端口契约，不来自实现 |
| VO02 | **能力协商拒绝路径**：请求音色/格式/采样率不在能力描述内 → 会话开始即**响亮拒绝**，且不发起供应商连接 | 静默降级到默认音色/格式 | 拒绝码 + 未建连的网络观测 | 需正反例；拒绝≠运行失败 |
| VO03 | **不透明标识钉定**：适配器对回显的 model/voice 常量校验；断言别名/音色轮换会**响亮失败** | 前缀放行、静默接受任意回显 | 构造别名响应的离线桩 | 沿用 `lore_provider` 的别名判据 |
| VO04 | **凭据不落库**：工作目录、证据、日志、错误消息中无密钥值；仅出现变量名 | 错误消息回显 Header；证据带 key | 扫描 + 脱敏错误注入 | 对齐 glossary:100-102 |
| VO05 | **离线可复现**：无网络时 `fake` 适配器驱动整条工作面链路，结果确定性可复现 | 离线即不可运行、依赖真实端点 | 断网复跑 ×2 字节比较 | 与 VO01 共用套件 |

## B. 流式与双工

| ID | 判据 | 相关反例 | 观测 | 独立性备注 |
|---|---|---|---|---|
| VO06 | **流式 ASR 顺序与语义**：partial 单调递增、final 唯一且 definite；乱序/重复分片被拒绝或去重 | 把 partial 当 final 入记忆；分片乱序静默接受 | 事件序列 + 事实流 | 离线桩 + 真实端点各一轮 |
| VO07 | **流式 TTS 与取消**：首音频在整段文本生成完之前到达；`cancel()` 后**在给定时限内不再有音频帧** | 取消后仍出声；必须等整段才能播 | 时间戳 + 音频帧计数 | 时限先测量再冻结 |
| VO08 | **barge-in 正确性**：说话期间用户语音 → 取消 TTS + 清播放队列 + 落 `voice.user.barge_in` + 状态回 LISTENING；被截断回复的引用与断点保留 | 打断后继续出声；截断回复丢失；状态机卡死 | 音频 + 事件 + 状态机轨迹 | 与 VO07 的取消判据独立（前者测机制，后者测策略） |
| VO09 | **false barge-in 抑制**：短促 backchannel（如"嗯"）与低频噪声**不打断**；真实插话在阈值内打断 | 什么都打断；或什么都不打断 | 构造音频 × 标注 | 阈值可配但判据固定 |
| VO10 | **轮次检测与恢复**：停顿思考不抢话、说完及时转 THINKING；transport 断开重连后不重放已播音、未确认轮标 INCOMPLETE | 静音计时抢话/等太久；重连重放 | 时间线 + 事实 | 端点参数来自风格预设 |

## C. 风格预设与"回答重点"

| ID | 判据 | 相关反例 | 观测 | 独立性备注 |
|---|---|---|---|---|
| VO11 | **预算守门**：输入远超预算的长答案 → 口语输出在 `max_spoken_seconds`/`max_sentences` 内；`voice.reply.condensed` 记 `from_ref` + `kept_ref`，完整答案仍可经引用取回 | 截断且无引用；超预算照念全文 | 口语文本长度 + 引用可达性 | 对齐 v5:252 |
| VO12 | **要点优先不丢依据**：投影里**没有**全文（token/字节可证），只有要点 + 指针；模型请求细节时经工具取回并可再渲染 | 全文入上下文再"总结"；细节不可达 | 投影产物 + 工具往返 | 判据是投影形状，不评文风 |
| VO13 | **预设生效边界**：会话中改 `voice.style.set` 带 `base_rev`；陈旧基线拒绝；新预设从**下一轮**生效，当前轮不中途换 | 中途换策略；无版本覆盖 | 事实 + 实际投影/参数 | 对齐 v5:204 |
| VO14 | **口语形式**：markdown/URL/代码按 `spoken_form` 处理（不念符号），数字口语化 | 把 `**加粗**`、`https://…` 逐字符念出 | 口语文本检查 + 音频可选 | 形式判据，独立于内容正确性 |

## D. 与工作面/框架的接缝

| ID | 判据 | 相关反例 | 观测 | 独立性备注 |
|---|---|---|---|---|
| VO15 | **音频不进事实流逐片落库**：ASR partial / TTS chunk 不逐条成为面事实；只落轮次事实 + artifact 引用 | 音频分片刷爆 facts | facts 行数 + artifact 摘要 | 对齐 landing §4.4 情况 2 |
| VO16 | **会话设施零驻留**：会话结束后工作专属媒体进程/连接释放；共享服务可常驻 | 每工作常驻 Agent | 进程/连接观测 | 对齐 v5:90 |
| VO17 | **会话层不写工作状态**：会话层被拒写 `harness/`、`surface/head`、`ledger/`；只能经 event 入口 | 会话层直接改文件当状态 | 挂载 + 写尝试 + 字节不变 | 对齐 landing §8 |
| VO18 | **幂等受理**：同一 `session_id+turn_id` 重复交付只受理一次；冲突答案被拒 | 重复轮次/重复副作用 | 去重账 + 事实流 | 对齐 landing §6 幂等 |

## E. 测量项（先测量再定阈值，不预设 SLA，v5:349）

| 项 | 方法 | 当前已知（2026-09-17 两次观测，非基线） |
|---|---|---|
| LLM 首 content token | 固定 prompt，`reasoning_effort` 两档各 N 次 | 默认 ≈4.3–5.5 s；`minimal` ≈0.9–1.3 s（[providers.md](providers.md) §4） |
| TTS 首音频 | 固定文本，记首个音频帧 | ≈0.35 s（单向流式；官方称双向首包 ≈0.3 s，单向 ≈0.6 s） |
| ASR 首部分结果 | TTS 句 → ffmpeg 16 kHz PCM → ASR | 200 ms 分片下逐字增长，末帧 `definite:true`（[providers.md](providers.md) §3.1） |
| 端到端轮次延迟 | 用户说完 → 首个音频 | 待测 |
| 打断响应 | 用户说话 → 音频停止 | 待测 |

## E2. 对话记录（[conversation-record.md](conversation-record.md)）

| ID | 判据 | 相关反例 | 观测 | 独立性备注 |
|---|---|---|---|---|
| VO24 | **记录完整性**：每个 user/assistant 片段有目录 + `meta.json` + 音频，`manifest.json` 的 sha256/bytes/时长与实际逐项相符；缺片段**显式报告** | 有事实无音频；sha 不符仍算完整；静默丢片段 | 目录扫描 + 哈希 + manifest 对账 | 判据来自 manifest 契约 |
| VO25 | **双工切片正确**：用户/助手/打断片段时间轴真实**重叠**保留；backchannel 有片段但不构成 turn；静音不产片段 | 只留"谁赢"；重叠被合并；backchannel 被当一轮 | 时间轴 + meta 的 `interaction` | 与 VO08/VO09 独立（那测机制，这测记录） |
| VO26 | **语音/文本同构**：`modality=text` 的输入产生同结构片段（`audio=null`），字段齐全 | 文本输入不入记录；另建一套结构 | 两条输入的记录结构比对 | 判据是同构性 |
| VO27 | **分析可重算且不覆盖原始**：换分析器版本产生新 `analysis/<name>/<version>.json`，**原始 `audio` sha256 不变**；分析带 `input_sha256` | 分析就地改写原始；版本覆盖；分析对不上输入 | 前后哈希 + 分析文件 | 对齐 v5:252 |
| VO28 | **保留/删除显式**：按 `retention_class` 删除后 manifest 报告缺失、相关分析标记失效；不静默补造 | 删除无痕；分析仍显示为有效 | 删除前后 manifest + 分析状态 | 隐私必须项 |

## E3. 定时与承诺（[scheduling.md](scheduling.md)）

| ID | 判据 | 相关反例 | 观测 | 独立性备注 |
|---|---|---|---|---|
| VO29 | **日程到点触发恰一次**：标准 crontab/一次性日程到点落 `sys.schedule.fired` 并开轮；取消后不再触发 | 到点不发；重复发；取消无效 | 事实流 + 触发轨迹 | 判据来自"到点即事件" |
| VO30 | **零驻留**：两次触发之间无工作专属常驻进程/长连接；调度工具是共享设施 | 轮内 `sleep` 常驻；每工作一个调度器进程 | 进程/连接观测 | 对齐 v5:90；与 VO16 独立（那测会话，这测定时） |
| VO31 | **权威在数据、crontab 是派生物**：日程存工作目录；换宿主后 runtime 重新 materialize 并继续生效；旧宿主条目无需迁移 | 日程只存在宿主 crontab 里；换宿主丢失 | 迁移前后对比 + 宿主 crontab 检查 | 与对话记录同一模式（外部机制可替换） |
| VO32 | **延迟补齐与时区**：过期未发**带 `lateness_ms` 补发**、已发不重发；用户时区解析正确；改期=追加事实 | 静默丢过期日程；按宿主时区算错；原地覆盖 | 崩溃/迁移注入 + 实际触发时刻 | 对齐 landing §6 |
| VO33 | **送达≠到点**：无活跃会话时未送达不得落 `notified`；重试有上限并最终 `expired` 留痕 | 把"到点"当"已提醒" | 送达记录 + 事实流 | 依赖对外投递缺口 |
| VO34 | **错误归属与聚合**：供应商错误落 `voice.adapter.error`（harness）且按窗口聚合、**脱敏**；runtime 设施错误落 `sys.*` | 每个失败包一条；错误里带密钥/URL | 事实流 + 密钥扫描 | 对齐 glossary:100-102 |
| VO35 | **标准语法、无自定义**：新增一个需要定时的 harness 只用标准 crontab/一次性时刻 + 已声明事件定义，**runtime 产品代码零改动** | 必须给 runtime 加自定义字段/DSL 才能定时 | 注册结果 + 触发轨迹 + runtime 版本 | 判据是可表达性，对齐 VE13 |
| VO36 | **cron 不写事实**：调度条目只调用 runtime 入口；工作/模型无法直接改宿主 crontab；事实流写者唯一 | 条目直接 append facts；工作写 crontab | 宿主 crontab 内容 + 事实流写者观测 | 安全/单写者必须项 |

## E4. 执行超时与存活检查（[execution-timeouts.md](execution-timeouts.md)）

| ID | 判据 | 相关反例 | 观测 | 独立性备注 |
|---|---|---|---|---|
| VO37 | **默认可观测**：长调用按默认间隔发 `sys.tool.check`（带 `silent_for_ms`）；系统不静默卡死 | 无任何观测，永久挂起无迹 | 事实流 + 时间线 | 判据来自"runtime 不让系统死掉" |
| VO38 | **到点不自动杀**：到达默认/软预算时**不杀**，harness 可继续；只有 harness 判定或资源上限才终止（终止时进程组全消失） | 30 s 无条件杀，误杀长工作；只杀直接子进程 | 事实流 + 进程组观测 | 复用 M03 进程组先例 |
| VO39 | **结果四分类**：`ok/failed/timeout/unknown` 可区分；`timeout` 不写成"没执行"；有副作用带 `side_effects` | 把无结果记成失败或"未执行" | 事实流字段核对 | 对齐 v5:332/336、X 合同 |
| VO40 | **资源安全网**：超过硬上限/并发上限时回收资源并落 `abandoned/unknown`；恢复先查询不重跑 | 回收后当失败重试，产生第二次副作用 | 外部效果计数 + 事实流 | 机制必须项 |
| VO41 | **默认与上限**：harness 默认按类别生效；显式值不得越 runtime 上限，越界被拒且留痕 | 模型设无限预算绕过 | 拒绝记录 + 实际检查时刻 | 与 VO40 独立（那测回收，这测拒绝） |
| VO42 | **in-band 是纵深**：命令级 `timeout` 存在时仍由 runtime 兜底；连接层无响应由 `check`/安全网处理并落 UNKNOWN | 依赖脚本里的 `timeout` 作为唯一保障 | 注入无响应 + 进程观测 | 与 VO37 独立（那测默认，这测兜底路径） |

## F. 通过门槛（草案）

- 每个适配器独立通过端口套件（V1–V5）→ 才允许进入会话层组合；
- 流式/双工（V6–V10）需真实端点 + 音频注入，不接受"应用声明"；
- 风格/接缝（V11–V18）需实际投影/事实/进程观测；
- 记录（VO24–VO28）需真实音频与目录对账，不接受"写了文件就算"；
- 定时/承诺（VO29–VO36）需真实时间流逝/崩溃注入，不接受把"到点"当"送达"；
- 执行存活（VO37–VO42）需真实挂起进程与进程组观测；默认是"发 check"而非"到点杀"，不接受只靠脚本里的 `timeout`；
- 组合与系统级（多会话、并发、故障恢复、规模）另立用例，不在本表内。

**未通过项不得计入通过**；失败修复须保留原记录并重跑（AGENTS.md）。


---

# 12. 路线图
> 来源：design/backlog.md 原文（B02–B21）

# 待落地想法与工作项登记（backlog）

地位：跨阶段的**想法/事项登记簿**，不是验收证据、不是门禁、不声称任何能力通过。
用途：用户想法与散落的"下一步"有唯一落点；每条给出与既有决定/合同的关系、下一步动作与需要的证据门槛。
不重复既有登记：未知项见 [unknowns.md](unknowns.md)（Q01–Q15）；X 组件未决项见 [g3/x/pending-items-2026-09-16.md](g3/x/pending-items-2026-09-16.md)；已验证/失败/未运行范围见 [../docs/validation-status.md](../docs/validation-status.md)；阶段门槛见 [../GOAL.md](../GOAL.md)。
状态词：`IDEA`（只有想法）｜`PENDING`（已登记待做，前提满足）｜`ADJUDICATE`（需用户/独立复核裁决）｜`DOING`｜`DONE`（附证据引用）｜`REJECTED`（附理由）。**DONE 必须指到证据，不能只写完成。**

| ID | 想法 / 事项 | 来源 | 状态 | 下一步 | 依赖 / 证据门槛 |
|---|---|---|---|---|---|
| B01 | **沙箱服务化 + 本地地址验证**：X 执行后端以本地服务形态提供，调用经本地地址（loopback）而非 in-process/unix socket；用同一套契约用例跨 transport 复跑，证明接缝没有绑定 Docker/本机文件系统 | 用户 2026-09-16 | IDEA | 出接缝扩展记录（在 [g3/x/backend-seam.md](g3/x/backend-seam.md) 上续写）：endpoint 类型抽象、wire = §2 方法集、profile 归属；解 `engine.py` 的 `unix://` 硬校验；本地服务启动/监管与预算会计；用例跨 transport 等价 + 非 loopback 拒绝 | 同一批 X 用例在两种 transport 下产出**同一组合同事实**（stopped proof、checkpoint manifest、幂等/UNKNOWN 语义）；请求只收授权引用不收宿主路径；模型/工作不可达服务 |
| B02 | 工作目录 D1：目录 = 工作侧 T0 落盘层 + 每工作设施根，host 共享机制留目录外 | [g3/work-directory-landing.md](g3/work-directory-landing.md) §12 U1 | ADJUDICATE | 用户裁决后收敛 v2 件 | 裁决记录；后续实现与用例 |
| B03 | 三分区与 glossary T0 修订（T0 = 接续区 ∪ 观测原件；接续集 = 接续区） | 同上 U2 | ADJUDICATE | 裁决后改 glossary 并注明沿革 | 独立复核；不动墓碑词 |
| B04 | content revision 机制：F `capture`（versions.git + archive/manifest）为主，worktree git 为 conventions 选项 | 同上 U3 | ADJUDICATE | 裁决后写入 v2 件 §12.1 | 与 F 合同/已有 oracle 一致 |
| B05 | R 控制库归属：工作侧运行账本随目录 / host 侧登记·授权·跨工作关系索引留 host（拆分） | 同上 U4 | ADJUDICATE | 裁决后拟 R 合同修订 | 拆分不得削弱授权边界；需 R 用例 |
| B06 | 可移植性措辞与外部 Userspace 迁移责任 | 同上 U5 | ADJUDICATE | 写进 v2 件 | 与 v5:38 / G1:25 对齐 |
| B07 | 事件导出时机：默认每 Round；每 Step 为 conventions 选项；导出接口形态（复用 runtime 读端 vs E 窄接口） | 同上 U6 | ADJUDICATE | 裁决后定接口 | 需 E/runtime 侧用例 |
| B08 | M06 ARCHIVE 对齐 + 自有批次重跑（运行包络已对齐，M06 未同步） | g3/x/pending-items 2026-09-16 | PENDING | 对齐后重跑 M06 套件 | 自有批次证据；不许以旧批次顶替 |
| B09 | M02 原始证据未随环境迁移：重建 M02 证据或正式标注历史证据失效 | 同上（验收发现） | PENDING | 二选一并落 [../docs/validation-status.md](../docs/validation-status.md) | 原始证据可复核，或明确降级 |
| B10 | 工具链：virtiofs 陈旧缓存导致新旧混合文件，编辑后容器侧核验惯例未机制化 | 同上（未决 6） | PENDING | 固化为协议（sleep+grep/ast 核验）并留反例 | 反例可复现；协议可机械执行 |
| B11 | 工作目录的拓展机制：`harness/tools/`、`harness/budget/` 是否入选标准点；manifest 事件声明 schema 已定语义（§4.5），剩余正式字段与 runtime 解析实现 | 用户 2026-09-16；[g3/work-directory-landing.md](g3/work-directory-landing.md) §4.1、§4.5 | PENDING | 进组件合同；配 VD13/VD14/VE06 用例 | 新增拓展点不改 runtime；未知条目保真；声明但 digest 不符须拒 |
| B12 | **示例能力与示例 harness 充分性**：goal / plan / work 委派 / archive（上下文控制）都必须只用通用原语 P1–P8 与"五件套"（词表+产生者+触发+投影+逻辑）表达；若必须新增框架目录，则补通用原语而非领域目录。**V-A 已裁决（2026-09-16，用户）：状态权威在事件（§4.4）** | 用户 2026-09-16；[g3/work-directory-landing.md](g3/work-directory-landing.md) §4.3–4.6 | PENDING | 定保留前缀命名空间申请机制；配 VE01–VE08 用例 | 无通用终态（v5:161,208）；完成声明≠业务验收；归档只缩视图不删依据（v5:252）；委派不继承授权 |
| B13 | **harness 示例集（一能力一文件）**：[g3/harness-catalog/](g3/harness-catalog/) 已写 goal / plan / archive / ask-user / coding / research / delegation / monitoring；用"能否只用通用原语定义"检验框架。**宁缺毋滥：缺口只登记，不提前加目录/字段** | 用户 2026-09-16 提议 | PENDING | 按需续写待写清单中的一个；缺口回补走独立评审 | 每文件只用一个通用原语缺口回补；不得把领域概念写进框架 |
| B14 | **示例集暴露的通用原语缺口（宁缺毋滥，先登记不设计）**：① 规范观测目录 `sys.*`（archive）② 对外通知/投递（ask-user）③ 模型辅助召回契约（research）④ 跨工作授权查询语义（delegation）⑤ 定时/时钟观测与等待责任（monitoring）⑥ **条件受理（base_rev 比较交换）**⑦ **冻结与修订**⑧ **依赖/失效传播**（后三项来自 system-design，plan/delegation 也会用到）⑨ **harness 声明的长驻会话组件（session-runner）**⑩ **流式观测通道（分片+引用）**⑪ **媒体 artifact 通用化**⑫ **工作空间变更观测**（⑨–⑫ 来自 voice-assistant）⑬ **工具存活检查与明确结果**（默认到点发 `sys.tool.check` 而非硬杀；harness 决策、runtime 资源安全网；`ok/failed/timeout/unknown` 四分类与 `abandoned`；[g3/voice-assistant/execution-timeouts.md](g3/voice-assistant/execution-timeouts.md)） | [g3/harness-catalog/](g3/harness-catalog/) 各文件"框架缺口"节 | IDEA | 等更多示例出现再判断是否收敛为原语；每个缺口先要一条反例 | 只补通用原语，不加领域目录；补前先有失败/受限证据 |
| B15 | **工作目录 runtime M1 已落地**（用户 2026-09-16 授权"先 runtime 再 harness"）：`lore_work/`（基础树/manifest 声明解析/facts/head/ledger/触发器水位/Round→投影→模型→工具→提交，harness 只读硬校验）+ `lore_harness/goal/`；真实验证 ark `glm-5.3-flash` 三次运行，独立校验器 003 全绿；两个反例（无进展循环、重复完成）已修复并留证 | [validation/work_runtime/FINDINGS-2026-09-16.md](../validation/work_runtime/FINDINGS-2026-09-16.md) | DOING | 继续：runtime 加固（崩溃/幂等/多轮）→ 其余 harness（plan/archive/ask-user/coding/research/delegation/monitoring/system-design）→ 独立复跑 | 证据在 `validation/work_runtime/evidence/`（gitignore）；未经独立验收，不声称组件通过 |
| B16 | **助手 work 设计**（用户 2026-09-17，含三项裁决）：**一个助手 = 一个长期 work**（会话是 work 内 `session` 区间，`session.ended` ≠ work 完成）；**语音只属于助手 harness**（端口/适配器/会话编排在 `harness/ext/voice/`，不新增框架设施）；**落在工作目录**（[g3/voice-assistant/assistant-work.md](g3/voice-assistant/assistant-work.md) 给出目录解剖与会话事件流）。含风格预设与"回答重点"口语化渲染、全双工（barge-in/轮次检测，复用开源编排）、Ark `glm-5.3-flash` / 豆包 ASR/TTS 2.0 适配规范（含实测协议观测）。设计资产：[design/g3/voice-assistant/](g3/voice-assistant/README.md)、[latency-and-curation.md](g3/voice-assistant/latency-and-curation.md)（及时响应 vs 知识维护：两个策略实例、延迟预算、工作空间认知、维护时机）、[events.md](g3/voice-assistant/events.md)（词表：产生者/触发/幂等键/最小闭环）、[conversation-record.md](g3/voice-assistant/conversation-record.md)（对话记录：目录化原始音频+元数据、端点切片、分析扩展位）、[scheduling.md](g3/voice-assistant/scheduling.md)（日程归助手、机制归 runtime；**复用标准 crontab + 事件定义**，不自定义/不重实现；两条纪律：权威在工作数据、cron 只叫醒不写事实；`adapter.error` 归 harness）、[execution-timeouts.md](g3/voice-assistant/execution-timeouts.md)（执行存活：**默认到点发 `sys.tool.check`、不自动杀**；怎么办归 harness；runtime 保留硬上限与资源安全网，回收即 `abandoned/unknown`；不做逐次提醒；in-band `timeout` 只是纵深）、[harness-catalog/voice-assistant.md](g3/harness-catalog/voice-assistant.md) | 用户 2026-09-17；[g3/voice-assistant/providers.md](g3/voice-assistant/providers.md) 实测 | PENDING | ① 框架定版（调研已完成：主选 LiveKit Agents 1.8.2 / 备选 Pipecat 1.10.0；须裁决 plan 鉴权差距与许可）② session-runner 通用机制的口径确认 ③ 对话记录落地（事件权威 `voice.segment.sealed` + 目录物化；定 `record_schema_version` 与 `retention_class`）④ **runtime 调度机制**（标准 crontab + 事件定义 → `sys.schedule.fired`；默认 runtime 内建循环 + 成熟解析库，宿主调度器仅作"不常驻"备选；迟到补齐；+ `sys.clock` 谓词式时间；多 harness 共用）⑤ **执行存活检查**（`sys.tool.started/check/finished/abandoned`；默认发 check 不自动杀；结果四分类 `ok/failed/timeout/unknown`；资源上限回收即 unknown；[execution-timeouts.md](g3/voice-assistant/execution-timeouts.md)）⑥ 端口契约 + `fake` 适配器 + 一致性套件 ⑦ doubao/ark 适配器 ⑧ 双工组合与打断 ⑨ 冷/热两循环与工作空间认知 ⑩ 独立验收（VO01–VO42） | 需先补通用原语：session-runner、runtime 调度、工具存活检查与明确结果、空闲观测、对外投递、流式观测通道、媒体 artifact 通用化、工作空间变更观测；换模型须有共用判据而非"两个都能跑"；密钥不落库；框架许可与供应链须审计 |

| B17 | **验收后遗留（不改进已验收版本，保持"被验=交付"）**：孤立代理项（lone surrogate）payload 让轮以 `UnicodeEncodeError` traceback 中止（可 `recover`，非弄砖）；应改为写入前的类型化拒绝（"payload 不是合法 UTF-8"） | 验收 A 收尾（[RECORD](../validation/work_runtime/acceptance/RECORD-2026-09-16.md) 边界 7） | PENDING | 在 `facts.append_fact`/`ledger.append_jsonl` 编码前捕获并抛 `ValueError` | 改后须重走一轮独立复验才能计入通过 |
| B18 | **并发/单写者租约**：并发 `recover` 无串行化（8 次冒烟中 1 次出现两个 abort 行，无事实丢失）；契约本就列明的缺口 | 验收 A R4 | IDEA | 先定义租约语义（持有者、崩溃回收），再实现 + 预注册用例 | 不得以冒烟代替证明；需真实并发用例 |
| B19 | **工具执行"30s 硬杀"→"check 先行"**：已按修订实施（2026-09-17）：默认发 `sys.tool.check`（只观测不杀，退避 ×2 封顶 60s）、`budget_ms` 策略预算到点整进程组终止（结果 `timeout`）、runtime 硬上限回收即 `unknown`+`sys.tool.abandoned`、`outcome` 权威/`exit` 兼容镜像；`tool_timeout` 参数移除 | 用户 2026-09-17 裁决；[amendment-task-tool-liveness-2026-09-17.md](g3/amendment-task-tool-liveness-2026-09-17.md)；[execution-timeouts.md](g3/voice-assistant/execution-timeouts.md) | DOING | 独立验收者复跑 VO37–VO42（`offline_tool_liveness.py` 已全绿）+ 既有套件 | 实现者自跑不算独立复跑；旧证据不迁移（旧行为绑定旧版本）；`exit 126`/`exit 0` 语义已保持 |
| B20 | **harness 共享基座已落地（2026-09-17）**：`lore_harness_base.py`（框架随版本标准库：action_protocol/parse_action/final_fallback、fold/facts_since、continue_when/start_unless_completed、make_accept、content_files/budget_lines/tool_history_lines/rejected_final_lines、file_digest/load_config）+ 十个 harness 全部迁移 + runtime 兜底投影/解析改用同源；域语义（kind 含义、payload 索引、规则文本、拒绝条件）留在各 harness；派生路径写入 harness-catalog README | harness 盘点（2026-09-17，13 项证据） | DOING | 独立验收者复跑全部离线用例 + 校验器（实现者自跑已全绿：12 用例 + VO37–42 + verify_goal_task e2e） | 迁移不改变判据；基座不进 harness digest；依赖=注册时 runtime 版本的既有依赖 |
| B21 | **落盘行形状与 landing §5 对齐 + 机制缺口**：facts 行缺 namespace/received_at/foreign_id（landing:420）、head 缺 revision_ref/segment 形态（landing:419）、admission 行缺 source/at（landing:424）、rounds 行缺 trigger_eval/attempts[]/Grant 快照/计量（landing:425）；wants/grants 无 grant generation（landing:487）；生命周期后半段（quiesce/archive/export/import/delete）无 CLI 入口；Attempt 概念未落地 | [work-directory-landing.md](g3/work-directory-landing.md) §5/§9-3；盘点（2026-09-17） | IDEA | 进组件合同时统一改行 schema（连带 digest/恢复/校验器整体设计），不逐条零散改 | 行形状变更=兼容性断裂，须整体设计+迁移方案+复跑；不与术语/对齐重构混做 |

## 想法池（无编号草稿）

新想法先记一行，够清楚再给 ID 与门槛。

| 想法 | 提出 | 备注 |
|---|---|---|
| （待补） | | |


---

# 13. 待裁决问题清单（评审重点）
> 来源：汇总自 landing §12、contract 修订记录、backlog；原文见第 5/6/12 章

以下均有登记、未擅自定死。原文引用见第 5 章（landing §12）；此处为汇总视图。

## 13.1 根本级（landing §12.2，阻塞形态定版）
- **U1（核心）D1 双层落盘模型**：目录 = 工作侧 T0 落盘层 + 每工作设施根，host 共享机制保留在目录外——"目录与既有设施关系"的根决策。
- **U2 D3 三分区与 glossary T0 修订**：Session/观测原件现无层级可归；候选 `T0 = A ∪ B，接续集 = A` 或新增 `T0o`。
- **U3 D2 content revision 机制**：已验的 F `capture`（versions.git + archive/manifest）为主 vs worktree git 作 conventions 选项。
- **U4 R 控制库归属**：每工作 `ledger/control.sqlite` vs host 共享库 + namespace 过滤；作者建议拆分（工作侧运行账本随目录、host 侧登记/授权/关系索引留 host），但这要动 R 合同。
- **U5 可移植性**：外部 Userspace 按引用版本另行迁移或显式拒绝。
- **U6 事件导出时机**：默认每 Round 一次范围导出；每 Step 为 conventions 选项。

## 13.2 机制级
- **grants 同词异义**：`relations.grants`（发送侧授权，landing §9-3 用的名字）与 glossary Round Grant 撞名；Round Grant 尚无实现物。改 glossary 还是改名，待裁决。
- **标准拓展点**：`harness/tools/`、`harness/budget/` 是否入选标准点，还是并入 `logic/`+`rounds/`（landing §4.1 对齐表；backlog B11）。
- **落盘行形状对齐**（backlog B21）：attempts / grant_snapshot / grant generation / 生命周期命令——涉及 digest、恢复、校验器联动，建议单独设计。
- **事件导出接口形态**：既有 runtime 读端循环 vs E 增窄 `export_range`（要动 E 合同与用例）。
- **host 登记/索引可重建性**：能否仅靠扫描 works-root 重建"在册"；跨工作 grants 权威是否只在 host。
- **观测区保留期数值**：待测量，不预设 SLA。
- **views/presentation 可选标准点的字段形态**：从轻，不定义视图类型学（landing §4.7）。
- **P1–P8 充分性**：以"示例只用通用点即可表达"检验；voice-assistant 缺口清单是最大压力源。

## 13.3 已取 M1 取舍、记录在案可复议（contract 修订记录 D1–D7）
- U26：`sys.tool.check` 频率数值（默认 10s / 封顶 60s）待测。
- U27：runtime 硬上限配置来源（X budget maxima vs `work.json.policy`）未定。
- U28：`sys.tool.finished` 并入 `sys.tool.result`（outcome/side_effects/duration_ms/call_id）。
- U30：check 落面事实（频率影响待测量后复议）。
- 死字段移除、provider 文档更正等杂项见修订记录第 6 条。

## 13.4 B16 框架定版
- 实时语音框架：主选 LiveKit Agents 1.8.2 / 备选 Pipecat 1.10.0；plan 鉴权差距与许可待审（voice-assistant/research-notes.md）。

---

# 14. 实现状态快照与历史层边界
> 来源：实现者撰写；与第 6 章契约互为对照

## 14.1 M1 已落地（与第 6 章契约对照）
- **`lore_work/`（runtime，~1500 行）**：layout（目录骨架 + manifest digest 盖章）、manifest（严格 digest 校验）、facts/head/ledger（append-only、单写者、head 唯一提交、受理幂等 foreign_id）、触发水位、Round 执行（投影→模型→工具→提交；单 JSON 动作协议）、工具存活三参数制、admit/relay（跨工作受理）、recover（崩溃隔离）、faux provider（离线验证）。
- **`lore_harness/` 十示例**：goal / plan / archive / ask_user / coding / research / delegation_parent / delegation_child / monitoring / system_design——全部基于共享基座；archive/delegation_parent/research/system_design 不吃 final（Round 只随进展结束）。
- **`lore_harness_base.py`**：第 7 章全文；框架随版本提供的标准库，不进 harness digest。

## 14.2 验证状态（全部为**实现者自跑**；独立复跑未做，组件不声称"通过"）
- 12 个离线用例（faux provider，无网络无凭据）+ VO37–42（工具存活判据，预登记）+ `verify_goal_work.py` 端到端独立校验器（不 import runtime，只重算盘上字节）。
- 真实模型验证：Ark `glm-5.3-flash` 三次运行（B15 期），证据在 gitignore 的 `validation/work_runtime/evidence/`。
- 判据未放宽；唯一断言文本随 relay 更名更新且理由记录在用例内。

## 14.3 未做清单（缺口，非缺陷）
沙箱隔离（X）/ 租约 / 调度 crontab / 对外投递 / 流式观测 / 媒体 artifact / host 登记/索引 / B21 行形状 / landing §13 用例执行 / voice-assistant 全部 / 独立验收。

## 14.4 历史层（不是当前设计）
`harness-runtime-revised-v5.md`（v5 系统设计，锁定，墓碑多处引用其行号）；G3/G4 期组件记录已于 2026-09-17 整批归档至 **design/archive/**（E/F/R/S/V/X 组件契约与用例、x-node-profile 证据链、reviews 独立评审、provider/tool-service/file-publication/session-plans、coordination.md、x-*.md、minimal-harness-extension-points.md，及 g1/g2/g4 阶段记录；布局与短码引用约定见 archive/README.md）；dated 记录（amendment-*、FINDINGS/RECORD/acceptance、docs/validation-status.md——其中冻结判据名 `task_uid` 等旧名照原样保留）。

---

# 15. 评审输出格式要求
请按以下结构输出，便于逐条回填登记：

1. **总裁定**：设计是否自洽、可作为组件合同的基线（可/有条件可/否），三句话理由。
2. **问题清单**：每条 = {章节定位, 严重度：根本级/机制级/措辞级, 问题描述, 建议处置}。按严重度排序；根本级问题必须给出反例或推导，不接受纯口味陈述。
3. **U1–U6 推荐组合**（若给）：每项一行推荐 + 理由 + 主要风险。
4. **通用原语缺口**：若判定 P1–P8 不充分，列出缺的原语、哪个示例/前瞻设计暴露了它、为什么不能靠现有原语组合表达。
5. **术语审查**：禁混表遗漏项、墓碑复活风险、命名不一致。
6. **你对设计的三个最好的问题**（我们回答后可继续对话）。

约束：不要因为"尚未实现/未验证"而扣设计分——缺口已如实登记（第 14.3）；请把火力集中在**原则性错误、推导链断裂、判据不可执行、单写者/受理的漏洞**上。