# Codex：客户端、局部执行与宿主边界

本记录研究官方 openai/codex 固定提交 ee6814bfa4889fe9b2b3dcc9cc8bdd91effa8ab8。问题来自 G1 H02/H08/H10、完整输出边界及 P14。它提供可借鉴的交互协议与执行体验，但本次不把 ChatGPT、桌面产品或云调度全部视为开源仓库内容，也不把局部 Thread 包装器当作本系统的持久宿主。

## 职责与事实归属

- **源码事实**：sdk/typescript/src/codex.ts 的 Codex 创建 CodexExec，并返回 Thread；resumeThread(id) 创建一个带既有 id 的包装器。thread.ts:73—119 的流解析把 JSON 转为事件，thread.started 更新 id；thread.ts:124—146 的 run 收集 item.completed，记录 turn.completed 的 usage，turn.failed 才拒绝。它没有显式要求最终必须收到 turn.completed。
- **源码事实**：sdk/typescript/src/exec.ts 的 run 为每个 turn spawn 一个 CLI 子进程，stdin 写 prompt，逐行读取 stdout、读取 stderr、核对退出状态，finally 清理/杀子进程。env 显式覆盖可阻断默认继承；resume 参数交给 CLI。TS 对象不是任务责任的持久权威。
- **源码事实，未运行 Rust 层**：codex-rs/rollout/src/recorder.rs:77—149 将规范 rollout、writer task 与锁归属分开；record_canonical_items:1013 只是入后台队列，persist:1031、flush:1052 等待 writer ack，调用方不能把入队返回当持久提交。load_rollout_items:1069 负责重读。thread/revert 的注释在 101—104 描述稳定 thread 身份对应新的不可变 rollout；这也不等于工作区/外部效果回退。
- **源码事实，未运行宿主层**：codex-rs/app-server/src/thread_state.rs:99 起的 ThreadState 保存运行时摘要、监听 generation，336 起的 ThreadStateManager 管理连接订阅。客户端连接、线程执行对象与 rollout 是不同生命周期，不能推导“窗口退出=持久任务取消”或相反。

## 已执行机制实验

先登记 protocol.json，再执行原始 TS SDK 源码，通过显式 CLI fixture 运行真实 OS 子进程。evidence/client-001 保存每个 stdout/stderr、child JSONL、argv/PID 和源码哈希。固定 CLI 是被声明的边界输入，不是自写 SDK 或 Rust Session 替身。

1. 完整事件流返回回答/usage/id；新包装器的 resume 参数确实传给子进程。
2. turn.failed、坏 JSON、CLI exit17 均拒绝；abort 后 SDK 抛 AbortError、子进程收到 SIGTERM。
3. **缺口**：同样的 agent_message 后直接 EOF/exit0、没有 turn.completed，run 仍返回 finalResponse，usage=null。`completion_guard_supported=false` 是能力反例，不能被 fixture 检查通过掩盖。

这证明可测试的 transport/parser/process seam，未证明真正 CLI/Rust Session 在崩溃后恢复、任务不重启副作用或模型可用性。client-001 的“resume”只验证 argv，不是持久恢复成功。

## 可用机制、拒绝与组件契约

可独立借鉴：结构化事件流、同一 thread 多 turn、显式错误与中断、可替换 exec 路径、完整环境覆盖、writer ACK 和可观察后台失败。候选拆分是 Session 适配器/事件规范化器、输出终态判定器、局部调用客户端，而非整个产品底座。

本系统适配器须要求明确 completion、当前 execution 关联、合法完整 schema，拒绝截断/未知/畸形流；自行持有结果身份与责任提交记录，不能把 usage、SDK Promise resolve 或界面“完成”当 P14。Rust persist/flush 的真实耐久与故障条件须在 G3 契约和后续组件实验独立验证；SDK abort 也不证明所有后代进程写能力撤销。

不采纳：用 Codex 内置 loop 决定本系统外部策略、用 TS Thread 对象承担持久调度、默认继承宿主环境、以最终自然语言作为完成证据。保留 Codex 作为局部能力/体验参考和适配候选，不据品牌提前选择完整宿主。

## 来源、许可和复现

官方来源 https://github.com/openai/codex ，identity.json 固定 HEAD 与 Apache-2.0 许可证原文摘要/哈希。源码锚点均相对 research/repos/codex；source-anchors.json 提供当前哈希。构建运行依赖仅隔离 tsx/esbuild 与 Node24，版本见 dependencies.json；没有安装或运行商业客户端，没有传入真实密钥、模型调用或 Rust 二进制。

复现：先按 setup-002 的 npm 命令准备隔离工具，再 `python3 -B research/codex/run-experiment.py --batch <全新批次>`。setup-001 的后台安装进程随桥接结束未完成，空日志不作为安装成功证据；setup-002 保存真实等待结果。

## 独立覆盖审查补充：用户交互与展示链

原研究清单还要求理解用户发起、干预、继续和执行过程展示；此前侧重SDK的章节没有完整覆盖这一点，按交叉审查补入固定源码映射。这里均为开源Rust TUI源码阅读，不是已运行桌面产品/完整交互测试。

- 发起：codex-rs/tui/src/chatwidget/input_submission.rs:112 接收UserMessage并处理未配置/限流时的输入队列；app_server_session.rs:1315 的turn_start把用户消息id、thread、cwd、权限等转成结构化TurnStart请求。输入预览与实际受理是两个边界。
- 干预：同文件1371的turn_interrupt以thread+turn发送请求，1397的turn_steer把新输入定向到正在运行的turn。命令发出/请求返回不是目标进程已无写能力的证明。
- 继续：tui/src/session_start.rs:29—51把Resume与Fork分成明确动作，Resume按thread_id调用resume_thread；其恢复展示也可能重放既有通知，不得视为新业务执行。
- 过程展示：chatwidget/protocol.rs:4统一接收ServerNotification，67/86区分TurnStarted/TurnCompleted，90/93区分ItemStarted/ItemCompleted，96接收AgentMessageDelta，并显式标记ResumeInitialMessages等replay情形；streaming.rs:182把delta交给streaming处理，plan流另有缓冲、cell提交与重绘。展示是协议的投影，消息文字、动画和重放都不是额外权威状态。

可借鉴的是输入意图→结构化请求→有身份的事件→展示投影的分层和恢复/实时事件区分。完整TUI键盘流程、拒绝/中断/steer竞争、断连重连、产品云端责任尚未运行；原client-001实验的结论范围保持不变。
