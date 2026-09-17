# 语音助手：全双工会话设计

状态：UNVERIFIED 设计稿。框架选型待定向调研与独立用例后裁决（[research-notes.md](research-notes.md)）。
相关：[architecture.md](architecture.md)、[style-profiles.md](style-profiles.md)、[validation-plan.md](validation-plan.md)。

## 1. 真实性问题（为什么不能只做"按一下说一句"）

半双工（walkie-talkie）在真实对话里会立刻露馅：

- 用户想在助手说话时插一句"不是这个，是上一个"——半双工要么听不见，要么把助手的话当噪声；
- 用户说到一半停顿思考——固定静音阈值要么抢话，要么等太久；
- 助手说了一长段，用户已经知道答案——不能打断就只能等它念完。

全双工 = **边听边说 + 可打断 + 语义端点判定**。这三件事都有成熟开源实现，本设计只做"接缝与抽象"，
不自研音频算法。

## 2. 会话状态机（会话层持有，工作面只收事件）

```
        ┌──────────────────────────── reconnect ────────────────────────────┐
        ▼                                                                   │
   ┌─────────┐  speech_start   ┌───────────┐  turn_end   ┌──────────┐  first_audio  ┌──────────┐
   │ IDLE    │────────────────▶│ LISTENING │────────────▶│ THINKING │──────────────▶│ SPEAKING │
   └─────────┘                 └───────────┘             └──────────┘               └────┬─────┘
        ▲                            ▲                                                  │
        │ session_end                │ speech_start（barge-in）                          │
        │                            └─────────────── cancel TTS + flush playback ◀──────┘
        │                                                  （发 voice.user.barge_in）
        └──────────────────────────── session_end ───────────────────────────────────────┘
```

- **IDLE → LISTENING**：`speech_start`（VAD 触发，能量 + 模型双判）。
- **LISTENING → THINKING**：`turn_end`（语义端点判定，不是单纯静音计时）。
- **THINKING → SPEAKING**：TTS 首个音频帧可用即进入（不等整段生成）。
- **SPEAKING → LISTENING（barge-in）**：说话期间检测到用户语音 → `TtsStream.cancel()` +
  丢弃未播音频 + 落 `voice.user.barge_in{turn_id, at_ms, transcript_so_far?}`。
- **回退抑制（false barge-in）**：短促"嗯/对/好"等 backchannel 走 `TurnEvent.kind = "backchannel"`，
  默认**不打断**（阈值可配）；能量过低的瞬态噪声不打断。这条是"能打断"与"别太敏感"的平衡点。
- **重连**：transport 断开 → 保留会话事实、重建会话层连接；**不重放已播音频**（对齐 v5:332/336
  "未确认的结果不能靠猜测补齐"；已确认的已播音是事实）。

打断之后被截断的回复**不丢**：保留 `reply_id`、已播句子序号、完整文本引用与音频 artifact 引用，
用户说"继续"时可从断点续说（策略可配）。

## 3. 轮次检测（端点判定）

推荐组合（复用，不自研）：

| 组件 | 作用 | 候选实现 |
|---|---|---|
| VAD | 语音/非语音分段 | Silero VAD（`snakers4/silero-vad`，MIT）等 |
| 语义端点检测 | "这句说完了吗" | LiveKit turn-detector、Pipecat `smart-turn` 等 |
| 可选：语义 VAD | 用模型判断是否在思考 | LiveKit semantic VAD 一类 |

端点判定的**参数不是常量**：语言、语速、场景（免提/近讲）、是否允许抢话——这些归**风格预设**
（[style-profiles.md](style-profiles.md)）与会话层配置，不改工作策略。

## 4. 实时编排后端：接缝与选型

### 4.1 接缝（无论选谁都不变）

**编排框架**（被包进 `harness/ext/voice/`）通过一个**适配器**实现 [architecture.md](architecture.md) §2 的端口：

```python
class RealtimeOrchestrator(Protocol):
    async def start_session(self, cfg: "SessionConfig", ports: "PortBundle") -> "SessionHandle": ...
    async def stop_session(self, handle: "SessionHandle") -> None: ...
    def events(self) -> AsyncIterator["MediaEvent"]: ...

class SessionConfig(TypedDict):
    transport: dict          # webrtc | websocket | local_mic
    asr: AsrConfig
    tts: TtsConfig
    turn: dict               # VAD/turn 检测配置（来自风格预设）
    policy_bundle_ref: str   # 工作面下发的策略包（system prompt/工具/风格）
```

- **换编排后端 = 换 `RealtimeOrchestrator` 适配器**；换模型 = 换端口适配器。两者正交。
- 工作面只认 `voice.*` 事件与策略包，不 import 任何编排框架类型。

### 4.2 候选框架（调研已于 2026-09-17 完成，详见 [research-notes.md](research-notes.md) §2）

- **LiveKit Agents 1.8.2（主选）**：Apache-2.0（turn-detector 权重另有 Model License）；
  `STT._recognize_impl`/`TTS.ChunkedStream._run`/`LLM._run` 抽象；`SpeechHandle.interrupt()` +
  false-interruption resume + adaptive interruption；**已有豆包插件 `livekit-plugins-volcengine`**。
  坑：插件走经典 `app_id`+`access_token` 与 `/api/v3`，与 plan Key/plan 端点不匹配 → 需窄适配器。
- **Pipecat 1.10.0（备选，许可最干净）**：BSD-2-Clause；`STTService.run_stt`/`TTSService.run_tts`
  各只需一个抽象方法，`WebsocketSTTService`/`InterruptibleTTSService` 自带重连与打断；
  无豆包适配器，需自写 ~2 文件。
- **TEN 0.11.71（不采纳）**：中文供应商最全，但 Apache-2.0 **附加 Agora 非竞争条款**，且是需要
  Docker/TMAN 的多语言运行时，不是可嵌入 Python 库。
- **Vocode 0.1.113（不采纳）**：最后提交 2024-11-15，事实停更。

构建块：VAD = Silero VAD v6.2.1（MIT）；端点检测 = `pipecat-ai/smart-turn` v3.2（BSD-2，支持中文）
或 LiveKit `inference.TurnDetector`（权重受 Model License 限制）；传输 = WebRTC（barge-in 依赖 AEC）。

选型判据（预登记）：能否只用一个适配器接入本稿端口；打断/取消语义是否可观测且可测；
许可是否商用无碍（含模型许可与附加条款）；中文 ASR/TTS 适配成本；与本仓库 Python 栈和凭据纪律的兼容性。
**未完成独立用例（VO01–VO03）前不选定、不写入产品依赖。**

## 5. 会话层生命周期与零驻留

- 会话层是**助手 harness 自有的长驻组件**（`harness/ext/voice/runner.py`），由 runtime 按
  `extensions[kind=session-runner]` 声明起停（[assistant-work.md](assistant-work.md) §5）；
  它不写工作状态，只发事件。
- 会话活则 runner 在，`voice.session.ended` 即释放；**不是**"每个等待工作常驻一个 Agent"
  （v5:90 的反面）。共享媒体服务（如 WebRTC SFU、模型网关）可常驻，但不属本 work。
- 崩溃语义：runner 崩溃不回滚工作事实；未确认的轮次标为 `INCOMPLETE`/重连，不重放已播音
  （重放会把已确认的已播音当"未发生"，违反 v5:332/336）。
- 音频原件默认不常驻：按策略落 artifact（sha256）或只留文本与摘要；保留期单独裁决（Q-V5）。

## 6. 与"回答重点"的衔接

双工让"用户随时打断"成为常态，"回答重点"因此更重要：说太长会被打断，且打断成本高。
风格预设中的 `max_spoken_seconds`、`key_points_only`、`expand_on_request` 直接喂给：
① 端点/打断阈值（说多久开始允许抢话），② 口语化渲染守卫（见 [style-profiles.md](style-profiles.md) §3）。
