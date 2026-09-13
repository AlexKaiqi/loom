# DeepSeek Harness：单一事件Session与真实冷恢复，恢复模式的尾部容错须单独约束

研究P01/P07/P12、H02/H10。commitc291e7961a515f6d7af9304e7fd1d257929aef26，根0.1.5-rc.2（developer preview）。根MIT；实际native/system文件锁代码BSD-3-Clause，不能只记根许可证。固定依赖与引用见[identity.json](identity.json)。

## 源码事实与权威归属

核心由Cordis插件组装：LlmRuntime、SessionStore、SessionProjectionRegistry、SystemPrompt、ToolRuntime、AgentRegistry、AgentLoop；JSONL持久插件在loop之前挂载，以便生命周期释放时先排空writer。Session是typed append-only event log，模型history、surface、请求header及其它投影来自同一记录。[session/src/index.ts](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/core/session/src/index.ts)及surface/request-header模块负责该边界；surface replace记录替换关系，不是删掉raw log。

AgentLoop普通代码发起turn/step、消息、tool/call和tool/result事件。Model-visible iff logged是维护方目标；它不等于每个live event已落盘。SessionStore.flush需被producer显式await，write-behind不能冒充确认。持久handle.append复制并验证批次、连续序号后写入；flush/close形成相应barrier。[storage.ts](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/session/session-persistence-jsonl/src/storage.ts#L187)

[resumeWith](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/core/agent-loop/src/index.ts#L844)先取得write handle，再读物理有效前缀，追加冷恢复closers，准备新Session、存未保存后缀后发布。JSONL持有真实POSIX flock到handle释放；无租约超时驱逐活写者。[lease.ts](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/session/session-persistence-jsonl/src/lease.ts#L70)

[repair.ts](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/core/session/src/repair.ts#L29)区分助手提出tool call但未记录开始与已记录开始无结果：分别生成TOOL_NOT_STARTED和TOOL_OUTCOME_UNKNOWN；后者cites tool/call seq，补step/end和interrupted turn/end。该信息可供Runtime决定查询/暂停，但提示文字并不强制未来模型不得重试。

外部策略通过waterfall agent/pre-step（必须next()）、工具注册、system prompt和projection插件施加。followup/inbox是新输入入口，SessionId是会话身份，不能直接推断执行请求幂等键或harness版本绑定。

## 实验、失败保留与更窄结论

[protocol.json](protocol.json)先于执行；[experiment.spec.ts](experiment.spec.ts)加载真实源码插件/原生flock，shipped MockAdapter给固定回复，真实fixture工具append目标文件。每阶段是新的Node/Vitest进程。Python[experiment.py](experiment.py)检查原始记录/独立目标效果；没有真实模型密钥。

[mechanism-002](evidence/mechanism-002/run.json)正常/恢复/造持久前缀/冷恢复4阶段：
- 真loop2次请求、工具效果1次；Session物理记录含工具结果、UTF8原始观测和回答。活writer的第二resume明确拒绝。
- 新进程resume同ID，模型请求0，原事件前缀及derived messages完全一致；再followup才产生新请求，效果不重跑。
- 单独持久前缀通过实际handle.append构造；新进程resume分别得到not-started/unknown及正确sourceEventSeqs；无模型调用、原前缀不变。这里是实际冷恢复机制实验，不声称测到了任意真实工具崩溃切点。
- 无换行torn片段被裁掉并恢复。
- 两项原判据未通过，run.status保留INVESTIGATE：第一恢复调用header优先reason=resume，外部series标记不会另记series；完整换行的坏尾行，在未遇到后续turn/end时也被恢复读取器截掉，而非拒绝。

第二项的确切范围由[format.ts475—515](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/session/session-persistence-jsonl/src/format.ts#L475)确定：recoverable模式保存首个解析/解码错误，跳过后续行；若遇到turn/end则抛错误，否则保留此前committedBytes。结构上不支持的V3行另有先行拒绝，不能说所有坏行都容忍。不能把“最终能恢复对话”替换成“任何已确认状态都不丢”。是否误裁了系统已确认记录，必须以外层确认边界及真实故障用例检验。

为澄清这两个边界，先另写[protocol-supplement.json](protocol-supplement.json)，未改原oracle/失败：
[supplement-001](evidence/supplement-001/run.json)证实已有初始请求后，外部pre-step标记导致实际header initial→series；坏完整行后明确追加turn/end时，新进程resume拒绝，原错误文件保留，无模型调用。补充只支持这个更窄事实，未将原完整坏尾拒绝项改PASS。范围到此停止，没有追求探索全部绿色。

首次mechanism-001仅fixture漏括号，0tests，完整失败和原脚本保留。所有后续脚本修改为fixture修复/明确新问题，没有改上游代码。

## 适配判断与可引用资产

| 候选 | 可复用内容 | 适配债务 |
|---|---|---|
| Session/typed event log/surface | raw与投影分层，消息来源/序号/替换关系 | 明确lore权威范围，不复制第二套消息真相 |
| handle+JSONL+flock | 单写者与显式flush，实际重开 | 确认边界、严格恢复模式、保留期、断电/竞争实测 |
| interruptedTurnClosers | 区分not-started/unknown，可引用原tool call | 真实目标查询/暂停协议；synthetic错误不是已完成执行结果 |
| Cordis扩展入口 | 普通策略模块、生命周期dispose | 引入整套插件服务的成本、稳定策略版本/决定关联 |

优先比较局部Session能力；不因“所有东西皆插件”而移植整个产品架构。其完整模型请求重建、immutable generations/迁移、fork语义可作后续定向组件候选，未证明本系统所有要求。未采用默认容错裁尾作为lore确认状态恢复标准，也不采纳unknown提示作为自动重试授权。

Node24.21.0；pnpm11.7.0 frozen lock安装ignore-scripts。WSL无cc的真实失败见build-001；随后官方Ubuntu22.04容器安装build-essential，以本提交flock.c和同Node头按源码相同参数编译，仅docker cp传源和产物。镜像digest、dpkg版本、编译命令、system.node SHA和清理在[build-002](evidence/build-002/run.json)。没有替身锁、全局库升级或sandbox能力声明。此次compression=none；未实测Zstd、历史迁移全链、断电、跨进程并发抢锁（只实测同live写者冲突）、模型质量或长任务资源上限。

## 原清单补充：dsh 入口与文件记录（独立复核后补充的静态分析）

本固定提交的 [CLI args](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/apps/cli/src/args.ts#L126) 是 profile 启动器；“dsh session”不能直接当作已存在并实测的固定子命令。具体 [headless runner](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/bundle/headless/src/index.ts#L185) 创建新 sessionId、固定 provider/model、followup→whenIdle→sessions.flush 后从事件取回答；本轮实际实验直接使用同一底层 Agent/Session 服务，没有执行完整 CLI profile。已实测 Session 物理日志保存请求 header、assistant message、tool call/result 及内容；它不是任意工作区文件快照。

文件路径分两类：普通工作区经 [fs-local.writeText](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/fs/fs-local/src/index.ts#L175) 写目标文件并返回版本/可选 diff basis；[fs-observation-policy](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/fs/fs-observation-policy/src/index.ts#L21) 的观察状态实际存在以 session 对象为键的 WeakMap，供旧版本写保护，不是持久目录历史。工具呈现进入事件记录，但不能推导所有文件字节或外部 Shell 改动都可回滚。[workspaceFiles](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/api/workspace-files/src/index.ts#L356) 的变化流仅来自 instrumented fs/observed，不监视整个 OS。另有 [attachment-local store](https://github.com/deepseek-ai/deepseek-harness/blob/c291e7961a515f6d7af9304e7fd1d257929aef26/packages/attachment/attachment-local/src/store.ts) 保存被引用附件对象，不能替代 Surface/Workspace 两域版本。这里均为固定源码映射；未运行文件工具/附件全链、文件历史回滚或 CLI profile，未升级既有机制证据范围。
