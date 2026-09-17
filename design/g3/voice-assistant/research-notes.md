# 语音助手：调研记录（开源实时语音框架与协议）

状态：**调研中（主要来源已核对，框架定版与 ASR 音频格式未决）**。本文件不是验收证据；
引用外部资料标注来源与观察日期，未经独立用例不写入产品依赖（对齐 [GOAL.md](../../../GOAL.md) G2）。
相关：[duplex.md](duplex.md) §4、[providers.md](providers.md)。

## 1. 待检验问题（先有问题，再收资料）

| 问题 | 观测/判据 | 停止条件 |
|---|---|---|
| Q1 用哪个开源框架承载实时会话层？ | 能否用一个适配器接入本稿端口；打断/取消是否可观测可测；许可；中文 ASR/TTS 适配成本 | 候选缩到 1 主 1 备并列出理由 |
| Q2 豆包/方舟在开源生态里有没有现成适配？ | 现成插件/适配器的接口、许可、维护活跃度、支持的端点与鉴权 | 至少一条可复用路径 + 其与 plan 端点的差距 |
| Q3 双工与打断有哪些成熟实现可直接用？ | VAD / 轮次检测 / 打断策略的库与默认行为 | 去重后的构件清单，标注"复用/自研" |
| Q4 plan 语音端点的真实协议 | 实测握手/帧/事件/音频格式（[providers.md](providers.md)） | 关键路径跑通或明确未决 |

## 2. 框架对比（版本/许可为 2026-09-17 快照；**引用前须复核**）

| 框架 | 版本 | 许可 | 抽象形态 | 双工/打断 | 豆包适配 | 结论 |
|---|---|---|---|---|---|---|
| **LiveKit Agents**（`livekit/agents`） | `livekit-agents` 1.8.2 | Apache-2.0；**turn-detector 模型权重另有 LiveKit Model License**（仅限配合本框架用） | `STT._recognize_impl` / `TTS.ChunkedStream._run` / `LLM._run` / `VAD` | `SpeechHandle.interrupt()` + false-interruption resume + adaptive interruption + preemptive generation | **有**：`livekit-plugins-volcengine`（社区） | **主选** |
| **Pipecat**（`pipecat-ai/pipecat`） | `pipecat-ai` 1.10.0 | **BSD-2-Clause**（最宽松，无模型许可附加） | `STTService.run_stt` / `TTSService.run_tts`（各只需 1 个抽象方法）；`WebsocketSTTService`、`InterruptibleTTSService` | `InterruptionFrame` + TTS 聚合器/序列队列 flush；保留 `UninterruptibleFrame`（工具结果不丢） | **无**（需自写 ~2 文件） | **备选（许可最干净）** |
| **TEN Framework** | 0.11.71 | Apache-2.0 **+ Agora 非竞争附加条款**（不是纯 Apache） | Extension + manifest/property + `ten_ai_base` 基类 | 全双工 realtime 示例 + TEN turn detection | **有**（`bytedance_asr`/`bytedance_tts_duplex`/`bytedance_llm_based_asr`，走 `/api/v2/asr` 等） | **不采纳**：许可附加条款 + 多语言运行时（非可嵌入 Python 库） |
| **Vocode** | `vocode` 0.1.113 | MIT | `StreamingConversation(transcriber, agent, synthesizer, output_device)` | 基础打断 | 无 | **不采纳**：最后提交 2024-11-15，事实停更 |

### 2.1 关键发现：已有面向本供应商的开源插件

**`livekit-plugins-volcengine`**（LiveKit Agents 插件，社区 `di-osc/livekit-plugins-chinese` 出品；
PyPI 最新 `1.8.1.post0`，2026-09-14；`requires_dist: livekit-agents>=1.8.1,<1.9`，Python ≥3.10）：

- STT：豆包流式识别，`resource_id="volc.seedasr.sauc.duration"`，
  默认 `base_url=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel`，支持
  `interim_results`、`enable_punc`、`enable_itn`、`vad_segment_duration`、`end_window_size`、
  `force_to_speech_time`。
- TTS：Seed TTS 1.0/2.0，`resource_id="seed-tts-2.0"`，音色示例
  `zh_female_xiaohe_uranus_bigtts`，`sample_rate ∈ {8000,16000,24000}`；音色/格式/采样率会发送，
  **语速/音量/音调当前版本未转发**。
- LLM：方舟文本模型（OpenAI 兼容，默认 `https://ark.cn-beijing.volces.com/api/v3/`）。
- Realtime：豆包端到端实时语音（`O`/`SC`），全双工
  `wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue`，16 kHz PCM 入 / 24 kHz
  `pcm_s16le` 出；支持 `speaking_style`（"说话简洁、自然，语速适中"）。

**与本设计的差距（必须诚实记录）**：

1. **plan 鉴权/端点不匹配**：插件的 STT 走经典 `/api/v3/sauc/bigmodel`，用**经典控制台
   `app_id`+`access_token`**；LLM 默认走 `/api/v3`（用户明确禁止，会产生额外费用）。
   本用户只有 plan 单一 Key（`ARC_PLAN_API_KEY`）且要求走 `/api/v3/plan/...`。
   → **即使选 LiveKit，也大概率要自写/改写一个窄适配器指向 plan 端点**（本稿已实测出 plan 帧与鉴权，
   见 [providers.md](providers.md)）；或先确认插件是否接受 plan Key。
2. **TTS prosody 缺口**：语速/音量/音调未转发，风格预设的 prosody 需要自己补。
3. **Realtime 是另一条路线**：端到端模型自做 ASR+LLM+TTS，与本稿"任务面管策略、会话层管编排"不同；
   可作**独立备选**评估，不默认采用。
4. **供应链**：插件为社区维护、单一维护者、许可元数据缺失（PyPI `license: None`）→ 采用前须审源码许可；
   PyPI 存在**仿冒名** `livekit-plugins-volcenginee`（多一个 `e`），不得安装；版本须钉死并 vendor 审计。

### 2.2 抽象纯度对照（"可替换模型"）

- **Pipecat 最纯**：一个新供应商 = 实现 `run_stt()` 或 `run_tts()` 两个生成器方法之一；
  WS 断线重连/keepalive/打断管线由 `WebsocketSTTService`/`InterruptibleTTSService` 提供。
- **LiveKit 接近**：实现 `_recognize_impl` + `RecognizeStream._run` / `ChunkedStream._run`；
  已有豆包实现可直接用/改写。
- **结论**：若"可替换 + 少造轮子"压过许可纯度 → **LiveKit Agents（主选）**；
  若"许可无附加 + 完全自有适配器"压过时间 → **Pipecat（备选）**。
  两条路都必须先过 [validation-plan.md](validation-plan.md) VO01–VO03（同一端口套件跨适配器）。

### 2.3 plan 变体的官方依据与"别造轮子"

- 官方页：[Agent Plan 接入语音模型（企业版）](https://docs.volcengine.com/docs/82379/2516290) /
  [个人版](https://docs.volcengine.com/docs/82379/2516286)。鉴权为**单一"专属 API Key"放 `X-Api-Key`**
  + `X-Api-Resource-Id`（`seed-tts-2.0` / `volc.seedasr.sauc.duration`）+ `X-Api-Connect-Id`；
  ASR 另带 `X-Api-Sequence: -1`。**没有** `X-Api-App-Id/Access-Key`。
  与标准端点的差异只有**路径前缀与鉴权**；Resource-Id、二进制帧、JSON 负载一致；计费改 AFP。
- **官方样例即完整 Python 客户端**（含 `protocols.py`、双向 TTS、单向流 TTS、HTTP NDJSON、
  aiohttp ASR 客户端）——内嵌在上述 plan 文档页里；另有官方 TTS 双向协议 zip
  （`protocols_.py`）。**结论：适配器应移植官方样例，不自行发明帧格式。**
- **没有**面向这些 WS 端点的官方 pip SDK（`volcengine-python-sdk` 是 Ark LLM SDK；语音 SDK 仅移动端）。
- 社区：Pipecat **无**豆包支持；LiveKit 有社区插件（`Decent9967/livekit-plugins-volcengine` 等），
  目标是 `bigmodel_async` + `tts/bidirection` 的**标准**端点，**均不指向 `/plan`**。
  TEN 的豆包扩展支持**未核实**（文档站 JS-only，勿据此宣称）。

## 3. 可复用的构建块（去重清单）

| 构件 | 选型 | 版本/许可 | 备注 |
|---|---|---|---|
| **VAD** | Silero VAD（`snakers4/silero-vad`） | v6.2.1 / **MIT** | 事实标准；PyTorch + ONNX；16 kHz/8 kHz |
| | webrtcvad | 2.0.10 / MIT | 冻结、C 扩展，仅作基线 |
| | TEN VAD | v1.0-ONNX / Apache-2.0+条款 | 更小更快，16 kHz only；许可有附加条款 |
| **轮次/端点检测** | LiveKit `inference.TurnDetector` | 随 `livekit-agents`；**权重另有 Model License** | 已是 `AgentSession` 默认；旧 `livekit-plugins-turn-detector` **已废弃** |
| | `pipecat-ai/smart-turn` v3.2 | **BSD-2-Clause** | 音频原生（含韵律）、**支持中文**、可 CPU；许可最干净 |
| | TEN Turn Detection | Apache-2.0+条款 | Qwen2.5-7B 文本分类，含 wait 态；较重 |
| **传输** | WebRTC（LiveKit SFU / Pipecat SmallWebRTC） | Apache-2.0 / BSD | **barge-in 依赖 AEC**，WebRTC 原生自带；WS+Opus 仅原型，需自担抖动/丢包 |
| **打断策略** | 复用框架内建 | 见 §2 | 不自己写音频级打断 |
| **前处理** | 框架/平台 AEC/降噪 | — | 不自研 |

## 4. 推荐（倾向，非裁决）

- **主选：LiveKit Agents + `livekit-plugins-volcengine`**（"别乱造轮子"；已有豆包插件），
  但**必须先解决 plan 鉴权/端点差距**（§2.1 差距 1），并规避 Model License 锁定
  （可改用 Silero VAD + smart-turn 作为端点检测）。
- **备选：Pipecat**（BSD-2、抽象最纯，自写豆包适配器 ~2 文件）。
- **端到端 Realtime 路线**：单独评估，不默认采用。
- 选型须过 VO01–VO03 后才写入产品依赖；框架 commit/tag 与许可须固定记录（G2 要求）。

## 5. 来源（观察日期 2026-09-17；版本为快照，引用前复核）

| 编号 | 来源 | 用途 | 状态 |
|---|---|---|---|
| S1 | [livekit-plugins-volcengine · PyPI](https://pypi.org/project/livekit-plugins-volcengine/) | 插件版本/许可/Python/依赖范围 | 已核对 |
| S2 | [livekit-plugins-chinese · 火山引擎插件文档](https://di-osc.github.io/livekit-plugins-chinese/plugins/volcengine) | STT/TTS/LLM/Realtime 参数与默认端点 | 已核对 |
| S3 | [di-osc/livekit-plugins-chinese · GitHub](https://github.com/di-osc/livekit-plugins-chinese) | 插件源码/许可审计 | 待做（GitHub API 限流） |
| S4 | [livekit/agents](https://github.com/livekit/agents)（`stt.py`/`tts.py`/`llm.py`/`voice/turn.py`/`voice/speech_handle.py`） | 基类、打断、turn detection、preemptive generation | 已核对（源码） |
| S5 | [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat)（`services/stt_service.py`/`tts_service.py`/`frames/frames.py`） | `run_stt`/`run_tts`、`InterruptionFrame`、`COMMUNITY_INTEGRATIONS.md` | 已核对（源码） |
| S6 | [pipecat-ai/smart-turn](https://github.com/pipecat-ai/smart-turn) | 端点检测模型与许可 | 已核对 |
| S7 | [snakers4/silero-vad](https://github.com/snakers4/silero-vad) | VAD 版本/许可 | 已核对 |
| S8 | [TEN-framework/ten-framework](https://github.com/TEN-framework/ten-framework) + `bytedance_asr` 扩展 | 中文供应商矩阵、许可附加条款 | 已核对（许可需法务复核） |
| S9 | [volcengine/rtc-aigc-demo](https://github.com/volcengine/rtc-aigc-demo)、[volcengine/veadk-python](https://github.com/volcengine/veadk-python) | 官方 demo/工具链参照 | 待定版核对 |
| S10 | 本仓库实测探测（[providers.md](providers.md)、[probe_plan_endpoints.py](probe_plan_endpoints.py)） | Ark plan LLM、豆包 plan ASR/TTS 帧与鉴权、TTS→ASR 往返 | 已观测（少量样本） |
| S11 | [Agent Plan 接入语音模型（企业版）82379/2516290](https://docs.volcengine.com/docs/82379/2516290) / [个人版 82379/2516286](https://docs.volcengine.com/docs/82379/2516286) | plan 鉴权、五个 plan 端点、完整官方 Python 样例 | 已核对（官方文档内容 API） |
| S12 | 官方 ASR 协议文档 6561/1354869、ASR 2.0 文档 6561/2630027、6561/2628951、TTS 2.0 文档 6561/2532486、6561/2534913、6561/2528925、错误码 6561/2611432、6561/2534853 | 序列帧、字段、错误码、`context_texts`（无 `emotion`） | 已核对 |

## 6. 未决清单

- U1 plan 语音端点官方文档核对（尤其 ASR `audio.format` 合法取值、双向 TTS `TaskRequest` 语义）。
- U2 `livekit-plugins-volcengine` 是否支持 plan Key/plan Base URL；不支持时的自研适配器工作量与许可审计。
- U3 框架定版（固定 commit/tag）、许可记录与供应链（仿冒包、单一维护者）评估。
- U4 端到端 Realtime 路线 vs 两面编排路线的对照实验。
- U5 LiveKit turn-detector 的 Model License 锁定是否可接受；不接受则用 Silero + smart-turn 组合。
