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
