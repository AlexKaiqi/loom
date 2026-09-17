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
