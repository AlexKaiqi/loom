# Harness Runtime：开源项目参考与调研清单

**整理日期：2026-09-12**  
**状态：调研计划；项目简介已对照官方仓库，尚未逐项完成源码审查与运行验证。**

## 1. 范围与调研依据

本清单汇总此前讨论，不修改 Harness Runtime v5，也不据此新增 Runtime 的业务接口。

**主清单 12 个：** 用户点名的 Codex、Pi、DeepSeek Harness、SoL-Pi，以及此前建议补充的 mini-swe-agent、OpenHands Software Agent SDK、OpenSandbox、DBOS、Harbor、Anthropic Sandbox Runtime、AgentFS、OpenClaw。

**Grok Bot 方向保留 3 个候选：** OpenMausBot、Rakazo、OpenBot。目前尚未确认用户最初记得的是哪一个；候选身份不等于三个项目必须全部深入调研。

**另外单列：** NATS JetStream 是此前已提出的事件底座专项；Daytona 仅作为历史公开实现参考。DBOS 的 Python/TypeScript 仓库按一个项目计，OpenHands automation 作为 OpenHands 的关联仓库，不重复计数。

调研依据沿用用户确认的核心目标：**Runtime 与 Harness 彻底拆开，Harness 降级为外部推进定义。** Runtime 提供事件底座、Surface、任务环境沙箱、解释 Harness 并执行推进四项契约；Harness 定义“模型看什么”和“怎么推下去”。价值仍是多策略原生并存与解耦演进、等待期任务专属资源归零与弹性伸缩，以及持久状态支撑长程恢复。

表中的“简介”来自项目维护方说明；“重点调研”是针对本项目提出的问题，不表示对方已经满足我们的契约。保留用户原来的研究取向：Codex 重点看产品与工程体验，Pi 重点看简单风格，DeepSeek Harness 重点看现有局部能力与插件边界；不把这些偏好写成未经验证的质量排名。

## 2. Agent 与 Harness：最简推进、上下文与产品体验

| 项目与仓库 | 简单介绍 | 重点调研哪些能力 |
| --- | --- | --- |
| **Codex** — [openai/codex](https://github.com/openai/codex) | OpenAI 的开源本地 coding agent，仓库包括终端入口与 Rust 实现；开源仓库范围不等于整个 Codex 商业产品。[1] | **产品与执行体验：** 用户如何发起、干预和继续任务，执行过程如何展示；**运行边界：** 会话、工具执行、权限检查和客户端之间如何分工；**可复用部分：** 哪些工程能力能独立于其既有推进策略复用。 |
| **Pi Agent** — [earendil-works/pi](https://github.com/earendil-works/pi) | Agent 工具集，包含 coding agent CLI、agent core 和统一多模型 API；原 `badlogic/pi-mono` 目前重定向至该仓库。[2] | **极简核心：** Loop、工具、上下文和 Session 分别有多小；**外部扩展：** 如何通过扩展或回调替换策略而不改核心；**恢复边界：** Session 保存哪些内容、哪些仍依赖活进程；哪些机制适合最简 Harness。 |
| **DeepSeek Harness** — [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) | DeepSeek 的开源 agent harness，命令名 `dsh`，采用 Cordis 驱动的全插件架构。[3] | **既有能力复用：** `dsh session` 实际保存和维护哪些模型、执行及文件记录；**插件边界：** 插件生命周期、依赖、配置、事件交互；**取舍：** 哪些运行职责已具备，哪些抽象增加了不必要的耦合或认知成本。 |
| **mini-swe-agent** — [SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) | 极简软件工程 agent，以 Bash 为主要交互，Agent、Model、Environment 分开，保留简单的线性历史。[4] | **最小可运行闭环：** 上下文如何形成、命令如何解析、结果如何反馈；**接口删减：** 哪些能力不需要专属工具；**与我们对接：** 环境适配能否接入双 Shell，历史记录如何与 Surface、Session 分工。 |
| **SoL-Pi** — [NVlabs/SoL-Pi](https://github.com/NVlabs/SoL-Pi) | NVIDIA 维护的 Pi 独立扩展，通过公开扩展接口提供操作与验证合并、工具输出按需召回、保留证据的日志精简和上下文压缩。[5] | **投影与裁剪：** 大输出如何保存、召回，压缩怎样保留证据；**推进效率：** 减少模型轮次是否损害验证和纠错；**解耦扩展：** 这些机制是否可独立挂载；如何通过对照实验确认收益。 |

**本组要得到的结论：** 最简 Harness 应保留哪些推进定义，哪些能力可以直接复用，哪些专属工具与状态机制没有必要引入。

## 3. Agent 宿主与持续交互产品：本地、服务器和多端之间怎样分工

| 项目与仓库 | 简单介绍 | 重点调研哪些能力 |
| --- | --- | --- |
| **OpenHands Software Agent SDK / Agent Server** — [OpenHands/software-agent-sdk](https://github.com/OpenHands/software-agent-sdk)；关联 [OpenHands/automation](https://github.com/OpenHands/automation) | 提供 Agent SDK、工具、Workspace 和 Agent Server，支持本地及临时环境中的执行；关联 automation 仓库负责调度、Webhook 和运行分发。[6] | **层间边界：** SDK、Server、Workspace、调度怎样交接；**远程运行：** 同一策略如何切换执行环境；**状态责任：** 运行结果、事件、恢复依据分别由谁持有；尤其比较其 Agent/工具部署方式与我们的双 Shell 边界。 |
| **OpenClaw** — [openclaw/openclaw](https://github.com/openclaw/openclaw) | 可自托管的个人助手，通过 Gateway 连接聊天渠道、会话与工具，并支持替换模型及 agent harness。[7] | **产品连续性：** 用户离开后怎样接收输入、触发运行、返回结果；**状态划分：** 上下文文件、记忆、Session、凭证如何分开；**资源模型：** 常驻 Gateway 与每个任务运行实例如何区分，能否避免任务专属进程长期占用。 |

**本组要得到的结论：** 用户可以持续接触同一个 Agent，不必意味着同一个任务进程或沙箱始终存在。需通过实现和实验验证，不从“可云端部署”直接推导 Scale to Zero。

## 4. 执行环境与文件状态：哪些底层机制可以复用

| 项目与仓库 | 简单介绍 | 重点调研哪些能力 |
| --- | --- | --- |
| **OpenSandbox** — [opensandbox-group/OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) | 面向 AI 应用的沙箱平台，分开定义生命周期与执行接口，支持 Docker/Kubernetes 运行环境及命令、文件、网络相关能力。原 `alibaba/OpenSandbox` 重定向至当前仓库。[8] | **环境生命周期：** 创建、复用、停止、销毁与重建；**执行契约：** 用户、cwd、挂载、网络、凭证和资源如何落实；**结果确认：** 执行身份、输出、超时、取消和断线后查询；哪些可以只在 Runtime 内部薄适配。 |
| **Anthropic Sandbox Runtime** — [anthropics/sandbox-runtime](https://github.com/anthropics/sandbox-runtime) | 轻量进程沙箱组件，通过操作系统机制限制文件与网络访问，可作为库或 CLI 使用；当前标注为研究预览。[9] | **Runtime Shell 限权：** 如何只允许访问自己的 Surface 而不变成宿主高权限 Shell；**进程树与端点：** 子进程、socket、凭证和 FD 的实际边界；**适用范围：** 本地进程约束与完整多租户任务沙箱还差哪些保障。 |
| **AgentFS** — [tursodatabase/agentfs](https://github.com/tursodatabase/agentfs) | SQLite 支撑的 agent 文件系统，提供 SDK 与文件系统挂载方式；当前处于 Beta。[10] | **普通文件接口：** Bash/Python 是否可自然使用，语义兼容性如何；**版本与恢复：** 快照、追溯、迁移覆盖哪些状态；**采用成本：** 与普通目录加 Git/已有快照相比，是否确有必要；不能因此把 Surface 改成数据库对象接口。 |

**本组要得到的结论：** 双环境、执行身份、权限和恢复范围如何真正落地，而不是增加一组模型可见的底层管理命令。

## 5. 持久推进与策略评测：对应长程可靠性和多策略演进

| 项目与仓库 | 简单介绍 | 重点调研哪些能力 |
| --- | --- | --- |
| **DBOS** — [dbos-inc/dbos-transact-py](https://github.com/dbos-inc/dbos-transact-py)；[dbos-inc/dbos-transact-ts](https://github.com/dbos-inc/dbos-transact-ts) | 基于 Postgres 的持久执行库，将普通函数组织成 workflow/step，提供步骤记录、队列、定时与持久通知。[11] | **外部推进定义：** 普通代码怎样由底座持续承担执行责任；**恢复：** 已完成步骤怎样复用，重试和未知结果如何处理；**等待：** 条件与继续位置如何保存，等待时是否仍占用任务进程；明确其要求与我们的最简契约是否相容。 |
| **Harbor** — [harbor-framework/harbor](https://github.com/harbor-framework/harbor) | Terminal-Bench 创建团队的 Agent 评测框架，支持不同 Agent、自定义任务/环境及并行实验。原 `laude-institute/harbor` 重定向至当前仓库。[12] | **多策略可比性：** 固定任务、初始文件、环境、模型与预算，只替换 Harness；**独立验收：** 检查产物而非相信 Agent 自述；**实验记录：** 轨迹、费用、耗时、失败归因和回归；如何放在 Runtime 外部验证策略。 |

**本组要得到的结论：** 推进责任能否不依赖活进程，以及策略替换后的收益能否被独立检验。研究某个持久执行库不等于决定采用它的全部工作流抽象。

## 6. Grok Bot 方向：原项目身份仍待确认的三个候选

| 项目与仓库 | 简单介绍 | 重点调研哪些能力 |
| --- | --- | --- |
| **OpenMausBot** — [milind-soni/OpenMausBot](https://github.com/milind-soni/OpenMausBot) | 自称开源 Grok Bot 替代；本地优先的聊天式应用，接入不同 agent，并让 bot 使用电脑环境。[13] | **产品组织：** Bot、对话、文件、执行画面与审批怎样呈现；**运行分工：** 本地 agent 驱动与远端电脑之间怎样交互；**适用范围：** 哪些能力真正在云端，哪些仍依赖用户设备。 |
| **Rakazo** — [elie222/rakazo](https://github.com/elie222/rakazo) | 持续 AI 队友平台，通过 Pi 接入模型，支持不同电脑/沙箱提供方；后端可在服务器运行，网页、桌面与手机作为客户端。[14] | **云端连续性：** 关闭客户端后任务如何继续；**长期状态：** 对话、记忆、routines 与执行状态如何分开；**弹性：** Bot 长期存在与沙箱生命周期能否解耦；**替换边界：** 更换模型和执行后端需要改哪些层。 |
| **OpenBot** — [CopilotKit/OpenBot](https://github.com/CopilotKit/OpenBot) | 可自托管的 AI coworkers 应用模板，每个 bot 有电脑、浏览器和文件，通过 AG-UI 接入不同 agent。维护方明确它是供克隆定制的模板，而非现成托管产品。[15] | **宿主中立性：** 不同 agent 怎样接入同一产品；**人机协作：** 操作前授权、执行后记录、人工接管与交还；**状态与资源：** Bot、电脑、运行历史怎样关联；是否必须接受其协议才可复用。 |

这三个项目研究的是持续、可远程接触的 Agent 产品形态，不因为用了“Grok Bot”名称就预设底座与我们相同。Rakazo 先看服务器连续运行；OpenMausBot 先看交互与本地/远端分工；OpenBot 先看可替换 agent 与受控操作。此顺序是本清单的建议，不是项目性能排名。

## 7. 已有底座专项与历史参考

| 项目与仓库 | 定位及状态 | 重点调研哪些能力 |
| --- | --- | --- |
| **NATS JetStream** — [nats-io/nats-server](https://github.com/nats-io/nats-server) | 此前已经提出的事件底座候选，不是本轮额外增加的 Agent 框架。JetStream 提供持久消息流与消费者能力。[16] | 命名空间与授权；提交确认；历史读取/回放；消费位置与重复交付；保留范围；怎样向 Harness 注入文件视图；怎样由薄提交入口校验请求，而不暴露消息中间件管理能力。 |
| **Daytona：历史参考** — [daytonaio/daytona](https://github.com/daytonaio/daytona) | 历史公开的 AI 代码执行基础设施。仓库声明自 2026 年 6 月起核心开发转入私有代码库，该公开仓库不再接收更新、修复或发布。[17] | 只研究公开版本中可见的环境创建、隔离、持久文件与生命周期设计。不能把现行商业产品能力直接算入公开实现，也不作为本轮持续跟踪开源底座的首选。 |

Git、OCI、Linux 文档，以及此前契约讨论引用的其他框架，继续作为专题依据。不能因为曾经引用某项技术，就自动把它升级为本轮必须深入调研的项目；这里不扩张清单。

## 8. 调研与现有设计的对应关系

下表是我们的研究分工，不是对各项目实现合规性的结论。

| 要回答的问题 | 首要研究对象 |
| --- | --- |
| 最简 Harness 到底只需定义什么？ | Pi、mini-swe-agent；DeepSeek Harness 对照已有 Session 能力。 |
| 怎样保留强产品体验，而不把既有策略固化进底座？ | Codex；OpenClaw；Grok Bot 候选。 |
| 上下文与工具输出怎样裁剪而不丢失必要证据？ | SoL-Pi、Pi、mini-swe-agent。 |
| 两套 Shell、实际执行环境与权限怎样由 Runtime 落实？ | OpenSandbox、Anthropic Sandbox Runtime；OpenHands 对照远程运行分工。 |
| 事件交付和继续责任怎样持久保存？ | NATS JetStream、DBOS；OpenHands automation 对照触发与分发。 |
| Surface 保持普通目录后，版本和恢复怎样做？ | AgentFS 与既有 Git/快照方案比较；不预先选定额外文件系统。 |
| 同一任务换 Harness 后，怎样验证收益？ | Harbor，配合固定任务和独立验收。 |

## 9. 每个项目的调研交付口径

每个项目最终留下：**职责与状态归属说明、一个与我们有关的可复现实验、可复用模块或接口位置，以及不采纳的设计及原因。** 运行结果必须区分“README 声称”“源码支持”“实际验证”；记录对应提交版本，不以移动的默认分支作为永久依据。

优先把最简 Harness、双环境执行、事件输入/提交这条路径跑通，再验证保存后停止、重启继续与必要权限边界。多 Surface 拓扑不作为首个样例前置条件。

复用代码前单独核查目标版本、许可证与第三方依赖；公开仓库和可参考的架构，不等于整个商业产品或所有目录都允许相同方式的复用。

## 10. 核对来源

以下是本轮介绍的依据，均为维护方仓库或官方文档。调研问题是结合用户设计提出的计划，不由这些页面证明。

[1] [Codex 官方仓库](https://github.com/openai/codex)。  
[2] [Pi 官方仓库](https://github.com/earendil-works/pi)；[旧地址重定向](https://github.com/badlogic/pi-mono)。  
[3] [DeepSeek Harness 官方仓库](https://github.com/deepseek-ai/deepseek-harness)。  
[4] [mini-swe-agent 官方仓库](https://github.com/SWE-agent/mini-swe-agent)。  
[5] [SoL-Pi 官方仓库](https://github.com/NVlabs/SoL-Pi)。  
[6] [OpenHands Software Agent SDK](https://github.com/OpenHands/software-agent-sdk)；[OpenHands automation](https://github.com/OpenHands/automation)。  
[7] [OpenClaw 官方仓库](https://github.com/openclaw/openclaw)。  
[8] [OpenSandbox 当前仓库](https://github.com/opensandbox-group/OpenSandbox)；[旧地址](https://github.com/alibaba/OpenSandbox)。  
[9] [Anthropic Sandbox Runtime 官方仓库](https://github.com/anthropics/sandbox-runtime)。  
[10] [AgentFS 官方仓库](https://github.com/tursodatabase/agentfs)。  
[11] [DBOS Python](https://github.com/dbos-inc/dbos-transact-py)；[DBOS TypeScript](https://github.com/dbos-inc/dbos-transact-ts)。  
[12] [Harbor 当前仓库](https://github.com/harbor-framework/harbor)；[旧地址](https://github.com/laude-institute/harbor)。  
[13] [OpenMausBot 仓库](https://github.com/milind-soni/OpenMausBot)。  
[14] [Rakazo 仓库](https://github.com/elie222/rakazo)，重点为 README 的功能与服务器部署说明。  
[15] [OpenBot 仓库](https://github.com/CopilotKit/OpenBot)，重点为模板定位、agent 接入及架构说明。  
[16] [NATS Server](https://github.com/nats-io/nats-server)；[JetStream 官方文档](https://docs.nats.io/concepts/jetstream)。  
[17] [Daytona 历史公开仓库](https://github.com/daytonaio/daytona)，维护状态说明。

## 11. 2026-09-15 增补：执行编排与沙箱底座相邻身份（用户简报五项）

用户简报指出开源界对"LLM 编排层 + 隔离执行沙箱"已有成熟实现，点名 OpenHands 应用本体、SWE-agent、AutoCodeRover、E2B、Daytona，并附一套 MVP 技术栈建议。本节只登记身份与调研记录入口，不改动上文主清单口径与历史记录。

| 项目与仓库（2026-09-15 观测地址） | 钉定版本 | 与主清单的关系 |
| --- | --- | --- |
| **OpenHands 应用本体** — [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands)（原 All-Hands-AI） | v1.18.0 | §3 已列其 SDK 重写版 software-agent-sdk；本项为 v1 事件流应用本体，双轨并行 |
| **SWE-agent** — [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent)（原 princeton-nlp） | v1.1.0 | §2 已列其极简衍生 mini-swe-agent；本项为 ACI 提出者父项目 |
| **AutoCodeRover** — [AutoCodeRoverSG/auto-code-rover](https://github.com/AutoCodeRoverSG/auto-code-rover)（原 nus-apr） | v1.1.0 | 新候选：AST 结构检索 + 测试反馈闭环，Harness 策略层对照 |
| **E2B** — [e2b-dev/E2B](https://github.com/e2b-dev/E2B)（SDK）与 [e2b-dev/infra](https://github.com/e2b-dev/infra)（自托管底座） | @e2b/python-sdk@2.49.1 | 新候选：Firecracker microVM 云沙箱服务，D-X-SEAM-001 远端后端的公开同构物 |
| **Daytona** — [daytonaio/daytona](https://github.com/daytonaio/daytona) | v0.190.0 | §1 原标注"历史公开实现参考"，现转为正式候选；与 §4 OpenSandbox 同位，择一深查 |

调研记录（职责与状态归属、可复用位置、不采纳/适配缺口、拟验证实验、纠错与核对来源）：[design/g2/execution-platforms-survey-2026-09-15.md](design/g2/execution-platforms-survey-2026-09-15.md)。该记录为文档级调研：版本钉定来自 releases/latest 重定向页（GitHub API 本轮限流，未取得 commit SHA），架构结论均为 README/官方页声称级，源码审查与运行实验后置。

[18] [OpenHands releases/latest](https://github.com/OpenHands/OpenHands/releases/latest)；[19] [SWE-agent releases/latest](https://github.com/SWE-agent/SWE-agent/releases/latest)；[20] [AutoCodeRover releases/latest](https://github.com/AutoCodeRoverSG/auto-code-rover/releases/latest)；[21] [E2B releases/latest](https://github.com/e2b-dev/E2B/releases/latest)；[22] [Daytona releases/latest](https://github.com/daytonaio/daytona/releases/latest)。

## 12. 2026-09-15 增补：Cursor Cloud Agent 产品形态参照

用户确认 Cursor Cloud Agent（早期名 Background Agents）即目标形态：云端 Harness + 每任务隔离 VM 沙箱 + 异步端到端交付（环境构建→修改→测试/自修→录屏产物→PR）+ 自托管沙箱选项。产品不开源，登记为**形态与机制参照**（非代码候选），按文档快照日期钉定（2026-09-15 观测），不设版本 tag。

调研记录（架构逐点核实、与 Loom 契约的映射表、差异与不采纳、修正三处简报偏差）：[design/g2/cursor-cloud-agent-reference-2026-09-15.md](design/g2/cursor-cloud-agent-reference-2026-09-15.md)。

[23] [Cursor background/cloud agents 官方文档](https://cursor.com/help/ai-features/background-agents.md)；[24] [Cloud Environment Setup](https://cursor.com/docs/cloud-agent/setup.md)；[25] [Secrets & Network](https://cursor.com/docs/cloud-agent/security-network.md)；[26] [What we've learned building cloud agents](https://cursor.com/blog/cloud-agent-lessons)；[27] [agent computer use 公告](https://cursor.com/blog/agent-computer-use)；[28] [Self-Hosted Cloud Agents](https://cursor.com/de/blog/self-hosted-cloud-agents) 与 [Cloudflare 自托管教程](https://developers.cloudflare.com/sandbox/tutorials/cursor-cloud-agents/index.md)。

**借鉴取舍入口**：以上调研（§11/§12）的借鉴评估与优先级落位见 [design/g2/adoption-assessment-2026-09-15.md](design/g2/adoption-assessment-2026-09-15.md)——A 立即（并入 linux-browser §5 流程修订）/ B 近期（专项判据）/ C 后置（登记防遗失）/ D 明确不采纳及理由。

## 13. 2026-09-15 增补：macOS 宿主基座（Linux VM appliance）候选

产品部署要求 macOS 宿主提供与 Linux 同构的运行时物理事实（renameat2、inotify、钉死 Docker Engine 28.0.1、固定 volume 路径与 /proc 判据）；现状依赖 Docker Desktop，其中 Engine 版本浮动、volume 不可钉、物理判据不可复现为耦合副作用。用户 2026-09-15 确认原则：**不重复造 sandbox/VM 底座轮子，macOS 基座复用成熟 VM appliance，自研 VZ 应用仅登记为后期演进项**。业界对应形态（Docker Desktop、Podman machine、Rancher Desktop、Finch）均为"自带 Linux VM appliance"。

2026-09-15 起草时本整理环境无外网，本节最初为身份登记（版本一律待钉定）；**同日稍后已完成在线核对与钉定（git ls-remote 直连 refs + releases/latest 重定向，GitHub API 限流同前），核对记录与证据见 [design/g2/macos-host-substrate-survey-2026-09-15.md §7](design/g2/macos-host-substrate-survey-2026-09-15.md)**，判据 V1–V4 预登记见 [substrate 验证协议](design/g2/substrate-verification-protocol-2026-09-15.md)，均未执行。

| 项目与仓库 | 钉定版本（2026-09-15 观测） | 定位与重点调研 |
| --- | --- | --- |
| **Lima** — [lima-vm/lima](https://github.com/lima-vm/lima) | **v2.2.0**，peeled commit `de0816ea4bdc5267b428ab21025889b8dd785526`（预发布 v2.3.0-beta.0 不钉定） | **主候选**：Finch/Rancher Desktop 共同底座。钉死内核与 appliance 版本、VZ 加速 arm64、VM 内 dockerd 与 docker.sock、共享目录上 renameat2/inotify/dev-ino 行为、deps volume 固定路径可行性 |
| **AWS Finch** — [runfinch/finch](https://github.com/runfinch/finch) | **v1.17.2**，commit `c0f8e88c60793fa0a92030136c2281bdbf06683c`（其 go.mod 钉 Lima v2.1.3，版本解耦先例） | Lima 生产化封装先例：安装器、镜像钉定、更新渠道组织 |
| **Podman machine / podman-machine-os** — [podman-container-tools/podman-machine-os](https://github.com/podman-container-tools/podman-machine-os)（原 containers/ 迁移重定向） | **v6.1.2**，peeled commit `0a7a56040f65c42d666fd13df2e9afbb6bfce0c0` | appliance 版本化与升级模型先例；Apple VZ/libkrun 后端选型参考 |
| **Docker Desktop** — 官方文档 | 形态参照（非代码候选），不钉定 | 现行开发模式事实底座；版本浮动与判据不可复现是"继续依赖"不成立的直接依据 |
| **Apple Containerization framework** — [apple/container](https://github.com/apple/container)、[Virtualization 文档](https://developer.apple.com/documentation/virtualization) | **1.4.1**，commit `9a8917ca2da5cd6ba059b9ba5ca5a74892e9bb7d`（登记项） | 系统级新变量："每容器一个轻量 VM"，不提供 Docker Engine；与 X profile 冲突，登记为未来 X 后端可评估项，采纳即"换 Engine"须重新验证 |

[29] [Lima 仓库](https://github.com/lima-vm/lima)；[30] [Finch 仓库](https://github.com/runfinch/finch)；[31] [Podman machine 文档](https://docs.podman.io)，appliance 说明；[32] [Docker Desktop 文档](https://docs.docker.com/desktop/)；[33] [apple/container 仓库](https://github.com/apple/container)与 [Apple Virtualization framework 文档](https://developer.apple.com/documentation/virtualization)。

## 14. 2026-09-16 增补：Temporal（durable execution 参照，用户点名）

用户确认 Temporal 思想与本项目高度重合（持久推进责任、durable execution），指定登记并充分调研。定位：**设计参照与机制对照物**（非代码候选——跨语言与系统形态差异，见调研记录 §4；2026-09-16 更正：分布式服务器本体为规模化**暂缓路线图**而非不采纳，单机不是项目目的，详见调研记录 §12）。clone 至 `research/repos/temporal`（gitignore 内；head=172d1b409，2026-09-16 观测；未钉定 release，跟随主分支）。归属：与 §5 DBOS 同类（持久推进），按用户点名单列。

| 项目与仓库 | 版本（2026-09-16 观测） | 定位与重点调研 |
| --- | --- | --- |
| **Temporal** — [temporalio/temporal](https://github.com/temporalio/temporal) | 主分支 head `172d1b409` | **服务器/SDK 分工**：事件日志+完成校验（服务端）vs 确定性执行+重放（SDK worker）；**continue-as-new** 与 Loom 后继机制同构性；历史尺寸分档（warn/suggest/error）；**MutableStateRebuilder**+checksum 的确定性重建与完整性校验；重试策略结构；CHASM 状态机库；与 Loom 未决项（暂停后重放、压缩再驱动冲突）的映射 |

调研记录（架构逐点源码核实、未决项映射表、CHASM 全文精读、sdk-core 重放引擎与确定性执行点、可复用组件判定、借鉴项 A/B/C/D 优先级落位、不采纳及理由）：[design/g3/x/temporal-research-2026-09-16.md](design/g3/x/temporal-research-2026-09-16.md)。文档级+源码审查已完成（服务器四服务、事件溯源充分性契约、workflow task 三型、continue-as-new、历史尺寸分档、CHASM、update 状态机、archival/versioning、retry、sdk-core TMPRL1100 确定性执行点）；未运行实验（本地起 Temporal 验证 continue-as-new 行为等需另行授权预算）。sdk-core 克隆于 research/repos/sdk-core（2026-09-16）。

[34] [Temporal 仓库](https://github.com/temporalio/temporal)；[35] [Temporal 官方文档](https://docs.temporal.io)；[36] [sdk-core 仓库与 ARCHITECTURE.md](https://github.com/temporalio/sdk-core)。
