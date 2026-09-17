# 语音助手 Work：实时语音能力的抽象与工作定义

状态：**设计稿（UNVERIFIED）**。只做设计、调研与预登记用例；未实现、未验收，不声称任何能力通过。
来源：用户 2026-09-17 要求——"再设计一个语音助手 work；语音这里做好抽象（可替换模型）；
流式语音输入、语音输出（按用户预设风格，可回答重点而非朗读全部）；语音双工交流
（做好抽象，开源有成熟方案的，别乱造轮子）"。

**已完成的探索性观测（不是验收证据，单机少量样本）**：Ark plan `glm-5.3-flash` 流式可用
（`reasoning_effort:minimal` 显著降低首字延迟）；豆包 plan TTS 单向流式出声（首音频 ≈0.35 s）；
豆包 plan ASR 用序列帧跑通一次 **TTS→ASR 真实往返**（部分结果逐字增长，末帧 `definite:true`）；
plan 语音网关用 `X-Api-Key` 单一 Key 鉴权。细节与边界见 [providers.md](providers.md)。

相关：[harness-catalog/voice-assistant.md](../harness-catalog/voice-assistant.md)、
[work-directory-landing.md](../work-directory-landing.md) §4.3–4.7（五件套、P1–P8、信息项/投影/呈现）、
[../../backlog.md](../../backlog.md) B16、[docs/validation-status.md](../../../docs/validation-status.md)。

## 已确认的定义（用户 2026-09-17 裁决）

1. **长期关系 = 一个 work**：助手是**长期 work**；一次会话是 work 内的 `session` 区间，
   `voice.session.ended` 不等于 work 完成（像 monitoring 一样长期在册、空闲不驻留）。
2. **语音只属于助手 harness**：端口/适配器/会话编排放在 `harness/ext/voice/`，
   **不新增框架设施**；代价是语音能力不可被其他 harness 直接复用（有意的隔离换简单）。
3. **要落在工作目录里**：具体实例形态见 [assistant-work.md](assistant-work.md)
   （目录解剖、会话事件流、与 runtime 的唯一通用机制、生命周期）。

> 三层"定义"要分清：**Assistant Profile**（人格/风格/策略/语音绑定，用户可改）→
> **Assistant Harness**（推进策略 + 语音机制，登记后只读）→ **Assistant Work 实例**（状态与记忆）。

## 这个工作要治的病

1. **语音能力绑死一家模型**：ASR/TTS/LLM 直接写死在编排代码里，换供应商要动业务逻辑。
2. **把整段答案朗读出来**：语音是线性、不可跳读的通道；把文档全量转成语音既慢又没用，
   用户要的是**结论与要点**，细节按需展开。
3. **只会"你说完我再答"（半双工）**：不能打断、不能插话、不能边听边说。
4. **重造音频轮子**：自己写 WebRTC/Opus/抖动缓冲/VAD/端点检测，既难验证又违背成熟复用。

## 范围

**做**：

- 语音能力端口抽象（ASR / TTS / 轮次检测 / 对话模型 / 音频传输）与**可替换模型**的换装纪律；
- 流式语音输入（partial → final）与流式语音输出（首音频尽早、可取消）；
- 用户预设**说话风格**（风格预设）与"**只讲重点、细节按需展开**"的口语化渲染链路；
- **全双工**会话：打断（barge-in）、轮次检测、回退与重连，抽象到可替换的实时编排后端；
- **对话记录**：目录化的原始音频 + 元数据，按端点切成片段，语音/文本同构，预留语气/情绪/人物识别扩展位；
- 与 Loom 工作目录/runtime 的接缝（事件、事实、投影、权限、凭据），以及可执行的验证计划。

**不做**（非目标，防止把设计变成平台）：

- 不自研音频传输、编解码、抖动缓冲、回声消除、VAD 模型（复用成熟开源方案）；
- 会话组件（runner）不直接写工作状态：只经事件入口落事实，不绕开受理与单写者；
- 不把语音做成框架级通用设施（本轮裁决②）；也不定义通用"语音终态"、不把"说完了"当业务完成（v5:161,208）；
- 不在工作目录、证据或日志里放密钥（对齐 glossary:100-102）；
- 不在本稿确定具体容量/SLA 数字；延迟目标先测量再定（对齐 v5:349 "毫秒级 SLA 不冻结"）。

## 文件索引

| 文件 | 内容 |
|---|---|
| [events.md](events.md) | **词表 + 契约**：该定义哪些事件、哪些根本不是事实、产生者/触发/幂等键、最小闭环集合 |
| [scheduling.md](scheduling.md) | **定时与日程**：日程归助手、机制归 runtime；runtime **复用标准 crontab + 事件定义**（不自定义、不重实现）；两条纪律（权威在工作数据 / cron 只叫醒不写事实）；`sys.clock` 谓词式时间；`adapter.error` 归属；§3.1 调度后端选型 |
| [execution-timeouts.md](execution-timeouts.md) | **执行存活检查**：默认到点发 `sys.tool.check`（**不自动杀**），怎么办归 harness；runtime 保留硬上限与资源安全网（回收即 `abandoned/unknown`）；超时≠未执行；为什么不做逐次提醒；in-band `timeout` 只是纵深 |
| [conversation-record.md](conversation-record.md) | **对话记录**：目录化的原始音频 + 元数据、双工端点切片、文本/语音同构、语气/情绪/人物识别扩展位；**权威在事件、目录是物化**（§6） |
| [assistant-work.md](assistant-work.md) | **实例形态**：一个助手 = 一个长期 work 的目录解剖、会话事件流、语音在 `harness/ext/voice/`、生命周期、归属问题 |
| [latency-and-curation.md](latency-and-curation.md) | **及时响应 vs 知识维护**：同一 work 内两个策略实例（会话循环/维护循环）、延迟预算与削减手段、用户空间认知、维护时机（会话边界/变更/阈值/空闲）、一致性边界 |
| [architecture.md](architecture.md) | 助手 harness 内的会话层/工作层、端口与适配器、注册与能力协商、"谁生成要说的文本"三案对比 |
| [duplex.md](duplex.md) | 双工状态机、打断语义、轮次检测、实时编排后端的接缝与选型、会话资源零驻留 |
| [style-profiles.md](style-profiles.md) | 风格预设 schema、"回答重点"的三层链路（信息项/投影/呈现）+ 守门与无损引用 |
| [providers.md](providers.md) | 具体适配规范：Ark `glm-5.3-flash`、豆包 ASR/TTS 2.0（含 2026-09-17 实测观测，不含密钥） |
| [validation-plan.md](validation-plan.md) | 预登记验证用例与证据要求（未执行） |
| [research-notes.md](research-notes.md) | 开源实时语音框架与协议调研来源、结论与未决 |
| [probe_plan_endpoints.py](probe_plan_endpoints.py) | **探索性**探针（非证据）：实测 plan LLM / 豆包 TTS 单向 / ASR；只打印变量名不打印密钥 |

## 核心判断（一句话版）

**助手 = 一个长期工作（harness 拥有策略与语音）+ 若干会话区间 + 一层可替换的语音模型端口；
runtime 只按通用机制起停 harness 声明的长驻会话组件。** 音频不进事实流逐片落库；进工作面的是
**轮次级**语义事件与软引用。"回答重点"是**投影/呈现策略**，不是删内容——被压缩的是可见视图，
完整答案仍有版本化依据（v5:252）。

## 追溯

| 本稿判断 | 来源 |
|---|---|
| **长期关系 = 一个 work；语音只属于助手 harness；落在工作目录** | **用户 2026-09-17 裁决** |
| 会话组件（runner）由 runtime 按通用机制起停、空闲释放 | v5:90（等待期零驻留）；[assistant-work.md](assistant-work.md) §5–6 |
| 音频不进事实流逐片落库 | v5:131/149（事件可作输入视图、输入边界固定）；landing §4.4 情况 2 |
| 端口化换模型、能力协商、响亮拒绝 | `lore_provider` 既有换基线纪律（design/g3/provider/amendment-model-baseline-*.md）；glossary:43（harness 登记后只读） |
| "只讲重点"是投影/呈现而非删内容 | work-directory-landing §4.6 示例 3（archive 只缩视图）、§4.7（信息项/投影/呈现三层）、v5:252 |
| 用户配置与模型产物分家（风格/边界 vs 记忆/表达） | [assistant-work.md](assistant-work.md) §7；landing §4.4 E5（内容不是侧信道） |
| 风格预设/策略不在一轮中途静默替换 | v5:204、v5:349；landing §4.5 R2/R3 |
| 凭据在仓库外、进程内 | glossary:100-102；`~/.env` 变量名 `ARC_PLAN_API_KEY`（值不落库） |
| 二进制 artifact 走摘要+引用 | design/g3/x/backend-seam.md §5a（图像 artifact 模式的泛化） |
