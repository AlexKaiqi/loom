# 执行编排与沙箱底座：2026-09-15 补充调研（用户简报五项）

**整理日期：2026-09-15**
**状态：文档级调研。** 已完成：候选身份与仓库迁移核实、最新发布版本钉定（GitHub releases/latest 重定向，2026-09-15 观测）、README/官方页声称与 Loom 关注点的对照。未完成：逐项源码审查、克隆运行实验；下文"可复用位置"是预期定位而非已核实路径；"拟验证实验"按 templates.md §9 交付口径后置。核对来源见文末，区分维护方来源与第三方页面。

**触发**：用户简报指出开源界对"LLM 编排层 + 隔离执行沙箱"已有成熟实现，点名 OpenHands、SWE-agent、AutoCodeRover、E2B、Daytona，并附一套 MVP 技术栈建议（LangGraph/GitHub App/强制反馈环）。

## 与既有清单的关系

主清单已覆盖相邻身份：OpenHands **software-agent-sdk**（§3，SDK 重写版）、mini-swe-agent（§2，SWE-agent 团队的极简版）、OpenSandbox（§4，与 Daytona 同位）、Daytona（原标注"历史公开实现参考"）。本次补充的是**父项目与应用本体身份**：OpenHands 应用（v1 应用本体，event-stream 产品）、SWE-agent（ACI 提出者）、AutoCodeRover、E2B，并将 Daytona 转为正式候选。五项合起来恰好横跨 Loom 的两个关注面：编排层（事件驱动、issue→PR 闭环）与沙箱底座（Docker 封装、MicroVM 云沙箱、环境管理平台）。

## 逐项记录

### 1. OpenHands（应用本体）— `OpenHands/OpenHands`，钉定 v1.18.0

- **身份核实（已观测）**：仓库已从 `All-Hands-AI/OpenHands` 迁移至 `OpenHands/OpenHands`；releases/latest 指向 v1.18.0。与主清单 §3 的 software-agent-sdk 是**并行双轨**：v1 应用（event-stream 架构产品）与 V0 SDK 重写（Agent SDK/Agent Server/Workspace），不可混为一谈。
- **职责与状态归属（README 声称级）**：任务经 Event Stream 驱动；代码执行、Bash、无头浏览器封装在独立 Docker 容器（Runtime）内；浏览器环境经 BrowserGym/Playwright 接入（历史 PR #3235 将 Browser Env 对接 EventStreamRuntime）；GitHub 侧有 issue→PR 自动化（automation 仓库承担调度/Webhook，已列主清单）。
- **对 Loom 的意义**：独立验证了两个既有选择——事件流作为推进底座（对应 E 事件权威）与"控制层/运行环境彻底解耦、执行封装进沙箱容器"（对应 X 的请求/预算/归档契约）。其浏览器在 runtime 容器内无头运行的形态是 M06（linux-browser 环境）的直接同构参考。
- **可复用位置（预期，未核实）**：runtime 容器构建（基础镜像层、浏览器依赖层）；condenser（上下文压缩，与 SoL-Pi §2 对照同题）。
- **不采纳/适配缺口**：应用级状态模型与推进策略是它的私产，不在复用范围；event stream 的具体事件词汇表未经源码核对，不得据此改 E 的契约。
- **拟验证实验**：钉定 v1.18.0 克隆，观察其 runtime 容器内浏览器进程树与 X11/无头栈的实际形态，为 M06 的 linux-browser 镜像分层（浏览器依赖 vs 任务身份）提供对照。
- **纠错记录**：检索索引显示的 v1.9.0 为陈旧缓存，以 releases/latest 重定向 v1.18.0 为准。

### 2. SWE-agent — `SWE-agent/SWE-agent`，钉定 v1.1.0

- **身份核实（已观测）**：`princeton-nlp/SWE-agent` 重定向至自有组织 `SWE-agent/SWE-agent`；NeurIPS 2024 论文项目；releases/latest 为 v1.1.0（"10s of thousands of training trajectories"）。
- **职责与状态归属（README 声称级）**：接收 GitHub issue 并自动修复；核心贡献为 **ACI（Agent-Computer Interface）**——为 LLM 定制高信噪比的浏览/搜索/编辑命令接口，目标降低 token 消耗与幻觉。
- **对 Loom 的意义**：ACI 与本仓库的实践同构——X 的接口面（readonly_mounts、输入归档确定性打包、journal 观测路径、错误码分类）正是"接口设计决定模型操作质量"的契约化版本；对 Harness 层工具定义有直接指导意义（接口信噪比是设计责任，不是模型能力问题）。mini-swe-agent（主清单 §2）是其极简衍生，二者结论应合并研读。
- **可复用位置（预期，未核实）**：其工具定义文件（bundle/config 形式的命令接口规范）可作为 Harness 工具词汇表设计的对照样本。
- **不采纳/适配缺口**：SWE-agent 的接口以 shell 文本命令为中心；Loom 的 X 适配器是 JSONL 结构化控制通道 + 结构化动作，语义层级不同——只借鉴"信噪比优先、单一职责命令"的设计准则，不引入其 shell 接口形态。
- **拟验证实验**：在 SWE-bench-lite 的固定子集上对照"裸 shell 接口 vs ACI 接口"的 token/轮次/错误率，验证 ACI 论点的量级，再决定 Harness 工具词汇表的裁剪。

### 3. AutoCodeRover — `AutoCodeRoverSG/auto-code-rover`，钉定 v1.1.0

- **身份核实（已观测）**：`nus-apr/auto-code-rover` 重定向至 `AutoCodeRoverSG/auto-code-rover`；迁移后仍在发版（v1.1.0 "Github comments processing"），维护状态比预期活跃。
- **职责与状态归属（README 声称级）**：项目结构感知（AST 分析）的自治软件工程 agent；README 声称 SWE-bench lite 37.3% / verified 46.2%（pass@1），每任务 <$0.7；依赖沙箱内重现缺陷、运行测试、以测试反馈闭环验证补丁。
- **对 Loom 的意义**：AST 结构化检索是 Harness 策略层（多策略演进）的一个高价值候选策略——检索与定位在宿主侧以纯工具完成，只有测试验证需要沙箱执行，与 X 的执行契约天然分工；"测试反馈闭环"与 X 的验收语义（exit code/stderr/归档）一致。
- **可复用位置（预期，未核实）**：结构检索工具（AST/spectrum 定位）可作为独立 Harness 策略组件嫁接，不动 Runtime。
- **不采纳/适配缺口**：其检索工具不得进入 Runtime 核心边界（分层职责）；性能数字是 README 声称，未经本仓库复测前不引用。
- **拟验证实验**：钉定 v1.1.0，在固定缺陷样本上运行其检索+测试闭环，观测沙箱调用次数与失败归因，评估作为 G3 阶段第二策略的适配成本。

### 4. E2B — `e2b-dev/E2B`（SDK），钉定 @e2b/python-sdk@2.49.1；底座在 `e2b-dev/infra`

- **身份核实（已观测）**：E2B 仓库以 SDK monorepo 形式发版（最新 @e2b/python-sdk@2.49.1）；自托管底座 infra 为独立仓库（API 限流，本轮未取得其 release 钉定）。
- **职责与状态归属（声称级，两处来源）**：面向 AI agent 的云端沙箱：REST Sandbox API + Python/JS SDK + Code Interpreter SDK + 持久卷 + 自定义模板构建 + CLI。隔离机制：第三方目录描述其"基于 fork 的 Firecracker microVM 运行时"；其沙箱内守护进程 envd 已被 Kubernetes SIG Sandbox 采纳为示例（agent-sandbox.sigs.k8s.io 的 envd-sandbox 用例页）——该事实如需引用须核对官方文档，本轮未读原文。
- **对 Loom 的意义**：E2B 是 **D-X-SEAM-001（ExecutionBackend 接缝）远端实现方向的公开同构物**——Loom X 的请求/预算/归档/只读挂载语义与"API 换一个完整 Linux 环境"的沙箱服务形态一一对应；backend.py 接缝的第二实现（E2B 后端）将是"同一请求语义、不同隔离机制（microVM vs 容器+seccomp）"的直接检验，比换一个 Docker 宿主更能证明接缝不渗漏。
- **可复用位置（预期，未核实）**：SDK 的 API 词汇表（create/exec/filesystem/volumes/template）作为远端后端请求形状的对照；infra 的自托管拓扑作为平台部署参考。
- **不采纳/适配缺口**：网络 API 服务（非 unix socket 直连）、计费与配额模型、安全边界不同（microVM vs 固定 seccomp+network none）——不替换 X 本体，只作接缝第三实现方向；其"毫秒级冷启动"为厂商声称，不采信为设计依据。
- **拟验证实验**：以 D-X-SEAM-001 的 SEAM_METHODS 为契约，编写最小 E2B 适配器跑 X 的拒绝类用例（X029/X030 同型），验证接缝在不改 requests 层的情况下可指向 microVM 后端。

### 5. Daytona — `daytonaio/daytona`，钉定 v0.190.0

- **身份核实（已观测）**：仍在 0.x 高频发版（v0.190.0，2026-09 观测活跃）；定位已从"开发环境管理器"演进为 agent 沙箱基础设施（第三方对比页与 2026-08 活动（HackSprint）佐证其活跃，具体能力矩阵未经官方页核对）。
- **职责与状态归属（声称级）**：自托管环境管理平台 + SDK/CLI，可按需拉代码仓、装运行时、供 agent 动态消费算力节点；第三方材料有"容器级 ~90ms 冷启动，快于 E2B microVM"的对比声称——来源为第三方整理，只作线索不作事实。
- **对 Loom 的意义**：与主清单 §4 的 OpenSandbox 同位（自托管沙箱平台、生命周期与执行接口分离）；作为"环境生命周期（创建/复用/停止/销毁）"的对照实现，与 OpenSandbox 择一深查即可，避免重复投入。
- **可复用位置（预期，未核实）**：环境生命周期状态机的对外形状。
- **不采纳/适配缺口**：0.x 版本号阶段的 API 稳定性、与 Loom X 契约的错位（面向通用环境管理，非固定身份执行）——列为观察项，不进入当前实施路径。
- **拟验证实验**：与 OpenSandbox 二选一后，做"创建→执行→销毁→重建同身份环境"的生命周期实验，对照 X 的 binding/container 身份模型。

## 对 MVP 技术栈建议的评估

用户建议的"控制层 LangGraph/纯状态机 + GitHub App 监听 issue + 强制反馈环（测试→退出码/stderr→自修→分支→PR）+ 沙箱层 Docker 封装或 E2B"是**从零自建视角**；Loom 已有等价物：E 事件底座 + S 触发与推进 + X 验收语义 + F 版本化。结论：不引入新编排框架（禁止用框架选型反向决定系统目标）；采纳其两点作为 Harness 层要求——反馈链路必须是强制环节而非可选提示；issue→PR 自动化是 S 的外部触发形态（OpenHands automation 仓库为主清单既有对照）。沙箱层"自托管 Docker 封装 vs 云端 E2B"恰对应 D-X-SEAM-001 的两个实现方向，与上表结论一致。

## 核对来源（2026-09-15 观测）

[1] [OpenHands releases/latest → v1.18.0](https://github.com/OpenHands/OpenHands/releases/latest)（组织迁移：All-Hands-AI → OpenHands）。
[2] [OpenHands Browser Env × EventStreamRuntime PR #3235](https://github.com/OpenHands/OpenHands/pull/3235)（浏览器环境与事件流运行时对接的历史结构证据）。
[3] [SWE-agent releases/latest → v1.1.0](https://github.com/SWE-agent/SWE-agent/releases/latest)（princeton-nlp 重定向）。
[4] [AutoCodeRover releases/latest → v1.1.0](https://github.com/AutoCodeRoverSG/auto-code-rover/releases/latest)（nus-apr 重定向）。
[5] [E2B releases/latest → @e2b/python-sdk@2.49.1](https://github.com/e2b-dev/E2B/releases/latest)；自托管底座 [e2b-dev/infra](https://github.com/e2b-dev/infra)。
[6] [Daytona releases/latest → v0.190.0](https://github.com/daytonaio/daytona/releases/latest)。
[7] 第三方线索（声称级，不作事实依据）：[Northflank: Daytona vs E2B](https://northflank.com/blog/daytona-vs-e2b-ai-code-execution-sandboxes)、[sandbox-environments 整理](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/references/sandbox-environments.md)、[E2B 项目目录描述（forked Firecracker）](https://github.com/api-evangelist/e2b-dev)、[envd 的 K8s SIG Sandbox 示例页](https://agent-sandbox.sigs.k8s.io/docs/use-cases/examples/envd-sandbox/)。
[8] GitHub REST API 本轮被限流（HTTP 403），版本钉定全部来自 releases/latest 重定向页，未取得精确 commit SHA；后续源码审查须先补 commit 级钉定。
