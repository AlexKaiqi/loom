# 语音助手：架构与语音能力抽象

状态：UNVERIFIED 设计稿。接口签名为**候选契约**，进组件合同时逐项裁决并经独立用例。
按用户 2026-09-17 裁决，语音**只属于助手 harness**：下面的"会话层/工作层"是**同一个 harness 内部**的
两层，不是 runtime 的两套设施；实例形态见 [assistant-work.md](assistant-work.md)。
相关：[README.md](README.md)、[assistant-work.md](assistant-work.md)、[duplex.md](duplex.md)、
[style-profiles.md](style-profiles.md)、[providers.md](providers.md)。

## 1. 助手 harness 内的两层

```
┌───────────────────────────────────────────────────────────────────┐
│ 助手 harness · 工作层（事件驱动、持久、策略；runtime 按 manifest 调用）│
│   词表 voice.* ｜ 受理 ｜ 触发 ｜ 投影/呈现 ｜ 逻辑/守卫             │
│   持：会话事实、风格预设引用、记忆、工具与安全策略、口语化渲染策略     │
│   不持：音频缓冲、连接、解码器、TTS 会话（都在会话层）              │
└───────────────▲───────────────────────────────┬───────────────────┘
       轮次级语义事件 / 软引用             策略包（system prompt、
   （transcript、reply 文本、时延、打断）    风格预设、工具 schema）
                │                               ▼
┌───────────────┴───────────────────────────────────────────────────┐
│ 助手 harness · 会话层 `harness/ext/voice/`（长驻实时，复用开源编排）│
│   runner.py：transport(WebRTC/WS) · Opus · 抖动缓冲 · VAD · 轮次检测│
│   · 流式 ASR · 流式 LLM · 流式 TTS · 打断/回退 · 重连              │
│   由 runtime 按通用机制起停（session-runner）；不写工作状态，只发事件│
└───────────────▲───────────────────────────────────────────────────┘
                │  统一端口（本稿定义的抽象）
┌───────────────┴───────────────────────────────────────────────────┐
│ 语音模型端口 Voice Provider Ports（可替换模型）                     │
│   SpeechToText · TextToSpeech · TurnDetector · ConversationModel   │
│   · AudioTransport ；适配器：doubao / ark / fake（离线）           │
│   实现位于 `harness/ext/voice/adapters/`（harness 自有，非框架设施）│
└───────────────────────────────────────────────────────────────────┘
```

**为什么 harness 内还要分两层**：runtime 的单位是有界 Round + 单写者提交 + 等待期零驻留
（v5:90、landing §6）。实时语音是连续音频流、亚秒级时序、随时打断——放进 Round 提交模型就要求
每个会话常驻一个进程。所以**实时在会话层（长驻、harness 自有），语义在工作层（按轮次）**；
两层都在助手 harness 内，runtime 只提供"起停 harness 声明的长驻会话组件"这一通用机制
（[assistant-work.md](assistant-work.md) §5）。会话层不直接改工作状态，只发事件经受理落面
（landing §4.4 E1/E2）。

## 2. 语音能力端口（可替换模型的关键）

端口是**本系统自己的窄接口**，不是某个开源框架的类型。编排框架（见 [duplex.md](duplex.md) §4）
是被适配的对象；换框架不改工作面，换模型不改编排。全部为异步、流式、可取消。

```python
# 候选契约（Protocol 为结构声明，运行期实现由适配器提供）

class AsrConfig(TypedDict):
    provider: str            # 例 "doubao-seed-asr-2.0"
    model: str               # 例 "volc.seedasr.sauc.duration"
    sample_rate: int         # 16000
    channels: int            # 1
    language: str            # "zh-CN"
    interim: bool            # 是否要 partial

class AsrEvent(TypedDict):
    kind: Literal["partial", "final", "error"]
    text: str
    definite: bool           # final 才算 definite
    seq: int                 # 单调，用于排序/去重
    ts_ms: int               # 相对会话起点
    words: list | None       # 可选词级时间戳（用于打断定位）

class SpeechToText(Protocol):
    async def open(self, cfg: AsrConfig) -> "AsrStream": ...

class AsrStream(Protocol):
    async def push(self, pcm: bytes, *, ts_ms: int) -> None: ...
    async def finish(self) -> None: ...           # 显式结束一轮
    async def cancel(self) -> None: ...            # 打断/放弃当前轮
    def events(self) -> AsyncIterator[AsrEvent]: ...

class TtsConfig(TypedDict):
    provider: str            # "doubao-seed-tts-2.0"
    model: str               # "seed-tts-2.0"
    voice: str               # 供应商音色 id（由能力描述校验）
    format: Literal["pcm", "mp3", "ogg_opus"]
    sample_rate: int
    style: "StyleParams"      # 见 style-profiles.md

class TtsEvent(TypedDict):
    kind: Literal["audio", "sentence_start", "sentence_end", "end", "error"]
    seq: int
    audio: bytes | None      # kind == "audio"
    text: str | None         # sentence_* 携带该句原文，便于字幕/对齐
    ts_ms: int

class TextToSpeech(Protocol):
    async def open(self, cfg: TtsConfig) -> "TtsStream": ...

class TtsStream(Protocol):
    async def push_text(self, text: str) -> None: ...   # 可多次，增量喂句
    async def finish(self) -> None: ...
    async def cancel(self) -> None: ...                 # 打断：立即停止出声
    def events(self) -> AsyncIterator[TtsEvent]: ...

class TurnEvent(TypedDict):
    kind: Literal["speech_start", "speech_end", "turn_end", "backchannel"]
    ts_ms: int
    confidence: float

class TurnDetector(Protocol):
    """VAD + 语义端点判定。实现可组合 VAD 模型与 turn-detector 模型。"""
    def push(self, pcm: bytes, *, ts_ms: int) -> list[TurnEvent]: ...
    def reset(self) -> None: ...

class ConversationModel(Protocol):
    """OpenAI 兼容流式补全（含 function calling），与 lore_work.provider 同族但必须支持流式。"""
    async def stream(self, messages, *, tools=None, style: "StyleParams", **kw) -> AsyncIterator[dict]: ...
```

### 2.1 能力描述与注册

端口实现者在注册表登记一条**能力描述**（capability descriptor）；会话开始时按声明做能力协商，
不匹配就**响亮拒绝**，不降级、不猜（对齐 landing §4.5 R2）：

```json
{
  "id": "doubao-seed-tts-2.0",
  "port": "tts",
  "adapter": "voice_doubao.tts",
  "models": ["seed-tts-2.0"],
  "formats": ["pcm", "mp3", "ogg_opus"],
  "sample_rates": [8000, 16000, 24000],
  "languages": ["zh-CN", "en-US"],
  "streaming": {"input": "incremental_text", "output": "chunked_audio", "cancel": true},
  "styles": {"emotion": ["neutral", "happy", "sad"], "speech_rate": [-50, 100]},
  "voice_catalog_ref": "artifact:sha256:…",
  "limits": {"max_concurrent_streams": 1},          // 实测填写，不预设
  "credential_ref": "env:ARC_PLAN_API_KEY"           // 只记名字，不记值
}
```

绑定落在 `work.json` 的引用里（`voice_refs`），与 `model_refs` 同族：**绑定 = 能力 id + 固定版本 +
能力描述 digest**。换模型 = 换绑定 = 新版本，走修订记录，一轮进行中不静默替换（v5:204、v5:349）。

### 2.2 换装纪律（可替换不是"接口存在"就算数）

可替换必须**可验证**，否则只是宣称。约定：

1. **一致性套件（conformance kit）**：同一套端口用例对每个适配器复跑——流式顺序、partial/final
   语义、取消后不再出声、错误分类、能力协商拒绝路径。离线用 `fake` 适配器做判据锚点。
2. **不透明标识钉定**：适配器把实测的供应商模型/音色回显钉成常量并校验；别名轮换**响亮失败**，
   不做前缀放行（沿用 `lore_provider` 的 `MODEL_ALIAS` 先例）。
3. **换模型留修订记录**：含独立理由、旧值保留、影响面与重跑范围（沿用
   `design/g3/provider/amendment-model-baseline-2026-09-*.md` 的格式）。
4. **"同套用例跨适配器产出同一组合同事实"作为通过判据**，而不是"两个都能跑"。

## 3. "谁生成要说的文本"：三案对比

语音的延迟预算把这个问题顶到台前。工作 runtime 的 Round 是"投影 → 模型 → 工具 → 提交"，
**提交点在轮末**；token 级流式产出若强行走事实流，会把原子提交模型捅穿（landing §6）。

| 案 | 谁生成回复文本 | 优点 | 代价 / 反例 |
|---|---|---|---|
| **R1 会话层生成** | 会话层 LLM 流式生成 | 首音频最快；工具调用由编排框架原生处理 | 工作面只当配置器，持久策略与回复内容脱节；回答"重点与否"靠 prompt 自觉 |
| **R2 工作面生成** | 工作 Round 生成完整回复后交会话层合成 | 事件权威最干净；策略在工作面 | 首音频要等整段生成；推理模型下不可接受（见 providers.md 实测） |
| **R3 混合（推荐）** | 会话层流式生成，**在一个工作下发的"策略包"约束下**；工作面在每轮后持久化并演进策略包 | 低延迟 + 策略在工作面 + 回复内容成为持久事实 | 需要"策略包"版本与生效边界；本轮产生的新上下文下一轮才生效 |

**R3 的边界规则（候选）**：

- 会话开始（`voice.session.started`）触发工作轮 → 产出 **`voice.session.configured`**：
  策略包引用（system prompt、风格预设 revision、工具 schema、记忆摘要、允许的行动集合）。
- 用户轮结束（`voice.user.turn.final`）→ 会话层在策略包约束下流式生成并播放；
  结束后落 **`voice.turn.completed`**（transcript、reply 文本引用、工具调用集、时延、是否被打断）。
- `voice.turn.completed` 触发工作轮 → 更新记忆/摘要，产出**新的策略包 revision**。
  **本轮不换策略**；新一轮生效（对齐 v5:204 "不在一次已开始的推进中静默换用新策略"）。
- 打断（`voice.user.barge_in`）是事实，不是取消工作推进；被打断的回复保留其引用与截断位置。
- 风格/身份等策略变更走 `voice.style.set{..., base_rev}` 条件受理，陈旧基线拒绝。

> **未决（需测量/裁决）**：R3 的"策略包一轮滞后"是否可接受，取决于工作轮时延与用户感知；
> 若不可接受，退化到 R1 并把策略包的生成放在会话开始 + 空闲期（不逐轮）。见
> [validation-plan.md](validation-plan.md) VO07/VO10。

## 4. 与 Loom runtime / 工作目录的接缝

| 关注点 | 归属 | 规则 |
|---|---|---|
| 音频分片（ASR partial、TTS chunk） | 会话层 + 观测域 | **不逐片进事实流**（流水爆炸）；按会话聚合，分片原件落 `session/` 或 artifact（软引用） |
| 轮次语义（transcript、reply 文本、时延、打断） | 工作层 | 经 Fact Admission 成为 `voice.*` 事实；幂等键 = `session_id + turn_id` |
| 策略包（prompt/风格/工具） | 工作层 `surface/content/` | 版本化产物，由事件引用 revision |
| 音频 artifact | F/artifact（摘要+引用） | 泛化 backend-seam §5a 的图像 artifact：落盘 → sha256 → 引用；不在事实里塞大字节 |
| 凭据 | 进程内存 + 仓库外 env | 只在适配器进程内读 `env:ARC_PLAN_API_KEY`；不落工作目录/证据/日志（glossary:100-102） |
| 会话进程 | harness 自有（T2，目录外） | 会话活则 runner 在，`voice.session.ended` 即释放；由 runtime 按通用机制起停；**工作不常驻专属进程**（v5:90） |
| 执行存活 | 机制在 runtime、策略在 harness | **默认到点发 `sys.tool.check`（不自动杀）**，harness 决定继续/取消/降级；runtime 保留硬上限与资源安全网（回收即 `abandoned/unknown`，不冒充未执行）；harness 声明分级默认与上限（[execution-timeouts.md](execution-timeouts.md)） |
| 业务时钟 | 机制在 runtime、策略在 harness | 日程用标准 crontab + 事件定义、谓词式时间用 `sys.clock`（[scheduling.md](scheduling.md)） |

## 5. 框架原语映射（详见 harness-catalog）

助手只用现有 P1–P8 通用原语即可表达；但暴露**五个**通用原语缺口（只登记，不新增领域目录）：

1. **harness 声明的长驻会话组件**（session-runner）：runtime 按事件起停/监督/释放一个 harness 自有组件，
   不理解音频。这是本设计唯一实际需要的框架新增机制（[assistant-work.md](assistant-work.md) §5）；
   在它落地前，runner 可由外部启动，harness 仍处理轮次级事件（降级路径存在）。
2. **出站投递/通知**：`voice.session.configured`（策略包）如何送达会话层/外部 runner
   （与 ask-user 的"对外通知/投递原语"同题）；若选 R2 方案，还需回复文本的投递。
3. **流式观测通道**：有序分片（ASR partial、TTS chunk）需要一个"分片+引用"的通用观测形态，
   否则只能各 harness 自造或把流水灌进事实流。
4. **二进制 artifact 通用化**：把图像 artifact 通道泛化为任意媒体 artifact（音频/视频）。
5. **runtime 调度机制**：接受标准 **crontab + 事件定义**（复用 bash 环境里的成熟调度工具，
   **不自定义语法、不重新实现**），到点落 `sys.schedule.fired`；另有 `sys.clock` 供谓词式时间。
   两条纪律：权威在工作数据（crontab 是派生物）、cron 只叫醒 runtime 不写事实
   （[scheduling.md](scheduling.md)）；monitoring、plan 截止、ask-user 超时共用。

（完整五件套与本工作的映射见 [../harness-catalog/voice-assistant.md](../harness-catalog/voice-assistant.md)。）

## 6. 开放问题

- **Q-V1**：策略包一轮滞后 vs 每轮重算的时延/质量权衡（需 VO07/VO10 测量）。
- **Q-V2**：部分 ASR（barge-in 时用户只说了半句）算不算一个用户轮？半句是否入记忆？
- **Q-V3**：多模态同时（用户边说边发图/文件）如何与双工会话合流。
- **Q-V4**：会话编排后端选型（Pipecat / LiveKit Agents / 其他）——见 [duplex.md](duplex.md) §4 与
  [research-notes.md](research-notes.md)；它被包在 `harness/ext/voice/`，选型须独立用例后再定。
- **Q-V5**：音频 artifact 的保留期与隐私（语音是生物特征，默认保留策略需单独裁决）。
