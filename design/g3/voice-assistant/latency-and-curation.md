# 及时响应与知识维护：两个工作重心，一个 task

状态：UNVERIFIED 设计稿。回答用户 2026-09-17 的问题：
**助手既要"马上答"，又要维护对用户工作空间的认知，该怎么安排？空闲做还是怎么做？**
前提（用户已裁决）：上下文**都是同一个助手 task 的上下文**，只是**工作重心不同**。
相关：[assistant-task.md](assistant-task.md)、[architecture.md](architecture.md)、
[style-profiles.md](style-profiles.md)、[providers.md](providers.md)、[validation-plan.md](validation-plan.md)。

## 1. 结论先行

**不拆 task，拆"策略实例"。** 同一个助手 task 里声明两套 `projection/rounds/logic` 实例
（框架已支持多实例角色，landing §4.5 R4）：

| | **会话循环（热）** | **维护循环（冷）** |
|---|---|---|
| 触发 | `voice.user.turn.final`（以及 `session.started`） | `session.ended` / 工作空间变更 / 阈值 / 空闲 |
| 目标 | 首个音频尽早 | 认知新鲜、记忆不腐、索引可用 |
| 延迟预算 | 首音频 ≈1.5–2.5 s（实测下限） | 秒级到分钟级都行 |
| 看什么 | **有界投影**：当前轮 + 生效风格 + 少量记忆/工作空间要点 + 指针 | 全量清单/变更集/日志（只在冷路径展开） |
| 模型档 | 快档（`reasoning_effort:minimal`，或换非推理模型） | 慢档（推理模型可以慢慢想） |
| 写什么 | 只写"轮次级事实"；**回复前不写** | 重写 `content/`（记忆、工作空间认知）+ 重建 `derived/` 索引 |

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

1. **预热（warm-up）**：`session.started` 轮把"这一场大概要什么"备好（最近记忆要点、常用工作空间卡片）。
2. **并行预取（prefetch）**：用户还在说时，用 ASR partial 的关键词预取候选片段（有界），说完即可用。
3. **投机生成（speculative）**：对短回合可先猜着生成、用户继续说就丢弃——Pipecat `EagerUserTurnStrategies` /
   LiveKit `PreemptiveGeneration` 已有成熟实现，**别自己造**。丢弃的投机结果不算已确认输出。
4. **有界投影**：热路径**看不到全文**（v5:250/252），只看到要点 + 指针；细节用工具按需取。
5. **懒工具**：工作空间只给"卡片 + 指针"，不灌文件树；要看再读。
6. **写不阻塞说**：记忆落盘、索引更新一律放轮后/冷路径；**先出声，再记账**。

> 反例：热路径上"先扫一遍工作空间再回答"、把整份记忆塞进上下文、用推理档模型答寒暄——
> 这三件事本身就把延迟吃光了。

## 3. 维护什么：先有"工作空间认知"，才答得上"我有哪些工作空间、都干嘛的"

用户问题需要一张**随时可读的认知地图**。它放助手自己的 `content/`（是**记忆**，不是外部 Workspace 本体）：

```
surface/content/workspaces/
├── index.md            # 清单：id · 一句话用途 · 指针 · 最近观测 revision · 可访问性
└── <ws-id>.md          # 卡片：用途 / 结构 / 入口 / 常用命令 / 注意事项 / 何时看过哪个版本
```

要点：

- **认知 ≠ 授权**：`index.md` 说"这是干嘛的"不需要访问权；**读它的文件要 `task.json.workspaces`/grants**。
  答"有哪些工作空间、都干嘛的"用认知；答"这个函数在哪"必须走授权 + 工具。
- **新鲜度显式**：每张卡片带 `observed_revision`（如 git HEAD / 目录摘要）。热路径拿认知时做一次**廉价陈旧检查**；
  过期就**明说"可能已过期"**并触发一次有界刷新或把刷新排进冷路径——**绝不假装是新的**。
- **冷路径写、热路径读**：卡片由维护循环更新（见 §4），会话循环只引用其版本（landing §4.4 E5）。

同样要维护的还有：**记忆本体**（`memory/`：会话摘要 → 主题要点，去重合并）、**召回索引**（`derived/`，可删重建）、
**风格/人格提案**（模型提案、用户接受，见 [assistant-task.md](assistant-task.md) §7）。

## 4. 什么时候维护：四类触发，空闲只是其中一类

| 触发 | 触发源 | 做什么 | 为什么放这里 |
|---|---|---|---|
| **会话边界** | `voice.session.ended` | 写本次会话摘要、更新相关卡片/记忆 | 便宜、一定有、天然在"说完之后" |
| **变更事件** | `workspace.changed`（外部观测） | 标记卡片 stale，排队刷新 | 有事才做，不空转 |
| **阈值** | `sys.memory.size` / `sys.context.threshold.crossed` | 折叠/压缩/去重（organization 策略） | 对齐 archive 示例，**只缩视图不删依据**（v5:252） |
| **空闲** | `sys.idle`（一段时间无会话） | 深整理：重扫工作空间、重建索引、合并重复记忆 | 便宜时做重活；**空闲不常驻进程** |

**空闲到底怎么做**（回答"是空闲时呢还是怎么做"）：

- 空闲是**补充**，不是唯一：会话边界 + 变更事件已经覆盖大部分；空闲用来做"重但不急"的整理。
- **空闲 = 等一个定时/空闲观测事实，不是起一个常驻循环**（v5:90）：等待期任务专属进程归零，
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
  { "id": "curation",     "on": ["voice.session.ended", "workspace.changed",
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

- **同一 task、同一 `content/`、同一事实流**；差别只在"哪套策略被哪个触发调用"——正是"上下文是 task 的、
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
| VO19 | **热路径装配本地且有界**：`turn.final` → 发起模型调用之间无第二次模型调用、无全量工作空间扫描；装配耗时与上下文字节有上界 | 回答前先扫 repo；把整份记忆灌进上下文 |
| VO20 | **冷路径不侵入热路径**：维护轮运行中用户开口，首音频延迟不劣于无维护轮基线的给定比例；维护可中断且状态一致 | 维护占满 CPU/锁，用户等整理完 |
| VO21 | **陈旧显式**：卡片 `observed_revision` 落后时，回答标明可能过期或先做有界刷新；不得把旧认知当新事实 | 静默用旧卡片；或每次回答都全量重扫 |
| VO22 | **认知 ≠ 授权**：无 grant 时可描述工作空间用途，读取其内容被拒且留痕 | 用"知道路径"绕过授权 |
| VO23 | **空闲零驻留 + 触发正确**：空闲整理由 `sys.idle`/定时观测触发，等待期无任务专属常驻进程；同一观测只触发一次 | 常驻 while 轮询；空闲事件重复触发副作用 |

## 8. 未决

- **U6** 陈旧窗口上界与"同步有界刷新"的时机/超时（需 VO19/VO21 测量后定）。
- **U7** 冷路径模型档与预算（维护轮用推理档是否划算；是否与热路径分开计费/配额）。
- **U8** `workspace.changed` 的观测来源：外部事件源 vs 会话边界抽查 vs 空闲重扫——先用哪种，成本多少。
- **U9** 投机生成（speculative）在"助手"语义下的边界：丢弃的投机是否留痕、是否算一次模型开销。
