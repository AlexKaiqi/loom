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
