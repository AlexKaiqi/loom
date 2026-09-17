# 语音助手：风格预设与"回答重点"的口语化渲染

状态：UNVERIFIED 设计稿。schema 为候选契约。
相关：[architecture.md](architecture.md)、[duplex.md](duplex.md)、
[task-directory-landing.md](../task-directory-landing.md) §4.6 示例 3 / §4.7（信息项 / 投影 / 呈现）。

## 1. 目标

用户要的不是"把答案念出来"，而是"**像人一样，先给结论和要点，细节按需展开**"。
语音是线性、不可跳读、打断成本高的通道：一次说 10 分钟等于交互失败。

因此"回答重点"必须是**结构造成的**，而不是靠模型自觉：
每轮给模型的上下文里**本来就没有全文**，只有要点 + 指针；要细节时靠工具按需取回
（对齐 v5:250 "不预先展开全量目录与全文"、v5:252 "裁剪只改可见视图，不删恢复依据"）。

## 2. 风格预设（Style Profile）

预设是**版本化产物**，当前生效的是**事实**（`voice.style.set{style_id, spec_ref, base_rev}`）。

```json
{
  "style_id": "brief-professional-zh",
  "label": "简短专业（中文）",
  "language": "zh-CN",
  "answer_mode": "key_points",          // key_points | full | adaptive
  "verbosity": {
    "max_spoken_seconds": 20,           // 口语时长预算（守卫用）
    "max_sentences": 4,
    "target_points": 3,                 // 目标要点数
    "detail_on_request": true           // "展开第二点"时再讲细节
  },
  "tone": "concise_professional",       // 口吻：专业/亲和/简短/活泼/严肃
  "spoken_form": {
    "markdown": "strip",                // 不念 ** / # / 表格
    "urls": "skip",                     // 不逐字符念链接
    "code": "summarize",                // 代码只说作用，不朗读符号
    "numbers": "normalize",             // 数字/单位口语化
    "lists": "prose"                    // 列表转成口语连接词
  },
  "expansion": {
    "offer": true,                      // 结尾给"要不要展开"的选项
    "granularity": "point"              // point | section | full
  },
  "prosody": {                          // → TTS 参数（见 §3.2 映射）
    "speech_rate": 0,                   // [-50,100]，100 = 2x
    "loudness_rate": 0,                 // 豆包 loudness_rate
    "pitch": 0,                         // 豆包 post_process.pitch，[-12,12]
    "style_instructions": ["用简洁、自然的语气说话"]   // 豆包 context_texts（自然语言风格指令）
  },
  "turn_taking": {                      // → 会话层端点/打断阈值
    "barge_in": true,
    "backchannel_min_ms": 200,
    "endpoint_silence_ms": 500
  },
  "provider_bindings": {
    "tts_provider": "doubao-seed-tts-2.0",
    "tts_voice": "zh_female_vv_uranus_bigtts"
  }
}
```

> **注意（供应商事实）**：`seed-tts-2.0` **没有 `emotion` 参数**（`emotion`/`emotion_scale` 属 TTS-1.0
> `*_mars_*` 多情感音色）。2.0 的风格走 `context_texts`（自然语言指令，不计费）、
> `model:"seed-tts-2.0-expressive"`、`use_tag_parser`（内联 COT 标签）与
> `speech_rate`/`loudness_rate`/`post_process.pitch`。见 [providers.md](providers.md) §2.4。
> 因此风格预设 schema **不固化 `emotion` 字段**——能力描述未声明该参数时不得下发。

预设的**边界**：

- 预设是**呈现/风格**，不改事实本身；同一事实可用不同预设渲染多次，各自留 revision。
- 预设变更**不从本轮中途生效**：带 `base_rev` 的条件受理，陈旧基线拒绝（landing §4.5）；
  正在说话的一轮用旧预设说完（v5:204 "不静默换策略"）。
- 预设里的 `provider_bindings` 必须与能力描述协商通过，否则会话开始即拒绝（不降级）。

## 3. 三层链路：全文 → 要点 → 口语

对齐 landing §4.7 的三层，逐层收窄，任何一层都不删依据：

| 层 | 落点 | 本任务里做什么 |
|---|---|---|
| **① 信息项（views）** | manifest `views` | 声明"全文/检索结果/工具输出/记忆摘要/当前轮状态"等可供展示项；有稳定 id、来源可定位、缺失显式 |
| **② 投影（projection）** | `roles.projection` | **选**最相关的 top-k 片段 + 给全文指针；注入"口语简报帧"；**不灌全文** |
| **③ 呈现（presentation）** | `roles.presentation` | 把风格预设编成 system prompt / 请求形式：只讲结论与 N 个要点、列表转口语、给展开选项 |

**呈现层的指令模板（候选，要点在约束而非修辞）**：

```
你是语音助手，正在与用户实时通话。
- 先给结论，再给最多 {target_points} 个要点；总时长不超过 {max_spoken_seconds} 秒。
- 只使用本轮提供的要点与事实；不得编造未提供的细节。
- 用户要求细节时，用提供的指针/工具取回后再讲。
- 输出是可朗读文本：不要 markdown、不要念链接、代码只说作用。
```

### 3.2 风格预设 → TTS 参数映射（豆包 seed-tts-2.0）

风格预设是**供应商无关**的意图；适配器把它翻译成具体参数，能力描述未声明的字段**不下发**：

| 预设意图 | 豆包 2.0 参数 | 备注 |
|---|---|---|
| 语气/表达风格 | `additions.context_texts: ["用…的语气说话"]` | 自然语言指令；2.0 音色可用、官方称不计费 |
| 更强表达力 | `model: "seed-tts-2.0-expressive"` | 与克隆音色/`context_texts` 搭配 |
| 内联风格标记 | `additions.use_tag_parser: true` + `<cot text=…>…</cot>` | 文本内嵌风格标签 |
| 语速 | `audio_params.speech_rate` `[-50,100]` | 100 = 2x |
| 音量 | `audio_params.loudness_rate` `[-50,100]` | |
| 音高 | `additions.post_process.pitch` `[-12,12]` | |
| 去 markdown/emoji | `additions.disable_markdown_filter` / `disable_emoji_filter` | TTS 侧再兜一层（呈现层仍应清洗） |
| 词级时间戳 | `audio_params.enable_subtitle` | 中文/英文；用于字幕与打断定位 |
| 方言 | `additions.explicit_dialect`（如 `beijing`/`sichuan`） | |
| **情感** | **不支持**（2.0 无 `emotion`） | 属 1.0 `*_mars_*` 多情感音色；不要下发 |

> 该映射属**适配器职责**，不属风格预设 schema；换 TTS 供应商只改适配器，预设与任务面不变。

## 4. 守门（guard）：预算超了就压缩，不是截断了事

模型仍可能超预算。`roles.logic` 在提交前做**有界**度量与收敛：

```
candidate = 模型候选口语文本
estimate  = 字符数 / 语言语速  → 预估秒数
if estimate <= max_spoken_seconds: 通过
else:
    pass2 = 一次"压缩为要点"的有界再生成（同一预算，最多 N 次）
    if pass2 仍超: 只播前 max_sentences 句 + 明确提示"细节随时展开"
    落 voice.reply.condensed{reply_id, from_ref, reason, budget, kept_ref}
```

规则：

- **压缩是有损渲染，不是删内容**：完整答案仍在 `content/`/artifact（版本化），
  `voice.reply.condensed` 记 `from_ref` + `kept_ref`，用户展开时可达（v5:252）。
- 预算与最大压缩次数是**配置**，不是硬编码常量；阈值不预设 SLA（v5:349）。
- 压缩失败（模型不可用等）→ 显式 `voice.reply.degraded{reason}`，不静默念全文。

## 5. 与双工的衔接

- 长回答 → 更容易被打断 → 预算约束同时服务"别念太长"和"打断点可控"。
- 用户打断后说"继续"：从 `kept_ref` 的断点续说，而不是从头念（[duplex.md](duplex.md) §2）。
- backchannel 不打断，但可用于"边听边嗯"的自然感（会话层回放，不入任务事实）。

## 6. 反例（不得变成什么）

- 把整篇文档塞进上下文再让模型"只讲重点"（没省 token，也没省时间，且容易漏）。
- 用截断代替压缩且不留引用（信息静默丢失）。
- 风格预设写死成 prompt 常量，用户改不了、换不了、无版本。
- 用"说完了"事件当业务完成（v5:161,208：没有通用终态）。
