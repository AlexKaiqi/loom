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
