# 对话记录：目录化的原始音频 + 元数据

状态：UNVERIFIED 设计稿。按用户 2026-09-17 要求：
① **必须有音频记录，也要有元数据**；② 非语音输入（文本/其他语言）**同样**进这套结构；
③ 双工音频要能**识别端点并切成音频片段**；④ 对话记录**目录形式**组织，目录下放原始内容 + 元数据，
并预留**语气/情绪/人物识别**等后续分析位。
相关：[events.md](events.md)、[assistant-task.md](assistant-task.md)、[latency-and-curation.md](latency-and-curation.md)、
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
<task>/session/records/<session-id>/          # 记录区（观测域；二进制不进 git）
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
  "session_id": "…", "task_id": "…",
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
  必须单独裁决（[assistant-task.md](assistant-task.md) U2、[validation-plan.md](validation-plan.md) Q-V5）。

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
