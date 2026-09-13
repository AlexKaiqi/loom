# OpenHands SDK 与 Automation：局部会话和持久责任

研究单元包括官方 software-agent-sdk 与关联 automation，两者算一个主清单项目，固定 HEAD 分别为 9c3571a694547734002518bd94b3cb41a187f9b6 与 645f20470168e25dcb5cf3dcf3ec5a10109e731b。焦点为 H02/H03/H08/H09/H10；开源身份及许可在 identity.json。

## 完整职责链和权威状态

维护方 README 区分 SDK/Agent Server 的 agents、tools、conversation、workspace、events 与客户端 API；Automation 负责 schedule、webhook、run history、dispatch。Canvas/UI 不属于本次被运行机制，也不承担权威完成判断。

**SDK 源码**：conversation/impl/local_conversation.py:380 创建 ConversationState；393 指明 base_state.json 是恢复 agent 配置的来源。1921 起的 run 驱动 agent.step、暂停、确认、stop hook 和终态；这是既有局部 loop，不是本系统要求的外部策略本身。remote_conversation.py:1132 的 run 可 blocking=false，只负责 POST run；阻塞等待采用 server 状态并防止旧 terminal/初始 WS snapshot 冒充新 run 完成。agent_server/conversation_service.py:675 起管理目录、持久状态加载、start/resume/delete，和客户端连接独立。

**事件与投影**：conversation/state.py:315 append_event 给 parent、追加原始事件、推进 HEAD；339 起 View 从活动分支重建，是派生读视图。event_store.py:180 起 append 用 FileStore.lock、同步磁盘 marker、拒绝重复 ID/不存在 parent 后写事件；LocalFileStore 的缓存注明独占文件假设，锁注明 NFS 不可靠。不能把这种路径 containment 当隔离边界，也不能把缓存当最终权威。

**Automation 源码**：models.py:145 的 AutomationRun 表兼任持久待分发队列；scheduler.py:147 起 poll_and_schedule 先轮询与更新 ALL fetched 的 last_polled_at、创建 PENDING，然后 commit。utils/run.py:163 create_pending_run 的返回仍需调用方 commit。dispatcher.py:537 先在 DB 标 RUNNING/commit，再以 asyncio.create_task 启动实际执行；537—616 存在真实跨设施交接窗口，须结合 watchdog/稳定远端身份核对才能支持本系统 H03，不能从“有 run 表”断言自动恢复完整工作流。PostgreSQL 有 SKIP LOCKED，SQLite 明确只假设单调度进程。

## 实测与反例

protocol.json → evidence/events-001 实际运行固定源码 EventLog/LocalFileStore/MessageEvent，独立 Python 进程读写 Linux 原生文件。退出后重读3条完整消息、root→branch B 投影、保留 branch A、同 ID 改内容拒绝且原文不变、4进程各追加2条（最终8条精确内容）均成立。坏 JSON 在读取时显式报错；这不是断电/fsync 测试。

**细化后的缺口**：events-001 的缺中间文件案例在 path_to_root(3) 抛 KeyError，所以 summary 的 gap_fails_closed 仅适用于“显式引用缺失 branch”操作。单独先登记 gap-protocol.json 后，evidence/gap-002 直接新建并迭代 EventLog，返回 count1 的连续前缀而不拒绝构造；尾部第3条仍在磁盘。完整性必须另做可验证尾/序列承诺，不能用能迭代作为完整历史已恢复。旧观察没有覆盖或改写。

automation-protocol.json → evidence/automation-001 实际运行 automation scheduler + SQLAlchemy + aiosqlite，无 dispatcher。三条定义中 A 不应运行、B/C 每分钟应运行；batch1 三次轮询实际创建数量0,1,1，轮询时戳轮转。调度进程逐次退出后，独立 sqlite3 读取仍有2条 PENDING；立即重轮询没有新记录；仅调用 create_pending_run 再 rollback 的负对照没有被接受的记录。该结果支持“责任记录可脱离阻塞进程”，不支持远端效果恰好一次或无界公平性。

## 可复用边界与不采纳

候选独立组件：不可变原始事件+分支投影、持久会话目录与客户端状态协议、持久待处理表/调度器公平轮转。需本系统契约补齐完整历史校验、稳定已接受决定关联、事务外远端接受核对、接管前实际停止/撤权、外部策略重建和独立产物验收。SDK 原有 agent.step loop 可作为受约束局部 Session，不应固化成本系统底座或隐藏完整状态。

不采纳：把 LocalConversation 完成/Automation COMPLETED 等同业务验收、把 file path normalize 当安全沙箱、在 SQLite 上未经验证横向启动多 scheduler、进程 create_task 之后就认为持久交接闭合、把 EventLog duplicate rejection 当幂等结果查询。

## 许可、依赖和运行范围

两仓库均按各自 LICENSE 保留（identity.json），source-anchors.json 固定源码哈希。SDK clone 版本1.47.0；Automation pyproject 明确依赖 SDK/Workspace1.46.0。因此在两个隔离 venv 分别运行，未擅自替换版本或声称1.47与Automation组合已验证。dependencies.json 给出实际安装分发版本与许可证元数据，setup日志保留全部安装结果。模型相关依赖虽安装但没有创建 LLM/发送模型请求；子进程得到空白 fixture HOME 和最小环境，遥测无项目key。

复现分别执行 run-events.py、run-automation.py，必须使用新 batch；gap-002 的原始 worker 命令及其不变输入目录记录在 gap-protocol.json。首次 setup-001 的后台进程未被等待，不计成功；setup-002 与 automation-setup-001 才为完成安装证据。
