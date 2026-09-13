# DBOS：步骤恢复与持久等待的实际边界

状态：G2相关机制已实测，待独立复核；不构成组件采用/系统通过。Python固定83805fd84494c85ea09105443884a2786152d921；TypeScript关联仓固定594da805891e37bc3bc42aa0976379bbcd4350bf，两仓按原清单计一个项目。Python按原源码安装2.32.0a16，48个已安装源码模块逐一与checkout相同，见research/environment/python-runtime-manifest.json。

## 职责、模型与状态

普通workflow按稳定ID受理，workflow_status记录运行/排队与版本归属，workflow_input/output持有内容，operation_outputs保存步骤结果，notifications/events提供持久通信；_recovery.py通过重新入队和原子领取恢复pending，已保存步骤的返回值供重放使用。源码并未承诺任意外部效果天然与结果记录原子。

Python公开DBOS.workflow/step、start_workflow/retrieve_workflow/send/recv可直接复用。当前_dbos.py:1797—1809的sync sleep在记录唤起时间后time.sleep；_sys_db.py:3646—3671的sync recv保留Event.wait循环。async版本使用await减少阻塞线程，但仍有待完成执行上下文；不能仅凭async关键字证明任务计算已完全释放。配置允许本地SQLite，实验使用它，不把结果推广为Postgres、集群或商业Conductor。

TypeScript源码对照：src/dbos.ts:1480把recv关联workflowID和步骤ID交给systemDatabase，sleepms记录后通过Promise/定时器等待；src/system_database.ts把实际payload移到workflow_input/output。两语言共享持久记录/重放机制方向，但本轮运行证据来自Python，未谎称TS栈也被执行。

## 先行协议与实际观测

protocol-001在worker/observer前登记D01—D04。worker只定义真实DBOS应用和本地文件效果，experiment作为独立父进程读取SQLite、文件与/proc；全部旧进程先确认消失再启动新的解释器。evidence/run-002保存完整原始表、线程栈、OS等待点及日志。

| 问题 | 实际观察 | 结论边界 |
| --- | --- | --- |
| 已确认步骤恢复 | SQLite已有步骤返回的原UUID，SIGKILL之后新进程结果仍含同UUID；独立fsync计数文件只写一次 | 所测步骤确认边界可复用，不是从头重推生成近似结果 |
| 输入冲突 | flow-1完成后以changed参数重交同ID，没有异常而直接返回original的已存结果，持久input也仍是original | 不覆盖旧值，但未拒绝内容冲突；需按本系统完整请求合同补严格受理边界 |
| 等待驻留 | 3个等待workflow对应3个实际线程栈进入recv，/proc的native TID等待点为futex_wait_queue_me；杀进程后它们消失而3条PENDING记录仍存在 | 持久可恢复成立；原生sync recv并非任务等待资源归零。共享进程承载线程不改变任务专属计算归属 |
| 未确认外部效果 | 受控step先fsync效果文件，尚无step输出记录时被杀；释放门闩后新进程恢复，同操作实际写入两次 | 不能用step装饰器独自保证非幂等效果安全重试；需要原执行身份/查询与明确未知处理 |

run-002的10项观察检查通过。D04观察到重复是预期要揭露的候选缺口，不是本系统允许重复效果。run-001保留观察器误读旧inputs列造成的FAIL，D04当时未跑；observer-repair-001说明改为当前真实表的依据，判据未弱化。

## 取舍与可独立验证组件

保留候选：稳定步骤返回值查询、队列原子领取与恢复、已保存输入/版本和通知；可围绕明确的有限推进阶段独立适配，不要求全部Harness成为纯函数。普通workflow重放须遵守确定的步骤次序，把非确定行为放入受记录步骤；已接受的外部决定与真实执行效果还需匹配本系统契约。

不直接采纳把整个长期Harness作为sync workflow常驻等待；不把workflow取消视作沙箱子进程停止；不把同ID复用等于完整内容冲突检查；不把未确认step自动重试作为不可查询外部效果的默认恢复。必要适配应与Pi等既有Session能力比较，避免在Runtime另造一套竞争的局部结果事实流。

Python/TS项目MIT许可，LICENSE及相关锁文件须保留；所装依赖包含SQLAlchemy(MIT)、psycopg及binary(LGPL相关声明)等，精确版本和原元数据列在environment manifest。这里没有作整个第三方分发合规的笼统保证；采用实际模块/分发方式时核对相应许可文件与通知。

复跑：使用固定源码构建的research/.venvs/runtime-research/bin/python research/dbos-py/experiment.py NEW_BATCH。每批新建临时数据和原始证据。源码初次安装因浅克隆缺少SCM版本祖先失败；只补tag/历史、不改HEAD后构建成功，失败与修正均保留environment记录。

依据：[官方workflow文档](https://docs.dbos.dev/python/tutorials/workflow-tutorial)、[Python固定源码](https://github.com/dbos-inc/dbos-transact-py/tree/83805fd84494c85ea09105443884a2786152d921)、[TypeScript固定源码](https://github.com/dbos-inc/dbos-transact-ts/tree/594da805891e37bc3bc42aa0976379bbcd4350bf)。这里的运行结果和资源判断来自保存的本地证据，非由文档措辞推断。
