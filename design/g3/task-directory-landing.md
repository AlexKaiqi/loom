# 任务目录：落盘机制与设施归属（v2 补全草案）

地位：[task-directory.md](task-directory.md)（v1，2026-09-16 对话裁决定稿）的补全件——v1 定了框架（框架固定/内容自由、目录树、写者归属、拓展点映射、git 边界、T2 外置），本件补它没有回答的另一半：**目录与既有组件设施（R/E/F/S/X）的关系、持久分区、逐文件规范、原子性、生命周期、权限矩阵、五个机制题的裁决，以及可机检不变量与预登记用例**。
状态：**DRAFT，无实现、无验证证据**；全部为设计判断或候选工程决策，不表示任何性质通过。v1 已裁决的框架原则不改；凡本稿修订 v1 处，集中在 §12 列出以待裁决，不静默覆盖。

来源与权威次序（冲突时按此排序，不按文档新旧）：v5 目标与不变量 → G1 顶层合同 → glossary v3.2 概念 → 各组件 G3 合同 → v1 任务目录框架。本件属最后一层的机制细化，**其中固定下来的目录名/文件名是 G3 组件级选择，可经修订更改，不上升为 v5 级不变量**（v5:349 明确目录名、每步 Git 提交等不冻结；v5:343 目录布局本身即待验证选择）。

### 0.1 硬约束 vs 候选（2026-09-16 用户："不要过早限制，宁缺毋滥"）

| 类别 | 内容 |
|---|---|
| **硬**（改变即改目标/语义） | L0 必需骨架与缺失语义（§4.1）；事件是唯一推进与接入契约 E1–E5（§4.4）；事件为状态权威（§4.4）；保留名与命名空间原则（§4.5）；不变量 I1–I8（§11）；"能力只用通用原语表达，缺则补原语而非领域目录"（§4.3） |
| **候选**（宁缺毋滥，等证据/实现再定） | L1 标准点清单（`conventions/projection/organization/rounds/admission/logic` 之外是否加 `tools/budget/views/presentation`）；manifest 的字段名与层级（§4.5 仅示意）；`views` 的 `source`/`resolver` 取值空间（§4.7）；具体设施落点（§2）；`surface/facts/` 分片命名（§9-1）；revision 机制 D2（§9-2） |

**佐证方式**：不靠争论，靠 [harness-catalog/](harness-catalog/)——每个文件讨论一种 harness 如何只用通用原语定义；定义不出来的地方，就是通用原语缺口，回补原语、**不加领域目录**。其中 [system-design.md](harness-catalog/system-design.md)（自顶向下系统设计）是 Surface 模型的最强验证：**有界投影 + 冻结/修订 + 条件受理**直接对应"模型不局部改、整体重写导致面目全非、收敛不到最终设计"这一实际病。

---

## 1. 事实基线：今天不存在 task-root

经源码核对（只读盘点，未改动）：

- 运行时的根是**分别配置**的：`bootstrap.assemble` 要求 `runtime{control_db, files_dir, execution_dir, session_dir, engine_endpoint, nats_url, authority, worker_id, event_profile}`、`startup_root`、`provider` 等，`Runtime.__init__` 再逐项复核路径与所有者根一致（`lore_runtime/bootstrap.py:59-95`，`lore_runtime/runtime.py:27-36`）。
- 实际落盘以 `sha256(具体 id)` 为键，**没有任何 `task_id` 或任务根**：R 控制库（`lore_control/storage.py:8,24-33`，登记含 realpath/dev/ino，`lore_control/registration.py:22,34`）、E 的 NATS stream `<prefix><ns>`（`lore_events/service.py:41-63`）与输入发布 `<input_root>/<sha256(invocation)>/{events.jsonl,invocation.json,execution-targets.json,manifest.json}`（`lore_events/input_files.py:7,18-30`）及 `.puback` 回执（`lore_events/receipts.py:9`）、S 快照库 `confirm-<sha256(request_id)>/…`（`lore_session/snapshots.py:99-119`）、X 执行库 `sha256(execution_id)/record.json`+blobs 与 `.slots/`、`.owner-lock`（`lore_execution/journal.py:47-100`、`slots.py:84-115`）、F `versions.git`+`artifacts/<sha256(ref)>/`（`lore_files/versions.py:14-60`）、provider wire `<sha256(effect_id)>/`（`lore_session/provider.py:111-129`）、plan 投影（`lore_runtime/session_plan_files.py:48-129`）。
- 只有 `startup_root` 已长得像任务根（`artifacts/ plans/ authority/ X-state/ E-inputs/`，`lore_runtime/startup_assets.py:42-46`）；NATS、Docker、控制库、F/S/provider 根、共享依赖卷是**有意 host 全局**的。
- 存在可复用的先例：验证驱动已把 R/F/S/provider 根放进同一个 `out/`，把 X-state/plans 放进 `host/`（`validation/system/m01_run.py:100-103`）——"每任务设施根"已被实际跑过，只是没被命名为任务目录。
- S 侧的**持久屏障已设计**：X 暂停 namespace → 导出同 exec/generation 的 Session manifest 与精确字节 → 校验后**外部持久化** → resume（`design/g3/s/contract.md:29,41`）。这条"外部持久化"至今没有指定落点；任务目录正是它的落点。

结论：v1 的目录树不是今天磁盘上已经成立的事实，而是一个**尚未接线的新分组**。补全件必须先回答"目录里的字节从哪来、和活设施谁是权威"。

---

## 2. 双层落盘模型（建议 D1）

**活层（live）**：设施持有的工作权威——E 持事件字节与顺序，R 持控制关系，S 持会话原件，F 持版本归档，X 持执行原件，provider 持传输原件。可以是 host 全局的、常驻的。
**落盘层（landing）**：任务目录内、与活层 manifest/digest **逐字节绑定**的副本或引用，对模型只读。
**T2 外部**：沙箱实例、轮执行现场、单写者租约锁、socket、Docker 对象、共享依赖卷——永不进目录。

规则：

- **L1 单一活权威**。每类事实只有一种可写权威；落盘层不产生第二种可写真相。目录副本按原所有者 manifest 绑定（事件按 E manifest 形状、Session 按 X 导出 manifest、版本按 F `version_ref`），恢复时以落盘层重建活层并逐项校验 digest；不符显式失败，不猜测、不静默补齐。
- **L2 静止点落盘**。落盘发生在 Round 边界或显式 quiesce，批量 fsync；活层与落盘层之间**不做跨设施事务**（G1:32 已声明不假设跨设施事务），用 manifest digest 比对代替分布式提交。
- **L3 目录只装任务侧持久物**。host 共享机制（NATS 服务器、Docker Engine、共享依赖卷、宿主 authority 配置）不进目录；其任务相关字节按范围导出落盘。
- **L4 目录是可移植单元，但不是授权单元**。搬走 = 接续区 + 观测区落盘；导入需**重新登记/授权**、重建活层、按引用重新提供外部 Workspace（见 §12 U5、I8）。

设施归属表（"落点"列为建议，非既有实现）：

| 活权威（今天） | 今天的配置根 | 目录落点（建议） | 分区 | 说明 |
|---|---|---|---|---|
| R 控制 sqlite | `runtime.control_db` | `ledger/control.sqlite`（每任务库）+ host 侧登记/授权索引 | A | 拆分见 U4 |
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
| **A 接续区（carry）** | `task.json`、`harness/**`、`surface/content`+`head`、`surface/facts/`、`ledger/**` | 不受损即可接续；glossary"接续 = 从 T0 重放"的 T0 实操含义 | T0（接续集） |
| **B 观测区（observation originals）** | `session/**`（Pi JSONL、快照、provider wire、X 原件导出）、`ledger/receipts/` | 原件、不可重建、非接续依赖；审计与仪器依赖 | T0 的观测子集（glossary 现未列） |
| **C 派生区（derived）** | `derived/**` | 随时可删可重建，产物可复核 | T1 |
| （目录外） | 沙箱实例、运行现场、锁、socket、Docker 对象 | 释放即归零 | T2 |

术语修订建议：把 glossary T0 写成 **"T0 = A ∪ B（不可重建的原件）"**，并新增一句 **"接续集 = A ⊊ T0"**；或者增设 `T0o（观测原件）`。两种写法都可消除缺口，但都动到已定稿的 glossary，须独立复核。

保留纪律：B 区可按声明策略修剪/导出，但修剪必须留**墓碑**（范围 + digest + 原因 + 时间），仪器可 pin 保留下限（对齐"保留/归档不得静默破坏仍被承诺的恢复依据"，v5:123；"保留范围不得删除仍被已受理责任依赖的记录"，G1:44）；B 缺失时恢复照常，但审计/仪器必须**显式报告缺失**，不得静默补造。

---

## 4. 拓展点与目录树 v2

### 4.1 目录是下界：三层与开放规则

v1 的"框架目录固定"固定的是**语义角色**，不是**闭集**。目录是下界——**至少**要有能兑现 runtime 语义的那几项；其余允许拓展。为同时满足"框架对所有任务同构"与"策略演进不侵入底座"（v5:18；`minimal-harness-extension-points.md`"策略可整体替换，缝隙不变"），分三层：

| 层 | 内容 | 约束 |
|---|---|---|
| **L0 必需骨架** | `task.json`、`harness/manifest.json`、`surface/content`、`surface/head`、`surface/facts`（基础为单文件 `facts.jsonl`，分片是后加机制）、`ledger/`（至少 control + rounds） | runtime 必须能解析；缺失 = 非法任务，登记/恢复响亮失败。**顶层只有 4 项**：`task.json`、`harness/`、`surface/`、`ledger/` |
| **L1 默认实例与标准点** | `harness/{conventions,projection,organization,rounds,admission,logic}`（+ 待裁决的 `tools/`、`budget/`；+ 可选的 `views/`、`presentation/`，见 §4.7）、`session/`、`derived/` | **不是骨架**：有默认路径；**可缺席**（缺席 = 该能力关闭）；可由 manifest 改指；**可多实例**（多策略对比，v5:18） |
| **L2 开放扩展** | `harness/ext/<ns>/`、`derived/ext/<ns>/`、`surface/content/**`、`task.json.extensions` | 命名空间下自由；runtime **保留、不解释、不因未知而失败** |

绑定**角色**而非路径：`harness/manifest.json` 声明 `roles:{<role>:[{ref,digest}...]}` 与 `extensions:[{id,kind,ref,digest}]`；runtime 先按声明解析，未声明才回退默认路径；未知 `kind` = 惰性数据，既不报错也不执行。

保留名与冲突：顶层目录名、`surface/head`、`surface/facts`、`harness/manifest.json` 为框架保留；L2 不得遮蔽；同角色多实例以实例名区分。

缺失语义：L1 角色缺席等于该能力关闭（无 `organization/` = 不折叠、不归档）；首轮前可无 `session/`；`derived/` 可整体缺失。

**与最简 harness 拓展点清单的对齐**（`minimal-harness-extension-points.md` 的 10 点，防止两套清单漂移）：

| 拓展点 | 任务目录落点 | 归属 |
|---|---|---|
| 1 模型基线 | `task.json.model_refs`（意图）+ runtime Model Routing（供给） | 任务声明 / runtime 落实 |
| 2 每步投影 transform_context | `harness/projection/` | 任务 |
| 3 上下文工作集维护 | `harness/organization/`（策略）+ `harness/rounds/`（触发） | 任务 |
| 4 预算准入 | `harness/budget/`（标准点，待裁决；或并入 rounds） | 任务 |
| 5 截止层次 | `harness/rounds/` + 环境 profile（T2，runtime） | 分层 |
| 6 X slot 包络 | **不在任务目录**（runtime 修订） | runtime |
| 7 事件与通知 | `harness/admission/`（收什么）+ `harness/projection/`（输入视图筛选） | 任务声明 / E 落实 |
| 8 终止判定 decide | `harness/logic/`（+ `rounds/` 结束条件） | 任务 |
| 9 观测协议 | **不在任务目录**（V/外部仪器；钉在 `derived/` 产物上） | 外部 |
| 10 工具执行 | 执行**不在任务目录**（runtime X）；工具**定义**在 `harness/tools/`（标准点，待裁决） | 分层 |

结论：v1 的标准点清单漏了 `tools/`，`budget/` 归属未定；上表把 10 点逐一对齐，并把"在 runtime 侧"的点显式标注，防止误把机制塞进任务目录。开放规则的可证伪判据见 §13 VD13/VD14。

### 4.2 基础目录树（宁缺毋滥）与默认实例

**基础树：只有这 4 项是骨架（必需）**

```
<tasks-root>/<task-id>/
├── task.json                # 身份/绑定/策略引用/状态（可变；runtime/管理面写）
├── harness/
│   └── manifest.json        # 声明：事件词表 + 角色引用（登记后只读）
├── surface/
│   ├── content/             # 模型唯一可写区：产物（设计/文档/协议代码/笔记）
│   ├── head                 # 提交点：head → revision（原子替换）
│   └── facts.jsonl          # 事实流（append-only；分片是后加机制，不改语义）
└── ledger/                  # 运行账本：受理去重 + 轮记录（Event ≠ 私有账本）
```

**按需位置**（出现即合法，不出现也合法）：`session/`（观测原件；接续不依赖，审计/仪器/无损归档用）、`derived/`（可重建：投影产物、索引、召回）。
**目录外**：Workspace 授权范围；T2（沙箱实例、轮现场、租约锁、socket）；host 共享机制（NATS/Docker/共享依赖卷/宿主授权配置）。

**为什么恰好是这 4 项**——不是分类学，是四条硬测试：

| 测试 | 问题 | 结论 |
|---|---|---|
| 存活 | 不拷它还能接续吗？ | `task.json`、`harness/`、`surface/`、`ledger/` |
| 权限 | 模型能写吗？ | 只有 `surface/content/` 可写 → 必须能单独挂载 |
| 语义 | 回答"现在是什么 / 为什么 / 运行记录"？ | content / facts / ledger 三者**互不可替，不能合并** |
| 拓展 | 新能力能只靠声明表达吗？ | 能 → **不加目录**（9 个示例，0 个新增顶层目录） |

**默认实例**（最小 harness 的完整形态，**不是骨架**；子目录可缺席、可改指、可多实例）：

```
<tasks-root>/<task-id>/                       # 目录名 = task_id；稳定、可移植、仅 [-._A-Za-z0-9]
├── task.json                    [A] 身份/绑定/策略引用/关系声明/状态/落盘边界；无密钥无端点
├── harness/                     [A] 推进定义（登记后只读，模型不可写）
│   ├── manifest.json            #   入口与各策略引用 + 自身 digest
│   ├── conventions/ projection/ organization/ rounds/ admission/ logic/
│   │                            #   标准拓展点：默认路径，可缺席、可改指、可多实例
│   ├── views/ presentation/     #   [可选标准点] 信息项声明与形式装配（§4.7）；缺席=只用 L0 最低信息
│   ├── tools/                   #   [标准点，待裁决] 工具定义与交互解析
│   ├── budget/                  #   [标准点，待裁决] 预算与截止声明
│   └── ext/<ns>/                #   [L2 开放] 任务自定义拓展（runtime 保留不解释）
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
│   ├── control.sqlite           #   R 控制库（每任务根；host 登记/授权索引在目录外，见 U4）
│   ├── admission.jsonl          #   外来事件去重账（接受行可由 facts 重建；拒绝行是原件）
│   ├── rounds.jsonl             #   轮记录：触发求值、起止、attempt、Grant 快照、计量
│   └── receipts/                #   [B] 设施回执原件
├── derived/                     [C] 可重建（随时可删）
│   ├── projection-cache/ index/ plans/ input/ recall/
└── (目录外) Workspace 范围 | T2：沙箱实例、轮现场、单写者租约锁、socket
```

**场景证据（harness-catalog/ 9 个示例，全部只用基础树，无新增顶层目录）**：

| 示例 | 用到的基础位置 | 新增顶层目录？ |
|---|---|---|
| goal | `task.json` / `harness/` / `facts` / `content/` / `ledger/` | 否 |
| plan | 同上（spec 在 content，状态在 facts） | 否 |
| archive | `content/` / `facts` / `derived/`（按需）/ `session/`（按需） | 否 |
| ask-user | `facts`（外部受理）+ 等待（本就不需要目录） | 否 |
| coding | `content/`（笔记）/ `facts` / `session/`（工具结果）/ Workspace（目录外） | 否 |
| research | `content/`（素材）/ `derived/`（索引）/ `views`（声明） | 否 |
| delegation | `task.json`（关系）/ `facts` / 对方任务目录（目录外） | 否 |
| monitoring | `facts` + 触发条件（无目录） | 否 |
| system-design | `content/`（设计本体）/ `facts`（决策·修订）/ `head` | 否 |

结论：**能力都长在 `harness/` 的声明与 `content/` + `facts/` 的数据里，不产生新顶层目录**；示例暴露的是**通用原语缺口**（backlog B14），不是目录缺口。

**Workspace 不在任务目录内**：v5/G1 把 Workspace 定义为独立的"授权文件范围引用"（v5:38、G1:25），`task.json` 只存 owner/kind/身份/版本引用；目录可移植不等于外部 Workspace 可移植，导入时按引用重新提供或显式拒绝（见 U5）。

### 4.3 示例：在目录上定义一个 harness（goal 模式 / plan 模式）

**先纠一个方向（用户 2026-09-16 纠正）**：目标（goal）与计划（plan）**不是框架要认识的目录**。它们是"在这个目录结构上怎么定义一个 harness"的**示例**——用框架的**通用拓展机制**定义出来，框架不因它们新增任何标准点。本件早期草稿曾把它们提升为 `harness/goal/`、`harness/plan/`、`harness/events/` 三个"标准点"，那是把领域策略写进底座，违反 v5:18 与 v5 §5.4"Runtime 不内置策略"。**该错已撤回，记录保留于此**（不掩盖不利记录）。

**示例 A：goal 模式**——一个 harness，用通用点表达"目标 + 完成事件 + 验收引用"：

| 它要做的事 | 用哪个通用点 |
|---|---|
| 定义自带事件（`task.completed` 等） | 声明：manifest 的 kind + Fact Contract 引用（P1） |
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

1. 形如 `task.completed` 的是 **harness 声明的事件**，不是 runtime 通用终态。v5:161 明确 `ready/done/fail` 不是每个 Harness 必须接受的 Runtime 业务语义；v5:208"没有通用 Surface 终态要求"。Runtime 只做三件事：产生观测事实、按声明求值触发条件、按声明投影。
2. **"完成" ≠ Task 不活**。Task 的"不活"只有管理动作 Archive（glossary Task 边界）；该事件至多让这个 harness 不再开轮，任务仍在册。
3. **完成声明不构成业务验收**。验收独立（V/外部验收器）；Runtime 只记录声明与证据引用（GOAL §4；AGENTS.md"禁止以应用声明证明完成"）。
4. **"上下文窗口接近"这类是 runtime 的声明式观测事实（P7）**：阈值由 harness 配置（领域调参），runtime 跨阈值落事实，是否开组织轮由 harness 的触发条件决定；**不是 runtime 注入固定文本**（这保持 `minimal-harness-extension-points.md` §3"缝隙在宿主、策略可换"，并满足 O6 可观测性）。

**可证伪判据（见 §13 VE01–VE05）**：示例 harness 只用 P1–P8 即可表达；**若必须新增框架目录才能表达，判为"框架缺通用原语"，补 P 项而不是补领域目录**。

**V-A 已裁决（2026-09-16）**：实例状态权威在**事件**，见 §4.4。`content/` 只放产物与渲染，Projection 由事实派生当前态。

### 4.4 事件是唯一的推进与接入契约（用户 2026-09-16 裁决）

用户裁决："我们都是基于事件的……推进也是一样；事件是接入实现的最好方式，不然就搞乱了。"本框架据此固定以下规则（与 v5/glossary 既有主线一致：Trigger Condition 是事实流上的谓词，glossary:64-66；一切事实落面，glossary:31；回放只恢复已记录事实、不重做其中动作，v5:163）：

| 规则 | 内容 |
|---|---|
| **E1 进来只有一个门** | 外来、跨任务、系统观测一律经 Fact Admission 落面；没有 Fact Contract 的事件进不来（无法校验、路由、安全消费） |
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
      { "kind": "task.completed",
        "contract": { "ref": "contracts/task-completed.json", "digest": "sha256:…" },
        "producer": "harness" },
      { "kind": "sys.context.window.approaching",
        "contract": { "ref": "<框架随版本提供>", "digest": "sha256:…" },
        "producer": "runtime" }
    ],
    "triggers": [
      { "id": "goal-progress",
        "on": ["task.completed", "sys.context.window.approaching"],
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
| **R6 digest 不自引用** | manifest **不内嵌自身 digest**；其 digest 由规范字节计算，记在 `task.json.harness.digest` 与登记记录里（【v2 修订 v1:19 的"含自身 digest"措辞】） |

**保留名与命名空间**（Q3 裁决：保留前缀 + 扩展命名空间）：

| 类别 | 保留 / 规则 |
|---|---|
| 路径 | 顶层 `task.json / harness / surface / session / ledger / derived`；`surface/{content, head, facts}`；`harness/manifest.json`。扩展只能放 `harness/ext/<ns>/`、`derived/ext/<ns>/`；`content/` 内部由 `conventions/` 决定，框架不保留具体名 |
| 事件 kind | 框架保留 **`sys.*`**（runtime 产生的观测，如 `sys.context.window.approaching`）；harness 自定义 kind 必须落在**自己的命名空间**（如 `acme.*`）。所以 `task.completed` 这个名字本身不归框架，是某个 harness 自选的 |
| 命名空间所有权 | 命名空间在 manifest 声明，**同一宿主内不得与其他已登记 harness 或保留前缀冲突**；冲突 → 注册拒绝（命名空间申请/转让机制留后续） |

### 4.6 能力怎么定义：五件套模板 + task / plan / archive 三个示例

**一个能力 = 五件套**（全部由 harness 声明，框架只提供 P1–P8 原语与 §4.5 解析规则）：

| 件 | 作用 | 落点 |
|---|---|---|
| ① 词表 + 契约 | 有哪些事件、payload schema（digest 即语义） | `facts.kinds` + contracts |
| ② 产生者 | 谁产生：**runtime 观测**（`sys.*`）／**harness 声明**（自己命名空间）／**外部受理**（外来） | kind 的 `producer` |
| ③ 触发与受理 | 什么事件开轮、什么事件被收/去重 | `facts.triggers` + `roles.admission` |
| ④ 投影 | 把"当前态"渲染给模型（给指针不灌全文） | `roles.projection` |
| ⑤ 逻辑 | 状态机、判定、门控 | `roles.logic`（+ `roles.rounds` 结束条件） |

产物是 `content/` 文件，由事件**引用其 revision**。**注意**：产生者不等于"谁都能写事实"——所有落面仍由 runtime 单写者执行；harness"产生"是调用声明过的受控入口（E1/E2）。

#### 示例 1：task 功能（任务级：进度 + 委派）

| 件 | 进度侧 | 委派侧（跨任务） |
|---|---|---|
| 词表 | `task.objective.set`（objective ref + acceptance_refs）、`task.phase.changed`、`task.completed` / `task.blocked`（附 evidence_refs） | `task.delegated`（parent/child、scope、input_refs）、`task.accepted`/`task.rejected`、`task.reported`（result_ref + 证据） |
| 产生者 | 外部受理（objective）+ harness 声明（progress/completed） | harness 声明（delegated/reported）+ 对方受理（accepted/rejected） |
| 触发 | `objective.set` → 开第一轮；`completed` → `rounds` 不再开轮 | `accepted`/`reported` → 开父任务轮 |
| 投影 | 当前 objective + phase + 验收清单 + 证据指针 | 子任务状态摘要 + 结果引用 |
| 逻辑 | phase 状态机；验收引用解析（谁验不归它） | 关系声明（wants/grants）、超时/取消判定 |
| 边界 | `task.completed` 只是声明，不是 runtime 终态（§4.3 边界 1–3） | 委派 = 两 Task 间事件受理，**无中心行动者**；**不继承授权**（B 的 wants + A 的 grant；副本不带授权） |
| 反例 | 把 `task.completed` 当 runtime 终态 | 父任务直接写子任务 `content/`；凭 `task.json` 文本继承授权 |

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
| task | `task.*` | 外部 + harness | objective.set / reported | 目标状态 + 验收清单 | 状态机 + 委派授权 |
| plan | `plan.*` | harness + 外部 | stage.completed | 当前 + 下一阶段 | 阶段门控 |
| archive | `sys.context.*` + `archive.*` | runtime + harness | threshold.crossed | 摘要 + 指针 + 尾部 | 折叠策略 |

**结论**：能力不是框架目录，也不是 runtime 分支；能力 = **词表 + 产生者 + 触发 + 投影 + 逻辑**，全部在 harness 里声明。这与你的理解一致，只多两处必须钉住：**产生者要分三类**（否则系统观测和应用声明会混为一谈），**投影与逻辑要分开**（一个给模型看什么，一个决定推进）。

### 4.7 给模型看的信息：信息项 / 投影 / 呈现（分开定义，约束从轻）

用户 2026-09-16："给模型看的信息也需要投影给模型；是否与投影分开定义——最好分开，但也不想去限制。"三层落地：

| 层 | 回答什么 | 落点 | 约束 |
|---|---|---|---|
| **① 信息项**（what can be shown） | 有哪些东西可供展示：当前目标/阶段状态、事件视图、前序反馈、工作区快照、检索结果、系统观测…… | manifest `views` 声明 + 可选 `roles.views`（解析器） | **从轻**：只要求稳定 `id`、来源可定位、解析器可寻址、产物可观测、缺失显式；**不定义视图类型学、不规定 schema 语言、不限数量命名** |
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
| `task.json` | JSON `lore-task/v1`：`layout_version, task_id, namespace, identity, harness{ref,digest}, model_refs{}, workspaces[], relations{wants[],grants[]}, state{lifecycle:active\|archived}, landing{boundary,last_round}, policy{session_retention}` | Runtime / 管理面 | A | 临时文件 + rename | 变更史入版本；禁密钥/端点（glossary:100-102） |
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
| 单写者租约锁 | 目录外 runtime spool `<locks>/<task-id>.lock` | Runtime | T2 | flock | 不进目录（拷贝不携带锁） |

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
- **单写者**：每任务一份目录外租约锁 + head CAS；检测到并发写者拒绝推进，不静默覆盖（v5:71、G1:88）。
- **跨设施非原子**：按 L2 用 manifest digest 比对，不引入分布式事务；失回执一律先按原身份查询（G1:38、R:31）。

---

## 7. 生命周期与身份

- **create**：从模板实例化 `harness/`（含 manifest digest）+ conventions 决定的 `content/` 骨架 + `task.json`（`layout_version`）。
- **register**：host 侧登记与授权（R），绑定 harness digest、Workspace 引用、model refs；登记不隐含启动（v5:210）。
- **run**：求值 Trigger Condition → Harness 前置逻辑（可选）→ ≥0 Step → 按 §6 提交。
- **quiesce / land**：Round 边界已是静止点；显式 quiesce 额外把 host 全局设施的任务相关范围导出落盘（事件范围、快照、回执）。
- **archive**：管理动作——数据保留、停止求值/受理（glossary:67-68）；**是状态不是目录**。
- **export / import**：quiesce 后拷贝目录即导出；导入到新宿主需重新登记/授权、重建活层、校验 digest、按引用重新提供 Workspace（AGENTS.md：新环境重新生成路径与物理身份，不复制旧 inode/device）。
- **delete**：显式动作；不得删除仍被已受理责任或其他任务引用依赖的记录（E:11、G1:44）。

身份收束：`task_id` ↔ `namespace` 1:1（最小情形），`session_scope=(namespace, surface_id, session_id, session_generation)`（`lore_session/snapshot_files.py:15`）。这回答了盘点中"代码里 task id 意图不清"：**task_id 是目录与移植的单位，namespace 是登记/授权的范围，二者在任务目录里显式绑定**。

三种 "archive" 禁混：任务级 Archive（不活，管理状态）、内容级归档（organization 策略产物，conventions 决定）、设施 archive（F/X 的原件归档）。框架不设 `surface/archive/`（v1:123 保留）。

---

## 8. 挂载与权限矩阵

| 路径 | Runtime 控制进程 | 模型 Surface 域 Shell | 任务沙箱（Workspace 域） | 观测器 |
|---|---|---|---|---|
| `surface/content/` | RW | **RW（唯一）** | ✗ | RO |
| `surface/facts/` | RW（导出） | RO（经本轮输入视图） | ✗ | RO |
| `surface/head`、`versions.git/`、`artifacts/` | RW | ✗ | ✗ | RO |
| `harness/` | RW（仅登记时） | RO | ✗ | RO |
| `session/`、`ledger/`、`task.json` | RW | ✗ | ✗ | 按授权 RO |
| `derived/` | RW | RO（可选） | ✗ | RO |
| 目录外 Workspace 范围 | 协调 | ✗ | RW | 按授权 |

【v2 修订 v1:60】v1 写"沙箱只挂载 content/"；按 v5/G1 的双 Shell 模型，写 Surface 的是**经授权的 Surface 域（Runtime）Shell**，任务沙箱写的是 Workspace/输出/临时区、**默认不挂载任务目录**（v5:70,184，G1:84）。目录边界即权限边界，只读性按挂载落实（v1 设计陈述 2 的原则不变）。

---

## 9. 机制题裁决（v1 §待定 1–5）

1. **事实流分片**：sealed 段按记录数或字节阈值（harness 配置，属领域调参；默认值待测，参照现有 8192 行/8 MiB 量级不预设 SLA），命名单调 `seg-<start>-<end>.jsonl`，**不重编号**；open 段未满不 seal；接续语义 = 按 `index.json` 顺序拼接 + 逐段 digest 校验（v1"按量/按时间滚动，接续重放语义不变"落地）。
2. **revision 粒度**：默认每 Round 一个 revision；工具调用级留痕是 conventions 选项；无论哪种，`head` 默认只在 Round 提交点推进，message/记录绑定 `round_id` + facts 范围 digest（v5:349 不冻结每步提交）。
3. **关系双向性**：消费侧 `wants` 记在 B 的 `task.json`，授权侧 `grants`（含 grant generation）记在 A 的 `task.json`；受理时由 Runtime 查 A 的**当前** generation；**副本不继承授权**——A 离线或未在新宿主重授权时，B 的 wants 不生效（见 I8）。细节归 admission 合同。
4. **归档区位置**：框架不设 `surface/archive/`；任务级 Archive 是状态、内容级归档由 conventions、设施 archive 是原件，三者不混。
5. **Session 保留/修剪**：策略声明在 `task.json.policy`（值可由 `harness/rounds` 声明）；默认全留于 B；修剪须留墓碑（范围+digest+原因）、尊重 pin 下限、缺失可发现；大对象走 `session/blobs/<sha256>`；导出可省略观测区，但导入必须报"观测缺失"。

---

## 10. 布局版本与迁移

- `task.json.layout_version` 是布局唯一版本号；目录名/框架布局属 **runtime 语义**，变更须随 runtime 版本提供迁移，未知更高版本**响亮拒绝**，更低版本迁移或显式只读。
- harness digest 与 `task.json` 绑定；换 harness = 新绑定版本，进行中的 Round 不静默换策略（G1:40）。
- 物理身份不落盘为权威：登记的真实根/dev/ino 是 **host 侧**登记事实，导入新宿主必须重新观测生成（AGENTS.md 平台约束；F:21 跨环境身份映射须显式指定并验证）。

---

## 11. 可机检不变量（草案，未验证）

| ID | 不变量 | 观测方式 |
|---|---|---|
| I1 | 接续自包含：quiesce 目录 + 重新授权可在新宿主重建活层并通过 digest 校验 | 迁移后逐项比对 facts/head/harness/ledger |
| I2 | 无宿主耦合：目录内无密钥、无绝对宿主路径（除 `task.json` 显式标注的 host-bound 引用）、不依赖 dev/ino | 扫描 + 导入不复制物理身份 |
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
| "拷走目录 = 搬走完整任务"（v1:40,105） | 搬走 **A 接续区 + B 落盘**；授权、host 机制、外部 Workspace **不随目录迁移** | E/R 授权在 host 侧（e:7、r:9）；Workspace 是外部引用（v5:38、G1:25） |
| "整个任务目录 = 一个 git repo（facts/session/ledger/derived 进 ignore）"（v1:104） | 目录 = 一个**版本边界**；机制可以是 F `versions.git`（capture profile 决定成员）或 worktree git + ignore，二选一（U3） | F 合同已把版本固定为 Git 对象+archive+manifest（f:38、f/manifest-contract.md）；避免同内容双 git |
| "沙箱只挂载 content/"（v1:60） | 写 content/ 的是 Surface 域（Runtime）Shell；任务沙箱只见 Workspace 范围，不见任务目录 | v5:70,184；G1:84；§8 |
| 目录树里只有 `surface/facts.jsonl` 单文件（v1:30） | `surface/facts/` 段目录 + `index.json`；单文件是退化情形 | 机制题 1 |
| `harness/manifest.json`"含自身 digest"（v1:19） | manifest **不内嵌自身 digest**；digest 由规范字节计算，记在 `task.json.harness.digest` 与登记记录 | §4.5 R6（自引用不可能） |

### 12.2 待裁决（根本级；需用户或独立复核）

- **U1（核心）D1 双层落盘模型**：目录 = 任务侧 T0 落盘层 + 每任务设施根，host 共享机制保留在目录外。这是"目录与既有设施关系"的根决策，直接决定后续实现形态。
- **U2 D3 三分区与 glossary T0 修订**：Session/观测原件现在无层级可归；建议 `T0 = A ∪ B，接续集 = A` 或新增 `T0o`。
- **U3 D2 content revision 机制**：建议以已验的 F `capture`（versions.git + archive/manifest）为主，worktree git 作为 conventions 选项。
- **U4 R 控制库归属**：每任务 `ledger/control.sqlite`（利于"拷走即完整"）vs host 共享库 + namespace 过滤（利于跨任务关系与公平轮转）。建议**拆分**：任务侧运行账本随目录、host 侧登记/授权/跨任务关系索引留在 host，但这要动 R 合同。
- **U5 可移植性措辞与 Workspace 迁移责任**：外部 Workspace 按引用版本另行迁移或显式拒绝。
- **U6 事件导出时机**：默认每 Round 一次范围导出；每 Step 导出为 conventions 选项。

### 12.3 新增未决（机制级）

- 事件导出的接口形态：用既有 runtime 读端循环（`lore_runtime/event_reader.py` 单条读取）还是给 E 增一个窄 `export_range`（后者要动 E 合同与用例）。
- host 登记/索引的可重建性：能否仅靠扫描 `tasks-root` 重建"在册"？跨任务 grants 的权威是否只在 host。
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

每条须独立判据、可拒绝相关错误、明确观测；当前全部 UNVERIFIED，且本仓库无任务目录实现，故只作为后续 G4 的预登记输入。

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
| VD11 | 复制含 `grants` 的目录到新宿主，未重授权不受理 | 凭 task.json 文本继承授权 | 受理尝试 + 授权侧核对 | 安全不变量 I8 |
| VD12 | 任务沙箱不可见任务目录；Surface 域 Shell 可见 content/ 与只读 harness/ | 沙箱逃逸读写 | 挂载 + 进程身份观测 | 对齐 P02 |
| VD13 | **新增拓展点不改 runtime**：给 harness 增加一个 manifest 声明的新 kind（自定义投影器/组织策略），注册并运行；runtime 不拒绝未知项、新策略被实际采纳（观测其产物），且 runtime 产品代码零改动 | runtime 按硬编码路径清单拒绝/忽略扩展；扩展遮蔽框架保留名 | 注册结果 + 真实投影产物 + 产品代码版本 | 单靠"注册未报错"不算；须观测策略实际生效 |
| VD14 | **未知 L2 条目保真**：`harness/ext/<ns>/` 下未知条目在 Round 提交、拷贝、导入、恢复、`derived/` 重建后仍在，且从未被 runtime 解释 | 未知条目在恢复/重建时被丢弃；被当成角色执行 | 迁移前后逐字节比对 | L2 规则的直接否证 |
| VE01 | **无通用终态**：未声明 goal/plan 的任务照常运行并按声明停止，runtime 不产生也不要求 `task.completed` | runtime 合成终态；无 goal 即拒收任务 | runtime 记录 + 事实流 | 对齐 v5:161,208 |
| VE02 | **示例 harness 充分性（goal 模式）**：只用 P1–P8 通用点的 goal 模式 harness 可表达"目标 + 完成事件 + 验收引用"，实现与运行**不新增任何框架目录/字段** | 必须加 `harness/goal/` 或 runtime 分支才能表达 → 判为框架缺通用原语 | 注册 + 运行 + 事实/投影产物 + 产品代码版本 | 判据是可表达性，不是业务结果正确性 |
| VE03 | **示例 harness 充分性（plan 模式）**：阶段完成事件落面后**下一阶段被投影进下一次实际输入**，全程无 runtime 调度器、无框架 plan 目录 | 需要框架为 plan 开后门；plan 变成 runtime 调度 | 实际投影文档 + 阶段边界 | 对齐 v5:18 |
| VE04 | **观测事实（P7）**：跨声明阈值产生观测事实（如上下文窗口接近）；harness 据此开组织轮；该事实出现在下一步输入投影中 | runtime 注入固定压力文本替代事件；观测不可见 | 输入投影原文 + 组织轮产物 | 对齐 extension-points §3 与 O6 |
| VE05 | **身份与保留名（P6/P8）**：harness 自定义对象的 id（如 goal/stage）跨 Round、重放、迁移稳定；扩展占用框架保留前缀被拒 | 标识随路径/重排而变；保留名被扩展遮蔽 | 重放/迁移前后比对 + 注册拒绝 | 与 §4.3 P6/P8 配套 |
| VE06 | **manifest 解析（§4.5 R1–R6）**：声明优先、默认路径兜底、缺席=关闭；声明但 digest 不符→注册拒绝；未知条目保留不报错；`sys.*` 只能订阅不能自定义；多实例按 `id` 调用 | 按硬编码路径名调用；未知字段即失败；harness 自定义 `sys.*` | 注册结果矩阵 + 实际调用轨迹 | 正反例都要，注册拒绝≠运行失败 |
| VE07 | **archive 能力（§4.6 示例 3）**：跨阈值产生 `sys.context.*` 观测事实并开维护轮；折叠后投影缩减而原文仍在；有损摘要记 `fold_digest`+`original_refs` | 用 `derived/` 当归档区；摘要丢原文无指针；runtime 硬编码阈值 | 事实流 + 折叠产物 + 原文可达性 | 对齐 v5:252 |
| VE08 | **task 委派（§4.6 示例 1 委派侧）**：父任务只能经事件与授权受理影响子任务；未授权委派被拒；子任务结果经 `task.reported` 回来 | 父任务直接写子任务 `content/`；凭副本继承授权 | 跨任务事实流 + 授权侧拒绝 | 对齐 glossary"无中心行动者"、I8 |
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
| 模型/任务不持密钥、控制端点、NATS 凭据 | glossary:100-102；E:7；R:9 |
| X pause→导出精确字节→外部持久化→resume | s:29,41 |
| 双 Shell 写范围与权限由 Runtime 落实 | v5:184,188,190；G1:84 |
| F 版本 = Git 对象 + archive + manifest；控制/授权/Session/事件不入回退归档 | f:38；f/manifest-contract.md |
| 登记身份含 dev/ino，路径不是权限 | f:9；r:17 |
| 现状无 task-root、设施分别配置；m01 先例 | 源码只读盘点；`validation/system/m01_run.py:100-103` |
| 三种 archive 禁混 | glossary:67-68；v1:123 |
| **事件是唯一的推进与接入契约；harness 自定义对象的实例状态权威在事件** | 用户 2026-09-16 裁决；v5:40,163；glossary:31,64-66；r:7（禁止竞争真相） |
| manifest 声明优先 / 保留前缀 `sys.*` / 扩展命名空间 | 用户 2026-09-16 裁决（§4.5）；v5:349（目录名不冻结） |
| 信息项 / 投影 / 呈现 三层分开，约束从轻；L0 最低信息五项 | 用户 2026-09-16（§4.7）；v5:204；glossary:109-115（Projection ≠ Presentation） |

---

**本稿不改任何既有验收结论**；它把"任务目录"从 v1 的框架半成品补成可复核的机制设计，并把其中真正根本的分叉（U1–U6）显式交回裁决。
