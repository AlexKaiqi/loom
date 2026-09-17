# Temporal（temporalio/temporal）调研记录 — 2026-09-16

**状态**：文档级 + 源码审查（进行中，未运行实验）。clone：`research/repos/temporal`，head=172d1b409（82MB，go 1.27.0，MIT）。用户授权背景：Loom 未决项（`pending-items-2026-09-16.md`）与其 durable execution 思想高度重合，要求判定可直接复用组件与应借鉴设计。

## 1. 架构骨架（源码核实）

四服务分层：`service/frontend`（API 网关）、`service/history`（**核心：事件溯源执行引擎**）、`service/matching`（任务队列）、`service/worker`（系统工作流容器）。持久化抽象 `common/persistence`（SQL/Cassandra/ES 可换），schema 在 `schema/sql/`。

**根本分工（对 Loom 最重要的一条）**：服务器**从不执行用户工作流代码**。确定性执行+重放活在 SDK worker（独立仓库 sdk-go / sdk-core[Rust]）；服务器职责 = 事件日志持有者 + 任务派发器 + **完成校验器**。用户代码跑出的命令序列与事件日志不匹配 → workflow task failed → 从日志重试。这就是"步边界"：**每个 workflow task 是一步，完成即持久化，下一步重新驱动；没有步内重驱**。

## 2. 与 Loom 未决项的逐项映射

| Loom 未决项 | Temporal 对应机制 | 结论 |
| --- | --- | --- |
| ① JOINT：暂停后保留回执重放失败 | `MutableStateRebuilder`（service/history/workflow/mutable_state_rebuilder.go）从事件日志确定性重建状态；服务器侧以 NextEventId/LastProcessedEventId/VersionHistories 校验（checksum.go payload） | 重建路径是一等公民（rebuilder + checksum 双保险）。Loom 的保留回执重放应向"从日志确定性重建+不变量校验"靠拢，而非只重放单条回执 |
| ② 溢出压缩空转 | 无对应——Temporal **不做原位裁剪** | 他们的答案：历史超限→`forceTerminateWorkflow`（context.go:1465-1479）或建议 continue-as-new |
| ③ 单步预算 vs 再驱动冲突 | 步边界模式：一 workflow task = 一步，完成即持久化，下一步重驱 | **直接候选答案**：Loom 的"步边界压缩"与此同构；pi 的步内再驱违背步边界，Temporal 印证其不可行 |
| ④ 真实规模溢出不可达 | 历史尺寸三档：warn 10MB / error 50MB / suggestContinueAsNew（dynamicconfig/constants.go:452-463） | 分档语义（警告/错误/建议续新）比 Loom 的 soft/hard 两档更细 |
| 后继机制 | **continue-as-new**：旧 run 结束，新 run 承接（全新历史，状态经 input 携带，run id 谱系保留） | 同构机制；Loom 已实现等价物（后继接力），可对齐其 reasons 枚举与触发协议 |

## 3. 值得借鉴的设计（已核实源码）

1. **完整性校验入持久层**：`generateMutableStateChecksum`（CRC32 over 执行不变量 payload：NextEventId、活动/信号/计时器计数、任务 id、版本谱系）随状态持久化并在读回时验证（service/history/workflow/checksum.go）。映射 Loom：S 快照/R.sqlite 的读回校验目前只有 wire 层，不变量校验（如条目计数、未决责任计数）值得加。
2. **超限行为显式分档**：warn（仅日志）→ suggest（向 worker 建议续新+理由枚举 `SuggestContinueAsNewReasons`）→ error（强制终止且记 FailureReason）。Loom 当前 soft=8192/hard=8192 重合；分档化可让"预算暂停"与"建议裁剪"解耦。
3. **重试策略结构化**：init interval/coefficient/max interval/max attempts/expiration/nonRetryableTypes + RetryState 枚举分类（common/retrypolicy、service/history/workflow/retry.go getBackoffInterval）。Loom 重试语义散落在各包，可对齐此结构。
4. **事件 schema 形态**：api/history/v1 的 HistoryEvent（attributes oneof、单调 EventId、VersionHistories 分支谱系）——lore_events 信封设计参照。
5. **CHASM**（Coordinated Heterogeneous Application State Machines，chasm/ 目录）：服务端状态机的统一库，历史服务同时跑两代引擎（chasm_engine.go + history_engine.go）——与 Loom S/R 状态机+事实归属的关注点相似，值得后续深读。

## 4. 可直接复用组件（初判，待验证）

- `common/backoff`、`common/retrypolicy`、`common/checksum`：小而纯的 Go 包。**Loom 是 Python 栈**，直接 vendoring 无意义（跨语言），倾向"借设计重实现"；license MIT 允许。
- 服务器本体（分布式系统：shard、复制、gRPC 集群）：**不可直接复用**——Loom 是本地单机证据优先运行时，引入即违背 Scale to Zero 与最小依赖目标。
- sdk-core 的重放引擎（Rust，独立仓库）：与 pi 的 loop 职责重叠，评估后置。

## 5. 后续深挖项（下一轮）

matching 服务任务队列语义（sticky execution、速率限制）、timer queue、CHASM 状态机、workflow versioning/patching、archival（history 归档 vs Loom trim 证据保留差异）、sdk-core 重放确定性执行细节。

## 6. 明确不采纳及理由

- 分布式服务器架构（多服务、shard 复制、ES visibility）：规模不匹配，违背本地最小依赖。
- 原位裁剪缺失本身：Temporal 依赖 continue-as-new 替代裁剪；Loom 的阈值压缩（归档+原来源完整可查+头尾视图）是更强的性质，M05 已验证 8/8——**不应为了像 Temporal 而放弃原位裁剪**。

## 7. 第二轮深挖（2026-09-16，官方架构文档 + 源码）

`docs/architecture/` 为官方内置架构文档（history-service.md 322 行精读）：

1. **Shard 所有权与 fencing**：历史分片数建群即固定；所有权经 ShardController（Ringpop 成员协议）协调；每分片 RangeID = 单调代数，用于**fencing**（旧持有者写入被拒）。映射 Loom：我们的租约/所有权代数（session_generation、lease_until）与其 fencing 同题，RangeID 的"代数随所有权转移递增"是成熟先例。
2. **事件充分性契约**：官方明文——"History Events 单独即足以恢复该执行的全部其他状态（Mutable State 与任务）"。这是 event sourcing 的硬承诺，`history_node`+`history_tree` 表支撑分支/reset 谱系——**与我们 journal 的分支/树形状同构**。Loom 的 pause 后恢复若做不到"仅凭 journal 重建"，就是与该契约的差距（JOINT 重放失败的根源视角）。
3. **状态转换统一路径**：四类输入（用户 RPC / worker RPC / timer 到期 / 外部工作流信号）走同一代码路径（GetAndUpdateWorkflowWithNew → UpdateWorkflowExecutionAsActive）；每次转换 = 原子事务{新状态+任务} + 事件追加。映射 Loom：R 的 _advance 多入口应收敛到统一转换函数。
4. **脏状态失败的恢复动作**：Mutable State 持有"最新已反映事件"的身份（checkpoint 等价物）；持久化失败 → **从持久层重载重建**，不猜测。这正是 Loom 未决项①应采纳的行为模板（失败即重建而非重放单条回执）。
5. **Transactional Outbox 模式**：任务与状态同事务落库，队列处理器保证最终派发（microservices.io 命名的经典模式）。映射 Loom：R/S 确认泵的同题先例，值得在文档中显式引用该模式名。
6. **effect 包诚实定位**：`effect.Buffer` 只是延迟回调累积器（Apply/Cancel），官方明文**不提供事务保证**（回调可部分应用）——不可与我们的效果预算/门语义混淆；借鉴点仅在"成功才应用、失败逆序取消"的结构。
7. **Mutable State 的持久化哲学**：可由事件重算但仍持久化摘要（重放太慢）+ 读回 checksum 验证 + 内存缓存。Loom 的 R.sqlite/S 快照同构；checksum 不变量清单（计数类、id 类、谱系）可直接对照设计。

**对 Loom 未决项①（JOINT 重放失败）的中期判定**：Temporal 的答案不是"更聪明的重放"，而是 (a) 事件充分性 + (b) 失败即从日志重建 + (c) 不变量 checksum 校验。Loom 修 JOINT 时应检查：暂停后继续的路径是否满足 (a)（journal 是否充分），并把 (b)(c) 作为修复方向，而非在重放点打补丁。

**后续**（第三轮起）：matching 服务 sticky execution 与速率限制、timer queue 实现、CHASM 组件树/task/transition 细读、workflow versioning、archival 对照、sdk-core（独立仓库）重放执行器评估。

## 8. 第三轮深挖（speculative/update/matching/CHASM/archival）

1. **Transient Workflow Task**（speculative-workflow-task.md）：任务失败重试时 Scheduled/Started 事件**不写入历史**（attempt 计数只在 mutable state），成功才补写——日志不被失败尝试污染。**与 Loom 证据优先有张力**：我们的暂停/失败记录是必须保留的证据（m01 'ak'/'an' 反例、M05 预算暂停证据）。借鉴边界：仅当失败记录是冗余副本（同一事实已在 R.sqlite）时才考虑，journal 本身保持完整失败记录。
2. **Speculative Workflow Task**：零数据库写的乐观任务（类比 CPU 投机执行），失败即弃，仅用于 Workflow Update 拒绝场景；配套 in-memory timer queue。文档诚实记录了一个已知 bug（sticky 缓存逐出后 speculative 事件缺失 → premature end of stream）——诚实文档的先例。
3. **Workflow Update 的"拒绝零痕迹"哲学**：rejected update 不写任何事件（请求在内存直到 accepted）。**判定**：Temporal 的 history = 面向用户的逻辑事件流（审计在 visibility/ES 层），Loom 的 journal = 证据/审计本体——两者角色不同，不可直接套用；但 update 的 admitted→accepted→completed 状态机与 registry 生命周期值得对照 Loom 的 continuation/decision 状态机。
4. **Matching 服务**（文档较薄）：长轮询、任务队列分区树（默认 4 分区、父子转发、空分区转发给 poller）、backlog 可加载/卸载。属规模化机器，Loom 本地运行时不需要；任务队列代码细节在 backlog_manager.go/matcher/，按需后查。
5. **CHASM（精读 docs/architecture/chasm.md 全文 373 行）**：Workflow 只是众多 ASM 之一。核心概念对 Loom 的映射：
   - **ExecutionKey 身份分离**：BusinessID（跨 reset 持久）+ RunID（reset/续新时变更）——**正是 Loom"裁剪不破坏原 ID/未决责任"的成熟答案**：业务身份稳定，运行身份可换代。
   - **ComponentRef 双 VT 校验**：回调（= 我们的工具回执！）携带 initialVT（防同路径删除重建错位）+ lastUpdateVT（防过期回调），引擎在应用前核验两个值，不匹配即确定性拒绝——**未决项①（JOINT 陈旧回执重放失败）的答案模式**：回执携带发行时的（代数，迁移计数），重放时核验而非"重新 normalize"。
   - **Pure Task vs Side Effect Task**：pure 在事务内运行（可读写状态，同事务继续）；side effect 在提交后异步运行（可调外部，改状态必须走外部 API）。Validator+Executor 双方法（validator 丢弃已被取代的任务）。**映射未决项③**：压缩再驱动可作为 Pure Task（同事务步内继续）合法化，而"1 provider/drive"预算语义归属 Side Effect Task 类。
   - **VersionedTransition 逻辑时钟**：FailoverVersion+TransitionCount 全序——我们的 journal serial/generation 应对齐此全序设计。
   - **字段粒度原则**：变更频率/大小/读取模式不同的数据分字段存储（各自成 node）——事实归属的成熟先例。
   - **任务=outbox**：任务与状态同事务写（再次引用 Transactional Outbox）。
6. **Archival**：仅薄上传服务（service/history/archival/archiver.go，历史归档到 blob storage），非原位裁剪——再次印证 Temporal 无原位裁剪能力。
7. **Versioning**：worker versioning（build-id 路由）在服务端；workflow patching 在 SDK 侧。服务端不做工作流状态 schema 演进。

**下一轮**：sdk-core 重放引擎（克隆中）评估、与 pi loop 的对照、可行性汇总（借鉴项优先级落位）。

## 9. sdk-core 重放引擎（第四轮，Rust，crates/sdk-core）

- **架构分层**（ARCHITECTURE.md）：Core（Rust）轮询任务、驱动状态机库、产出 WorkflowActivation（激活 job）给语言层；语言层跑用户代码，回传 WorkflowCommand。术语链：HistoryEvent → StateMachine（TemporalStateMachine trait）→ MachineResponse → ActivationJob → 用户命令。
- **确定性执行点**（machines/mod.rs:120-150）：每个命令必须在其状态机上产生合法迁移；非法迁移 → `nondeterminism!("Unexpected command...")` → TMPRL1100 致命错误 → workflow task 失败。**确定性校验=状态机迁移合法性**，不是逐字节比对。
- **含义（对 Loom）**：pi 的 loop + 我们 harness 钩子的"确定性"同样应表述为状态机迁移合法性（M05 的钩子压缩事实、m01 的预算不变量都是迁移规则）；重放校验的目标是"迁移合法"而非"输出一致"。

## 10. 综合判定：借鉴项优先级落位（对照 adoption-assessment 惯例 A/B/C/D）

**A 立即（映射未决项，修复方向已明确）**
1. **ComponentRef 双 VT 校验模式** → 未决项①（JOINT）：工具回执携带发行时（执行代数，迁移计数）；重放核验两值，不匹配确定性拒绝——替代"重新 normalize 单条回执"的现行失败路径。
2. **失败即从日志重建 + 事件充分性契约** → 未决项①：暂停后恢复路径必须满足"仅凭 journal 可重建"，重建失败=证据缺口要修，而非重放点打补丁。
3. **Pure/Side-Effect Task 二分** → 未决项③：压缩再驱动可作为同事务步内继续（pure）合法化；"1 provider/drive"预算语义归属 side-effect 类。溢出压缩空转（未决项②）同路径解决。

**B 近期（设计与配置）**
4. **ExecutionKey 身份分离**（BusinessID 跨代持久 + RunID 换代）→ M05-JOINT 的原 ID/未决责任检查项语义对齐。
5. **Mutable state checksum 不变量清单**（计数/id/谱系）→ S 快照与 R.sqlite 读回校验增强（CORRUPT 类判据扩展）。
6. **超限三档分档**（warn/suggest/error）→ Loom soft/hard 阈值解耦：8192 软压力/阈值触发/硬终止三档各司其职。
7. **VersionedTransition 逻辑时钟**（FailoverVersion+TransitionCount 全序）→ journal serial/generation 全序对齐。

**C 后置（登记防遗失）**
8. 重试策略结构（RetryState 枚举+nonRetryableTypes）→ Loom 重试语义结构化。
9. 事件 schema 形态（attributes oneof、history_node/history_tree 分支谱系）→ lore_events 信封演进参照。
10. CHASM 自包含 ASM 包布局与字段粒度原则 → 事实归属审查指南条目。
11. 诚实文档先例（speculative 文档记录已知 bug 的写法）→ 验证状态页可效仿。

**D 明确不采纳及理由**
- **分布式服务器本体**（多服务/shard 复制/ES visibility/分区树）：规模与依赖目标不匹配；Loom 本地单机证据优先，引入即违背最小依赖与 Scale to Zero。
- **代码级复用**：Go/Rust 包与 Python 栈跨语言，common/backoff 等小包借设计重实现成本更低；**无直接 vendoring 组件**（诚实结论：复用=设计级，非代码级）。
- **Transient/Speculative 的失败零痕迹**：违背证据优先（失败记录是判据本体）。
- **continue-as-new 替代原位裁剪**：Loom 阈值压缩是更强性质（M05 8/8 已验证），不回退。
- **effect 包**：仅回调缓冲器，官方明文无事务保证，语义易混淆，仅借"成功才应用/失败逆序取消"结构。

## 11. 调研完备性声明

已覆盖：服务器四服务架构、事件溯源+充分性契约、MutableState/Rebuilder/checksum、workflow task 循环（normal/transient/speculative）、continue-as-new、历史尺寸分档与强制终止、matching（文档级）、CHASM（全文档精读+关键源码）、workflow update 状态机、archival/versioning 定位、retry 策略、sdk-core 重放引擎与确定性执行点。**未运行实验**（文档级+源码审查）；运行实验（如本地起 Temporal 验证 continue-as-new 行为）后置且需另行授权预算。sdk-core 克隆于 research/repos/sdk-core（main head 2026-09-16）。

## 12. 更正与澄清（2026-09-16，用户指正后）

**更正一（D 级理由框架错误）**：§10 D-1 原理由写为"分布式服务器本体与本地单机证据优先运行时的规模/依赖目标不匹配"——用户指正：**单机不是目的**，也不希望限制单机只能启动一个 Loom 服务；真实意图是"规模化暂不花过多精力"，而非"架构目标是单机"。本更正不覆盖原文，仅声明 D-1 的理由作废，改为：**分布式服务器本体 = 暂缓（登记为规模化路线图），非不采纳**。D 级其余各项（失败零痕迹、continue-as-new 替代原位裁剪）理由为证据优先性质冲突，维持不变。

**多实例现状核对（依据本会话证据，非臆断）**：现有架构已是多进程（S session service 独立进程、NATS 解耦、R 驱动）；所有权机制已有（session_generation、lease_until 租约，与 Temporal RangeID fencing 同构）。缺的是规模化层：所有权分配（谁的执行归谁）、端点/端口分配、状态卷隔离、namespace 多租户——**现状不是"绑定单实例"，而是"规模化层未建"**，Temporal 恰是该层建成后的参照实现。

**澄清二（"重新发明核心"的准确含义——四个层次拆开）**：

| 层次 | 与 Temporal 的关系 | 结论 |
| --- | --- | --- |
| 问题/不变量层 | **相同** | 推进责任不依赖活进程、日志=唯一真相、确定性重建、步边界效果、身份跨代续存——双方独立得到同一组不变量 |
| 机制层 | **大量可借鉴，且多数与规模化无关** | 双 VT 校验、失败即重建+事件充分性、pure/side-effect 二分、checksum 不变量、身份分离、三档分档、VersionedTransition 全序——这些是**任何 event-sourced 系统都要的机制**，不是"分布式才要的机制"，现在单进程就能用 |
| 代码层 | **不可直接复用** | Go/Rust 包 vs Python 栈跨语言；服务器本体是另一系统；无 vendoring 组件（§4 维持） |
| 平台层（规模化） | **暂缓，非不采纳** | shard/fencing/outbox/分区队列/visibility 是未来需要时的现成路线图；届时借设计或评估部署，而非现在自研 |

**修正后的总判定**：调研价值 = 机制层（现在就修未决项①②③）+ 平台层路线图（规模化时启用）。"重新发明"的准确表述：**我们在同一块地基上盖了不同的楼**（他们为业务流程连续性，我们为证据链与未决责任），而他们的施工图对两者都有用。
