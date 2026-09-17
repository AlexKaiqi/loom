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
