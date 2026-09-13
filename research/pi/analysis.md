# Pi：已有真实持久局部Session，但operationId不是幂等受理键

研究P01/P07/P12、H02/H10。固定commit71dca871bc80b6bc97be37f0ca3189399d651fff，组件0.85.1，MIT。不是旧版“只靠内存loop”的Pi；本提交已有StorageBackedSession、持久operation状态和lane API。身份与依赖见[identity.json](identity.json)。结论仅用于G2候选比较。

## 源码事实与权威归属

[Session类型](https://github.com/earendil-works/pi/blob/71dca871bc80b6bc97be37f0ca3189399d651fff/packages/agent/src/harness/session/types.ts#L530)提供entry树、typed values/list、独占mutate及存储后端。JsonlSessionRepo/JsonlStorage用format4 JSONL事务行记录条目和值；还有独立sqlite-node后端。本实验仅JSONL。状态权威应留在Session；Runtime引用Session/operation/entry，不能再复制一套可竞争的“已完成”记录。

[Lane.accept](https://github.com/earendil-works/pi/blob/71dca871bc80b6bc97be37f0ca3189399d651fff/packages/agent/src/harness/runtime/lane.ts#L574)把prompt条目、branch tip、op.meta/op.state和lane.state合并commit；drive另行启动。createAgentHarness的restoreSession仅读持久状态、验证lane及operation关联，不自动触发模型、工具、hook或计时器。getResult(operationId)从Session读取终态记录；终态含tipId，实际回答由对应entry查得，不是把回答文字重复保存到Runtime。

局部状态机包含starting/checkpoint、assistant ready/effect_pending、工具effect_pending/outcome_ready、deferred/retry、summary/navigation等。工具有稳定invocationId（预留结果entryId）和operation/turn/source关联。[恢复工具](https://github.com/earendil-works/pi/blob/71dca871bc80b6bc97be37f0ca3189399d651fff/packages/agent/src/harness/runtime/drive/tools.ts#L515)只在记录及当前工具均声明replay=safe时重放；否则用持久progress合成明确unknown结果。未知效果因此不会被这条恢复分支伪装成成功，但后续模型/策略如何处理还需外部限制。

策略扩展入口为HookRegistry、tools、systemPrompt回调、entryProjectors和toProviderMessages。before_run_end可返回followUp，transform_context负责投影。Session原条目与投影分层可复用；自定义hook是普通代码，重启后重新注册，不自带harness版本、回调副作用或完整决定关联的持久契约。

## 实测事实

先登记[protocol.json](protocol.json)，再执行[experiment.py](experiment.py)+[worker.mts](worker.mts)。实际源码通过TSX加载，使用上游fauxProvider固定回复；实际自定义工具append目标文件。Python父观察器读取目标效果/query审计/Session文件，模型不读取oracle。

[mechanism-002](evidence/mechanism-002/run.json)：
- 进程A只accept，0模型/工具调用后退出；B恢复相同open operation，仍0调用、结果缺省；C按同ID drive获得固定回答；D读取原始终态及回答entry，0模型调用。
- 普通策略1次模型请求；外部before_run_end追加一条followUp后2次，继续输入及第二回答实际存入Session。
- 两个独立副本分别重交已完成的同ID+同内容、同ID+改内容，均返回ok并形成新的open operation，而getResult仍返回该ID旧completed记录。严格幂等/冲突契约失败，不能直接将operationId用作Runtime执行去重键。
- 工具真实append后对唯一worker SIGKILL。unsafe路径重启附着无调用，drive不重放原工具，效果仍1次，原fixed-call关联及unknown文本保留。
- 同样append工具错误标记replay=safe的相关对照，恢复后效果变2次。标签是调用方承诺，不是框架替调用方证明幂等性。

[mechanism-001](evidence/mechanism-001/run.json)正常和同ID观测保留；其crash观察器拒绝tsx CLI转译的137退出码。改成node直接--import tsx后按原-9判据执行新批次，没有放宽阈值。

## 可复用契约与缺口

| 局部候选 | 已有证据 | 正式采用前必须补 |
|---|---|---|
| SessionRepo/Session/entry查询 | 跨进程原始记录恢复 | 后端持久性、并发写者/保留期契约 |
| lane accept/drive/getResult | 受理与启动分离、原结果可查 | 严格受理ID+内容/来源/版本绑定，拒绝重用已完成ID |
| unsafe tool恢复 | 不盲目重放，明确unknown | 上层实际查询或暂停，禁止将synthetic未知当成功/任务完成 |
| hook和投影接口 | 外部继续策略实测 | 稳定已接受决定、hook版本及副作用边界；单次局部执行颗粒度 |

public drive是运行到settled/waiting，不是“任意完成一个模型/工具动作就原子交给外部继续”的通用单步API。直接将整个native run当一个Runtime步骤是否足够，需要G3先冻结lore执行颗粒度；不能因存在内部checkpoint就声称外部每个决策已受理。

OperationRequest没有source_result/harness_version字段。上述同ID缺口已经否定裸API的完整受理契约；本次未为每个不存在字段设计伪测试。需要最小适配合同，不建议fork/复制整个Pi或另造框架。若适配变成第二个Session权威则应重新评估职责划分。

JSONL Node append路径没有显式fsync（NodeExecutionEnv.appendFile），repo.openSessions排他是实例内Map；本次没有实测跨实例竞争或掉电，不能推断强持久/排他保证。sqlite-node是另一个可独立验证后端候选，尚未运行。

npm ci冻结lock并禁止生命周期脚本。尝试直接构建chord/telemetry成功，ai构建缺生成模型catalog且Google SDK枚举类型不匹配，失败保留[build-001](evidence/build-001/run.json)。随后按核心入口本身无catalog副作用的设计，用路径映射运行实际核心源码；没有伪造catalog或宣称完整分发构建成功。Node24.21.0，TSX/依赖锁见identity。线上模型、全部扩展、SQLite、远程服务/传输、安全边界、长期性能均未验收。
