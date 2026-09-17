# 助手 Task 实例形态（一个助手 = 一个长期 task）

状态：UNVERIFIED 设计稿。本文件按用户 2026-09-17 的三项裁决落地：
① **长期关系 = 一个 task**（会话是 task 内的 session 区间，不是新 task）；
② **语音只属于助手 harness**（端口/适配器/会话编排都在 `harness/ext/voice/`，不新增框架设施）；
③ **要落在任务目录里**（本文件给出一个具体实例的目录解剖、会话模型与事件流）。
相关：[README.md](README.md)、[architecture.md](architecture.md)、[duplex.md](duplex.md)、
[style-profiles.md](style-profiles.md)、[providers.md](providers.md)、
[../task-directory-landing.md](../task-directory-landing.md) §4–§8。

## 1. 定义收敛（三层，一层都不能少）

| 层 | 定义 | 归属 | 可变性 |
|---|---|---|---|
| **① 助手档案 Assistant Profile** | 人格、默认风格、能力/工具白名单、安全边界、记忆策略、语音/音色绑定 | 助手 harness 自带的模板 + 每 task 的用户配置 | 用户/管理面改 = 新 revision；模型只能**提案** |
| **② 助手 harness** | 推进策略（何时开轮/看什么/怎么守门）**+ 语音机制**（端口/适配器/会话编排） | `harness/`（登记后只读） | 改一字节 = 新 harness 版本 = 新绑定 |
| **③ 助手 task 实例** | 一个具体助手的存在：目录、事实、记忆、会话史、授权 | 任务目录 | 由事件推进；关系结束才归档 |

**关键判据**：一次会话的结束**不是** task 的结束。`voice.session.ended` 只是事实；
task 的 `state.lifecycle` 仍为 `active`（像 monitoring 一样长期在册，但**空闲期不驻留进程**）。

## 2. 一个实例的目录解剖

```
<tasks-root>/<assistant-task-id>/
├── task.json                       # 身份与绑定（runtime/管理面写）
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
│   │   ├── workspaces/index.md     # 用户工作空间清单：id·用途·指针·最近观测 revision（见 latency-and-curation.md §3）
│   │   ├── workspaces/<ws-id>.md   # 工作空间卡片：用途/结构/入口/注意事项（认知 ≠ 授权）
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

一次会话 = task 内的一段区间（`session_id`），不是新 task。

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
任务轮负责持久化与记忆演进。**本轮不换策略**（v5:204），新 bundle 下一轮生效。

**音频不进事实流**：ASR partial / TTS chunk 落 `session/sessions/<id>/`（观测域）与 artifact 引用；
面事实只到轮次级。

## 4. 语音机制在 harness 内的布局（裁决②）

- **端口与适配器**（[architecture.md](architecture.md) §2 的 Protocol）放在 `harness/ext/voice/`，
  是 harness 的普通代码；换模型 = 换 `voice_refs` 绑定 + 复跑同一套一致性用例。
- **会话编排**（双工状态机、barge-in、重连）在 `ext/voice/runner.py` 与 `session.py`；
  复用开源编排后端（LiveKit Agents / Pipecat）时，它同样被包在 `ext/voice/` 里，**不进 runtime**。
- **凭据**：`registry.json` 只写 `credential_ref:"env:ARC_PLAN_API_KEY"`，值只在 runner 进程内读；
  不落任务目录、证据、日志。
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
| create | 实例化 harness 模板 + `content/` 骨架（persona 空稿、style 默认、memory 空索引）+ `task.json` |
| register | host 侧登记/授权；绑定 harness digest、voice_refs、Workspace（若有） |
| session | `voice.session.started` → runtime 起 runner（T2）→ 轮次级事件驱动 task 轮 |
| idle | `voice.session.ended` → **释放 runner 与任务专属媒体资源**；task 仍在册、`lifecycle=active`（v5:90） |
| archive | 关系结束 → 管理动作 Archive：停止求值/受理；**不是** `voice.session.ended` 的自动结果 |
| export/import | quiesce 后拷贝目录即导出；新宿主须重授权；`derived/` 可删重建 |

## 7. 归属问题（本文件新增，需留意）

- **用户配置 vs 模型产物**：`task.json.assistant` 是**用户/管理面**可写（风格列表、策略、绑定），
  模型不可写；`content/` 是**模型**可写（人格演进、记忆、会话摘要）。
  模型想改风格 → 提案（`voice.style.proposed`）→ 用户接受 → 配置新 revision（带 `base_rev`）。
  这样"用户预设的风格"与"模型学到的表达"不会互相覆盖。
- **persona 的边界**：安全边界在配置（`assistant.persona_ref` 指向的版本 + `session_policy`），
  表达风格在 content。边界不允许模型单方面放宽。
- **记忆**：只存**要点/摘要 + 指针**，不存全文流水（v5:250/252）；recall 索引在 `derived/`。

## 8. 未决

- **U1 session runner 生命周期**：runtime 通用机制（推荐）vs 外部服务 vs 借用 `shell` 长驻。
- **U2 记忆策略**：摘要粒度、何时合并、保留期（隐私：语音是生物特征，默认策略需单独裁决）。
- **U3 回复生成位置**：runner 流式（推荐，低延迟）vs 任务轮生成（事件权威更强、延迟高）。
- **U4 多会话并发**：同一助手同时多个会话是否允许；允许则 runner 实例与 `session_id` 的对应关系。
- **U5 音频 artifact**：`session/` 引用 vs 版本化 artifact（F 通道泛化，仍属框架缺口）。
