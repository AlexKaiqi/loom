# Cursor Cloud Agent：产品形态参照（2026-09-15 文档级调研）

**整理日期：2026-09-15**
**状态：文档级调研（产品参照，非代码候选）。** Cursor Cloud Agent（早期名 Background Agents）不开源，本记录按用户简报核实其官方设计文档与工程博客，登记为**形态与机制参照**：没有可复用代码与版本 tag，全部按"2026-09-15 观测的文档快照"钉定。引用层级均标注"官方文档声称"；其性能数字（可靠性两个 9、40%+ 内部 PR 占比）为厂商自述，不作事实依据。

## 1. 形态核实（与用户简报的逐点对照）

官方文档（setup/security-network 页）与博客确认的架构：每个 Cloud Agent 独占一台隔离 Ubuntu VM（仓库、依赖、secrets、网络）；Harness 云端托管；产出直接是附验证产物的 PR；异步长时运行。**用户简报基本准确**，三处修正/补充：

1. **自托管确认为真**：官方博客 self-hosted-cloud-agents 存在（多语言版本）；Cloudflare 有官方教程（每会话跑在隔离 Cloudflare 容器内的自托管机器）；社区论坛出现"self-hosted workers 与 Automations 集成"的讨论。简报所列 AWS Lambda/Modal/Vercel/E2B 具体平台广度未经官方页逐个核对，仅 Cloudflare 一项有官方教程实证。
2. **私有资源 ≠ 自托管**：官方文档同时提供"VM 仍在 Cursor AWS 基础设施 + 经 Tailscale userspace/Cloudflare Tunnel/PrivateLink 触达内网"的路径——"代码不出内网"只在自托管模式下成立，两案并存。
3. **Background Agents 已更名 Cloud Agents**；触发面为 IDE/网页/移动端/Slack/GitHub/Linear @Cursor + Automations（定时/事件）。

## 2. 逐点映射：Cursor 形态 ↔ Loom 既有契约

| Cursor 概念（官方文档声称） | Loom 对应 | 记录价值 |
| --- | --- | --- |
| 每 Agent 专用隔离 VM | X 固定身份执行容器（task uid 1000、slot labels、固定 seccomp、network=none） | 验证"任务=隔离环境实例"的形态共识 |
| `.cursor/environment.json`（Dockerfile+context+幂等 install+start/terminals）、环境解析顺序（repo→个人→团队）、schema 公开 | `environment_profiles.json`（M06 前置修订）+ M06 待泛化的"按 profile 建镜像"路径 | **证明 per-profile 环境定义是业界主流形态**，M06 后续方向的直接先例 |
| Build＝基镜像+克隆+install 的磁盘快照；失败 Build 不替换 active Build；层缓存；快照只保留磁盘态（进程/环境变量不延续）；90 天滚动不活跃保留 | X 镜像钉定 + S checkpoint/seal/release 语义；证据生命周期 | "快照只含磁盘态"与 checkpoint 边界同构；"失败不替换活动版本"与修订保留旧值同精神 |
| agent loop／机器状态／会话状态三者解耦；append-only 会话存储；重试后客户端检测部分输出并回绕 | R/E/F/S 事实归属划分（E 事件权威、F 文件、S 会话推进） | 厂商级工程实践确认"事实分层归属"是必经之路 |
| work-stealing → Temporal 迁移（"一个 9"→"两个 9"）；"永恒 workflow 改为单任务短 workflow" | E 事件底座 + 目标续推；主清单 §5 DBOS 专项 | 同一空间轻量替代即 DBOS——验证清单既有立项 |
| Runtime Secrets：内容在工具结果/转录/提交中替换为 `[REDACTED]`；Build Secrets 仅入 Docker secret mount | 凭据纪律（不进 Git/镜像/证据包/任务环境）的机制化样例 | F/E 凭据边界的具体实现参照 |
| OIDC 短时 token 从 VM 本地 socket 铸造；HSM Ed25519 签名提交 | X 执行身份思想：身份短时化、来源可验证 | 与 slot labels/固定 uid 同向，且给出"来源可验证"的产品级做法 |
| 网络三档（全开/默认+允许表/仅允许表）；同一允许表共享给桌面沙箱；明确警告"允许表通配符=提示注入外泄路径" | X network=none 固定 profile；M06/M07 网络策略待定项 | 网络策略收紧方向与共享允许表设计的现成参考 |
| **Computer use＝Harness 专用子代理**（独立模型路由+定制提示+录屏）；VNC/Chrome 属于环境、父代理与子代理共享（父可直接跑 Playwright）；官方原话"模型未就绪，用脚手架过渡，但调用时机由 agent 控制" | M06 契约（浏览器为环境能力面）+ 模型路由（画像/质量分） | **回答早前"computer-use 沙箱业界是否成熟"**：成熟形态=环境内置 VNC/Chrome+录屏产物，模型能力缺口用子代理路由补 |
| PR 附视频/截图/日志产物（验收者不必 checkout 分支）；远程桌面人类接管 | 独立验收证据观（直接核对产物，不信自述） | "产物可验收"是产品级证据纪律的变体 |
| 自托管 worker（沙箱内轻量进程接收云端指令；Cloudflare 官方教程实证） | D-X-SEAM-001：同一请求语义、可替换执行后端 | **接缝设计的产品级先例**：harness 不变、沙箱位置可换 |
| "Harness 不是消失，而是内容在变"：早期每步复核/强制提交 → 移为 agent 可控工具（分支/PR/GitHub CLI、大输出自动落文件可检索）；云端提示更自主（阻塞成本高）；auto-install 自愈 | 外部 Harness 定义"模型看什么/怎么推下去"；G2/Harness 策略演进 | 官方承认 Harness 内容随模型能力迁移——支持多策略并存、策略可替换的设计 |

## 3. 与 Loom 的差异与不采纳

- **封闭产品**：无可复用代码；本记录只登记形态与机制，不据此改动 Loom 契约（禁止以厂商设计反向决定系统目标）。
- **信任模型更激进**：官方自述"agent 自动运行所有终端命令"并以网络策略兜底，明确承认提示注入风险；Loom X 的固定身份+seccomp+network=none 更保守——是设计差异，不是落后。
- **Loom 特有而 Cursor 公开文档未覆盖**：判据独立与可拒绝错误的验收纪律、预算/journal 作为一等观测、契约→独立用例→实现→验证的开发纪律本身；这些不做让步。
- **环境即产品**（官方经验第一条："环境是最大的质量因素，缺失的症状是产出质量微妙劣化而非报错"）与 Loom 的环境契约方向一致，可作为 M06/M07 优先级的佐证引用（厂商经验声称）。

## 4. 拟验证实验（后置）

形态参照无直接运行实验；其机制若要进入 Loom，须经各自组件门槛：Build/快照语义对照 S 的 checkpoint 用例；Runtime Secrets 脱敏对照 F 的凭据边界用例；computer-use 环境内置栈对照 M06 的 linux-browser 镜像分层。自托管 worker 若成为部署形态，走 D-X-SEAM-001 的第二实现验证（同 SEAM_METHODS、不同后端）。

## 5. 核对来源（均为官方页，2026-09-15 观测）

[1] [Background agents 概述（更名 Cloud Agents、VM 隔离、产物、触发面）](https://cursor.com/help/ai-features/background-agents.md)。
[2] [Cloud Environment Setup（environment.json/Build/快照语义/资源上限/computer use 支持范围/密钥与 OIDC）](https://cursor.com/docs/cloud-agent/setup.md)；[环境 schema](https://www.cursor.com/schemas/environment.schema.json)。
[3] [Secrets & Network（三类 secret 脱敏、签名提交、网络三档、通配符警告、数据保留、egress IP）](https://cursor.com/docs/cloud-agent/security-network.md)。
[4] [What we've learned building cloud agents（Temporal 迁移、三者解耦、harness 内容迁移、computer use 子代理与 VNC/Chrome 归属、auto-install）](https://cursor.com/blog/cloud-agent-lessons)，2026-06-02。
[5] [Cursor agents can now control their own computers（录屏产物、远程桌面接管、30%+ 内部 PR 来自云代理）](https://cursor.com/blog/agent-computer-use)，2026-02-24。
[6] [Self-Hosted Cloud Agents 官方博客](https://cursor.com/de/blog/self-hosted-cloud-agents)；[Cloudflare 官方自托管教程](https://developers.cloudflare.com/sandbox/tutorials/cursor-cloud-agents/index.md)（自托管最小实证）。
