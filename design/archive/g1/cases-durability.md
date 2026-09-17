# G1 持久性、确认与交付：预先定义的有限模拟用例

状态：**DRAFT_NOT_FROZEN**。本批有 28 个用例，尚待交叉审查和基线冻结；未实现或运行模拟代码，未证明任何真实系统性质。JSON 为用例协议的完整定义，本文解释其边界并提供索引。

依据 G0 已确认的原始要求、v5 §4.2—4.4、§5.1、§5.3—5.4、§6.1、§7.1—7.2 独立确定预期，再与顶层草案对照。抽象操作、状态路径与阶段词只用于模型验证，不是 Runtime API、业务状态协议、产品选型或新的 DSL。

## 独立判据与有限范围

每例包含原始 requirement IDs、初始状态、带参数的有限 actions、检查点 expected、错误变体和失败原因、假设及现实差距。案例内未单列的假设与 gap 继承 JSON 的 shared_assumptions 和 unverified_real_world_gaps；空数组不表示没有现实差距。

expected 用点分观察路径与 eq/ne/contains/set_eq 表达。aN 表示该动作完成后的状态；all 同时检查初始与每个动作后的状态。未知字段是协议错误；仅已声明身份映射中的缺项可观察为 null。比较值来自独立 fixture 和原始性质，不能由被测实现生成或修改。

归一化观察器可以适配不同状态存放方式，但不能改变判据含义。已确认内容与可解析引用是两项观察：只有 ID/路径/成功摘要不够，必须能由独立持久 fixture 返回原版本内容。外部效果计数、模型调用次数、实际进程停止和资源归属来自环境轨迹；Runtime 自述不能直接设置这些值。

每例最多两个 Surface、两个事件、两步、一份等待和有限身份。计数只区分 0/1/2/overflow，时间只区分承诺有效/过期。标签和数字是有限实验输入，不是生产路径、身份格式、容量或 SLA。

settle_enabled_recovery 在有限公平调度下驱动通用转移，默认每次最多 8 个启用转移。达到探索界限而没有完成覆盖为 INCONCLUSIVE_NOT_PASS；已受理工作在公平调度下形成停滞或循环为 MODEL_FAIL。这个界限不是实际时延承诺。冻结前可依据抽象阶段结构修订并保留版本，不得为通过而忽略未完成工作。

## 对后续模拟器的约束

模拟器必须解释复用的状态转移和 fixture 动作，不能按 case ID 硬编码结果，也不能从 expected 复制“正确状态”。恢复动作不得预设无条件成功；它必须读取实际存在的持久责任和可解析内容。

每例先运行合法转移，再运行其 known_bad_variant。变体针对通用机制，例如提前清旧责任、把通知当唯一待办、错误地把取消请求当停止、用重算覆盖受理决定。负对照不修改 expected，且必须实际违反该例 must_violate 列表中的至少一条。识别出变体名称但未运行状态变化不能算拒绝成功。

本批不预选跨组件事务、outbox、队列、数据库或消息产品；原责任覆盖未结阶段和已接受后继可以有不同实现。也不承诺所有传输与执行尝试恰好一次：用例检查稳定逻辑关系及已确认副作用不因重复/恢复被盲目重做。

## 三个不能互相替代的结论

1. DUR-006/010—012 检查未确认或未知结果的安全处理；存在确切查询缺口时，可以有依据暂停并保留责任。
2. DUR-007—009/020 检查承诺内的已确认结果和受理责任。永久停住、缺失已保存内容或仅明确报错/暂停，都不能通过。
3. DUR-026 只处理已事先结束保留承诺、且没有未结责任仍依赖该记录的历史缺失。不能用该例给 DUR-020 的提前清理找豁免。

## 与顶层草案的交叉发现

DF01：DUR-007 揭示普通模型/工具结果已保存，不代表调用可以结清。根 Agent 保留草案1并修订草案2/3；本角色已直接重读第4节，确认其明确要求未结解释/继续责任，只有新责任已受理或按 Harness 可终结的完整回答/有依据停止结果保存后才可结清。用例预期没有为了适配旧表述而降低。

DF02：DUR-028 不假定普通 Harness 代码恒定。A/op2 已被持久接受后，即使独立候选变成 B/op3，恢复也必须保留并实施 A；同身份冲突不得改写 A。DUR-007/027 的固定继续/终结函数只是相应 fixture，不能外推到一般代码。根 Agent 草案3的稳定决定/请求身份和已接受内容复用已直接复核，真实回调及执行器支持仍是 G2 证据债务。

## 现实差距

本批假设经确认的持久依赖事实在约定崩溃中保留，环境 fixture 能独立报告查询、停止及资源变化；它不能证明 fsync、消息服务配置、Session 继续点、真实进程树停止、连接释放或保留归档机制。

等待责任受理与正式进入资源已释放的等待状态分开观察：accept_wait 只证明责任持久接收；declare_waiting 还需必要状态保存与任务资源释放。共享服务可存在，后续被唤起的活跃任务可重新占用资源。真实释放时限、Linux 条件、负载和费用另行验收。

## 用例索引

| 用例 | 要检验的反例边界 | 原始要求 | 错误机制 name |
| --- | --- | --- | --- |
| DUR-001 | 写出字节不等于受理 | V5-A081, V5-A083, V5-A086 | bytes_implies_completion |
| DUR-002 | 受理、登记完成与启动三个阶段 | V5-A083, V5-A100, V5-B032, V5-B065 | acceptance_starts_model |
| DUR-003 | 保存后丢回执与相同身份重试 | V5-A083, V5-A084 | lose_request_identity_on_restart |
| DUR-004 | 同身份不同内容必须冲突 | V5-A084 | overwrite_conflicting_request |
| DUR-005 | 操作完成回执丢失可以查询原完成事实 | V5-A083, V5-A084, V5-A100, V5-B032 | query_causes_side_effects |
| DUR-006 | 未保存结果不能由易失内容猜测恢复 | V5-A010, V5-B084, V5-B085 | invent_unsaved_result |
| DUR-007 | 结果保存后至继续登记前崩溃 | V5-A073, V5-B025, V5-B028, V5-B040, V5-B085 | drop_responsibility_after_result |
| DUR-008 | 已受理下一步在启动前崩溃 | V5-A073, V5-A092, V5-B028 | volatile_next_step_acceptance |
| DUR-009 | 已确认恢复集合跨全部易失域丢失仍保留 | V5-A010, V5-A042, V5-A050, V5-B084, V5-B085 | sandbox_only_confirmed_content |
| DUR-010 | 未知副作用查询发现已完成，不重做 | V5-B015, V5-B020, V5-B041, V5-B086 | retry_unknown_before_query |
| DUR-011 | 未知副作用无法查询时暂停并保留责任 | V5-B020, V5-B079, V5-B086 | discard_unknown_operation_on_query_failure |
| DUR-012 | 暂时查无结果不等于安全重试 | V5-B015, V5-B016, V5-B086 | retry_on_nonfinal_not_found |
| DUR-013 | 目标条件发生于登记等待之前 | V5-A094, V5-A095, V5-A096, V5-B081 | ignore_preexisting_events |
| DUR-014 | 检查后登记之间发生条件 | V5-A073, V5-A095, V5-B081 | scan_subscribe_gap |
| DUR-015 | 条件发生于等待受理之后 | V5-A095, V5-A096, V5-B081 | ignore_future_events |
| DUR-016 | 明确起点排除不属于本次等待的旧事件 | V5-A090, V5-A095 | ignore_wait_origin |
| DUR-017 | 通知丢失且底座重启仍恢复等待交付 | V5-A073, V5-A094, V5-A096, V5-B034, V5-B081 | notification_only_worklist |
| DUR-018 | 读取事件视图不是消费完成 | V5-A092, V5-A093 | read_view_marks_processed |
| DUR-019 | 重复通知不重做已处理输入的实际动作 | V5-A073, V5-A084, V5-A092 | notify_creates_new_business_step |
| DUR-020 | 恢复承诺仍有效时不能过期删除依据 | V5-A071, V5-A090, V5-B085 | expire_promised_record |
| DUR-021 | 归档可改变位置但不改变恢复内容与身份 | V5-A071, V5-B084, V5-B085 | archive_leaves_stale_reference |
| DUR-022 | 等待期任务资源归零而共享底座可保留 | V5-A008, V5-A050, V5-A051, V5-A096, V5-B080 | preserve_task_waiter |
| DUR-023 | 等待确认必须晚于必要状态持久确认 | V5-A050, V5-A096, V5-B019 | release_before_durable_wait |
| DUR-024 | 取消受理不是进程实际停止 | V5-A057, V5-B017, V5-B018 | cancel_request_means_stopped |
| DUR-025 | 事件回放只恢复事实，不重做描述的动作 | V5-B087, V5-A092 | replay_executes_event_payload |
| DUR-026 | 承诺期外缺失也须显式报告，不伪造空历史成功 | V5-A071, V5-A090 | missing_history_means_success |
| DUR-027 | 保存结果后的停止策略不被恢复器强行继续 | V5-B028, V5-B029, V5-B031, V5-B067 | result_implies_automatic_continue |
| DUR-028 | 已受理决定 A 不因恢复后候选变为 B 而被改写 | V5-A073, V5-A084, V5-B027, V5-B028, V5-B085 | recompute_accepted_decision |

## 抽象操作词汇

每个操作均使用 {op, args} 结构。参数值取自对应 case；身份是有限域标签，cut 仅标明注入点，不可作为按例分支开关。

| op | 抽象语义 |
| --- | --- |
| transport_write | 仅由传输 fixture 确认字节写出；receiver_accepts=false 时不生成接收端受理事实。 |
| accept_request | 使接收端对合法请求完成抽象持久受理，建立原身份/内容关联；不自动完成操作或交付回执。 |
| lose_reply | 对应服务端阶段的回执未到客户端，caller_view 变为 unknown；不改变服务端真实阶段。 |
| complete_registration | 完成被受理登记的对象与 Harness 绑定，并产生可核对完成事实；不启动模型。 |
| explicit_start | 外部明确请求启动已合法登记对象；本有限轨迹只提交一次有效启动。 |
| resubmit | 以给定原请求身份和内容重交；同内容关联原请求，不同内容须冲突且不覆写。 |
| query_request | 按原请求身份读取服务端现有受理/完成事实并更新客户端认知，不重做操作。 |
| crash | 清除 args.domain 指定的易失进程/连接/缓存/沙箱；保留故障范围承诺持久的依赖事实。cut 为插入位置注释，不改变阶段转移规则。 |
| restart | 重新建立共享运行机制；不能凭启动本身伪造任务完成、模型结果或受理责任。 |
| recover_saved_state | 从承诺保存的引用/身份恢复实际可取内容和阶段；缺失时区分承诺内失败与已约定范围外缺失，不从旧易失内存猜测。 |
| save_result | 权威结果设施确认给定实际结果与操作/版本关联已保存；普通结果不是本次调用终态。 |
| settle_enabled_recovery | 公平驱动该用例已启用的恢复、外部解释、交付或启动转移，直到有限目标的稳定状态；不得按 case ID/expected 写状态。参见调度与界限规则。 |
| query_external | 由独立目标端 fixture 按原 operation 返回给定查询事实；found_completed、unavailable、not_found_nonfinal 有不同语义。 |
| recover_execution_result | 使用已查询到的同身份确定结果建立恢复引用；不能新发原操作。 |
| request_safe_continuation | 尝试继续未知操作；safe_retry_basis=false 时不得重试且须保留可追查的暂停依据。 |
| external_effect_occurs | 独立目标环境记录实际效果一次；可能来自未停止的旧请求/子进程，不由 Runtime 成功声明驱动。 |
| record_event | 权威事件 fixture 保存给定身份/位置/类型/载荷；位置仅在本有限单流内有序；通知与保存分开。 |
| begin_wait | 给出外部条件、目标和包含式历史起点，进入准备阶段；不是接受等待或创建模型业务等待命令。 |
| accept_wait | 确认外部等待责任及其必要起点/引用已持久接受；与资源实际释放及正式 declare_waiting 分开。 |
| scan_history | 以指定范围观察已有事件；扫描结果本身不是唯一未来交付依据，也不消费责任。 |
| notify | 发出指定已保存事件的可丢失唤起提示；不新造事件或业务身份。 |
| drop_notification | 丢掉对应提示而不删除已保存事件、等待或受理责任。 |
| read_input_view | 读取本次已交付文件视图；不确认处理完成、不删除结果或责任。 |
| request_expiry | 请求清除指定记录；必须遵守仍有效恢复承诺和责任引用，可拒绝或保留可读归档，不可静默缩范围。 |
| archive_record | 把权威记录迁移到抽象新位置，内容/身份及获授权可解析引用仍须成立；不是固定产品功能。 |
| release_task_resources | 请求并由环境 fixture 核对任务进程、连接、沙箱释放；executor_confirms 表示确有外部完成事实，不等于调用请求自身成功。 |
| declare_waiting | 报告任务已经进入本模型的稳定等待；必须先保存必要依据并完成该任务资源释放。 |
| request_enter_wait | 请求准备等待；保存确认 fixture 不可用时不能报告等待已安全接受或主动销毁唯一未保存状态。 |
| confirm_required_state_saved | 由持久设施 fixture 确认给定必要引用已保存，不从被测模型的自述产生。 |
| request_cancel | 记录取消请求，不直接更改依赖侧真实进程生存或确认结束。 |
| executor_confirms_stop | 由执行器 fixture 确认目标执行及参数指定子进程已实际停止，更新可核对结束事实。 |
| replay_events | 按范围重新读取已记录事实，不执行其正文描述动作；观察集合可去重，传输可重复。 |
| request_out_of_scope_history | 请求已明确处于保留承诺外且无未结责任依赖的历史；缺失须报告，不能伪造空历史恢复成功。 |
| accept_decision | 持久接受外部定义给出的决定身份、内容、源结果、版本及执行身份；一般解释代码不假定恒定。 |
| set_harness_candidate | 独立 fixture 改变如果再次求值外部代码会返回的候选；不得改写已接受决定。 |
| propose_decision | 再次提交同一稳定决定身份与给定内容；不同于已接受内容时冲突，不能用新执行身份逃避原责任。 |

## 原文版本

| 来源 | SHA-256 |
| --- | --- |
| harness-runtime-revised-v5.md | 700f8ed191ed24e913db40a33d14cbb57579b6f7f8ee6a38fa114c77f8df6865 |
| design/requirements/v5-a.json | cf97406b91c53874ee3212cc37341fd621560416e47520b0213e45b89d462a28 |
| design/requirements/v5-b.json | 3e03a0e79bb2c6cf310762cf780a2fb95b97c91f042730b00bd2076e5530938a |

交叉读取的顶层草案 SHA-256：5644cd02f5d6625690ba8ff9e90e7e4085606eba44eb532eb4c2de34314adeb4。该草案用于比较而非生成独立预期；后续若修改，应重新检查受影响用例，而非自动更换预期。
