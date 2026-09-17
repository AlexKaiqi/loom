# X 执行后端接缝与环境扩展：判断记录

状态：DRAFT-2026-09-15。这是取舍记录（模板 §3 形态）与设计判断，不是 X 契约修订，不修改任何代码，不产生通过结论。现有 `design/g3/x/contract.md`（G3_REVIEW_DRAFT）、已验批次与 `docs/validation-status.md` 的范围不变。

## 1. 依据与授权

- v5 §4.3：执行方式通用、环境明确分流属执行定义；§7.3 把"执行环境：隔离产品、用户映射、目录路由、挂载与端点限制"列为待验证工程选择。AGENTS.md 要求平台相关行为按 `sys.platform` 显式分支并记录证据范围。
- 用户 2026-09 决定：沙箱以本地 Docker 为当前唯一后端；为"本地 Docker / 远程沙箱一套协议"保留抽象；业界已有收敛进展则留接缝，否则暂缓；随后补充授权把浏览器、软件插件、MCP、computer use 纳入沙箱环境扩展的预先考虑。
- 本记录回答：接缝放在哪里、外部依据是什么、哪些内容归 profile、哪些扩展点需要提前声明、何时按什么流程重估。

## 2. 外部事实与来源

以下为 2026-09-15 的外部文档观察（列于 §7），均未做固定版本源码核查；事实与推断分开陈述。

**事实（来源文档明示）**

- OpenAI Agents API（managed agents）把系统拆为 harness（托管模型/工具循环与会话）/ environment（远程沙箱、本机、容器或函数计算）/ application server；`environment.type` 支持 none、openai_hosted、self_hosted。
- self_hosted 连接形态：环境内运行执行器（`codex exec-server`），以环境 ID 与受限 executor key（仅允许连接环境，无其他 API 权限）注册，出站 WebSocket 收命令、回结果，断线自动重连；应用主密钥留在环境外。
- 生命周期：session 可长于 environment；API 明示"不保证进程崩溃后恢复 pending input，先核对请求或会话结果再重试；原请求等待期间不得重发"；复用 environment ID 不恢复替换计算中的文件；turn 完成时 `/workspace/outputs` 发布为不可变 artifacts；支持 webhook 触发的按需供给（`environment_connection` required action）。
- OpenAI Agents SDK（开源）沙箱代理：harness（控制面：循环、工具路由、审批、tracing、恢复）与 compute（执行面）显式分离；`SandboxClient` 单一接口下有 UnixLocal、Docker 与 E2B/Modal/Daytona/Cloudflare/Vercel/Blaxel/Runloop 等实现；"provider 属于 run 配置，不属于 agent 定义"；Manifest（workspace 相对路径、跨本地/容器/托管可移植）；RunState、可序列化 session state（`serialize`/`resume`）与 snapshot 三层状态。
- AgentScope 2.0：`WorkspaceBase` 单一接口下有 Local、Bubblewrap、Docker、E2B、Daytona、K8s、OpenSandbox 七个实现；MCP server 运行在隔离环境内、经 in-workspace gateway 暴露。
- computer use 环境配方：web 用隔离浏览器（Playwright，`chromium_sandbox`、空 env、禁扩展/文件系统）；桌面用 VM/容器（Docker：Xvfb+xfce4+x11vnc+xdotool+imagemagick，`EXPOSE 5900` 供人工接管）；动作集为 screenshot/click/double_click/drag/move/scroll/type/keypress/wait（支持批量）；截图以图像输入回传（`detail: original`、固定分辨率、缩放需重映射坐标）；亦可自建 UI 工具或持久 exec runtime（`{session_id, language, code}` → text+image）；文档明示"Node vm 与受限 Python globals 不是安全边界"，须一次性低权容器且与 API 客户端凭据分离；风险动作（密码、CAPTCHA、安装、发送、支付、改设置）须动作时确认，必要时人工接管。
- E2B 提供 computer use 桌面沙箱与云端浏览器用例；Grok Bot 为账号级共享"云电脑"（各 Bot 屏幕独立但文档明示屏幕不是安全边界），作为便利性优先的反面参照。

**推断（本记录判断）**

- 抽象形态已收敛：两家主流开源 SDK 独立得出同一形状——单接口多后端、provider 属配置、manifest/快照/恢复进契约。
- 开放 wire 协议尚未形成：唯一协议化先例（OpenAI executor 出站 WebSocket 契约）绑定其自身 harness 且为 beta；各家云沙箱供给 API 均为私有 SDK；MCP 只覆盖工具层，不含环境生命周期、预算与恢复语义。
- 按用户判据（"业界几乎没有进展才暂缓"）：抽象值得留，协议不值得押注，远程后端不值得现在实现。

## 3. 决定 D-X-SEAM-001：接缝即既有 X 契约方法集

- 接缝定义为 `design/g3/x/contract.md` §2 方法集（execute、query、restore、request_stop、checkpoint、resume、seal、release）加 §3 状态语义与双向流。该合同 §4 已写明"未来其它有总配额的成熟后端可替换，但必须"满足同一合同；本决定只是显式化该替换入口，不改字面。
- **后端必须产出的事实**（属后端合同，不是实现细节）：stopped proof；checkpoint 归档与 manifest（prepared_artifact receipt）；release 时剩余写能力核验；UNKNOWN / INCOMPLETE_OBSERVATION / INCOMPLETE_LIMIT 语义；按 execution_id + request_digest 幂等、不确定不重跑。这些语义不可为迁就新后端放宽；放宽即契约修订。
- **backend 专属内容归 profile**：readonly_mounts/tmpfs 语义、Engine 身份与版本锚定、metadata profile 限支持集、环境标识（现 `fixed-python-linux-v1`）。`lore_execution/requests.py` 现仅放行 `readonly_mounts`，维持现状。
- **非目标**：不实现远程后端；不解锚 Docker Engine；不扩 endpoints 语义；不新增运行时行为或新模型可见命令。
- 代码级落点（2026-09-15，非行为变更）：`lore_execution/backend.py` 以 `typing.Protocol` 声明同一方法面（SEAM_METHODS、OWNER_INTERNALS、SERIALIZED_WRAPPED、BACKEND_OWNED_* 三组 profile 归属常量）；`simulations/test_execution_backend.py` 为静态符合性检查（协议参数形状对齐 ExecutionStore、上层访问只允许接缝方法或 owner 内部、归属字段必须位于 requests 核心字段集之外）。该测试只防声明漂移，不执行任何后端，不构成组件验收。发布清单已同步登记（source-manifest.json，100 个产品文件）。

## 4. 决定 D-X-ENV-001：环境扩展按三档预留

- **T0 装镜像**：软件插件、浏览器自动化库、MCP server 都是镜像/依赖内容，不新增执行形态。前置条件是环境 profile 资产化：`environment` 从单一常量改为 R 可登记、带 digest 的 profile 引用；预留 `linux-shell`（现状）、`linux-browser`、`linux-desktop`、`macos-vm` 变体。X 按 profile 分支校验预算与环境，分支记录证据范围。
- **T1 便捷形式**：MCP 默认沙箱内放置 + 本地 gateway（AgentScope 模式），不触碰 `endpoints=[]`；仅托管连接器才把 endpoints 扩展为"受限出站端点 + 凭据引用 + 域名允许表"，且作为 profile 字段而非全局放开。端口/预览用 `exposed_ports`（见 §5b），授权登记在 R，不构成任务环境的控制通道。
- **T2 computer use**：执行形态复用 schema_version 2 duplex 会话与 checkpoint/restore（X 已有），不新增执行入口。GUI 工具面归 Harness：建议 screen（截图与 accessibility tree 观察，axtree 优先于像素）/input（click/type/key 等）/exec（持久 runtime）三件套；确认分级规则写在 Harness，动作时强制阻断在 Runtime；动作留痕复用 outbox 模式；人工接管经 VNC 走 exposed_ports。截图回传依赖多模态模型输入，属模型侧前置条件。

## 5. 提前声明的契约扩展点（防返工）

- (a) **工具结果图像 artifact**：截图落盘 → F 版本（sha256 证据链）→ tool reply 携带引用（沿用 publication_ref 模式）。前提：S/Pi 消息 content 支持图像 part、provider 桥支持图像输入。在 S 多模态支持落地前，不得以纯文本替代截图语义。
- (b) **exposed_ports 进 X request**：新增 request 字段须修订 `design/g3/x/contract.md` §2 request 绑定与 `cases.json` 用例，经独立验证后生效；端口的可见性与访问控制属 R 授权责任。

## 6. 重估触发与流程

- 触发条件任一满足即重估：出现真实远程沙箱需求；OpenAI 沙箱契约自 beta 转 GA 且被多家采纳；出现开放 wire 标准。
- 重估流程按模板 §3/§4：固定提交核查与许可记录、契约修订、独立用例、组件验证通过后才允许组合；本记录中的外部文档观察不构成采用依据。
- 已知未决：`design/unknowns.md` Q13（Grok Bot 原项目身份）不在本记录闭合；§7 的产品文档与该问题所指研究对象的对应关系未确认。

## 7. 来源（观察日期 2026-09-15）

| 编号 | 来源 | 用途 |
| --- | --- | --- |
| S1 | OpenAI Agents API 架构：https://developers.openai.com/api/docs/guides/agents-api/architecture | harness/environment/app 拆分 |
| S2 | OpenAI Agents API self-hosted sandboxes：https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted | 执行器连接形态、受限 key、provider 列表 |
| S3 | OpenAI Agents API sandbox lifecycle：https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle | 按需供给、崩溃语义、不保证恢复 pending input |
| S4 | OpenAI Agents API openai-hosted：https://developers.openai.com/api/docs/guides/agents-api/environments/openai-hosted | packages/setup/网络策略、artifacts 发布 |
| S5 | OpenAI Agents SDK 沙箱代理：https://developers.openai.com/api/docs/guides/agents/sandboxes | SandboxClient 接口、manifest/快照/恢复、provider 属 run 配置 |
| S6 | AgentScope 2.0 Workspace：https://docs.agentscope.io/versions/2.0.7/en/building-blocks/workspace/overview | 七后端同接口、MCP 沙箱内放置 |
| S7 | OpenAI computer use 集成指南：https://developers.openai.com/api/docs/guides/tools-computer-use-integration | 浏览器/桌面配方、动作集、图像回传、确认分级 |
| S8 | E2B computer use：https://docs.e2b.dev/use-cases/computer-use | 桌面沙箱与云端浏览器用例 |
| S9 | Grok Bot 文档：https://docs.x.ai/grok-bot/overview 、https://docs.x.ai/grok-bot/computer-and-apps | 共享云电脑模型（反面参照：屏幕非安全边界） |
| S10 | xAI 本地沙箱 profile：https://docs.x.ai/build/features/sandbox | Landlock/Seatbelt profile 分档参照 |
