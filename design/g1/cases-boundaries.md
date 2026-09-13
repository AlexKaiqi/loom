# G1：双域、写者、版本与事实边界用例预注册

版本：draft-2；状态：PREREGISTERED_DRAFT。21 个主轨迹，1 个附加缺失版本轨迹。尚未编写或运行模型；所有 Runtime 性质仍 UNVERIFIED。

原始来源是 v5 与已独立通过的 G0 要求。精确来源 ID、文件摘要、初态、op+args 动作及 path/eq/value 断言均在同目录 cases-boundaries.json。该 JSON 是此预注册的机器可读完整内容；本文件提供语义说明和审查索引。

## 有限模型边界

路径、对象身份、授权配置、实际写能力、owner 记录、内容版本、原始事实和投影视图分别表示。执行器的停止／失权输入不能由租约或 owner 变化自动推导。模拟器只能读取初态、op+args 和错误机制开关；不能读取 expected 或按 case ID 选择结果。

每个比较从最终状态按 path 段数组定位，数字段索引数组，eq 要求类型与值一致。缺路径、未知操作、没有观察或跳过附加轨迹都为失败。对照按 known_bad_variant 及 additional_mechanisms 登记；合法路径必须成功，不能全拒绝来取巧。

本批选择一个符合原文的有限解释：越权身份字段不产生授权；prepared 对象变化拒绝；冲突人工编辑先拒绝并保留提议；已存在的输入版本集合按绑定读取。其他等价实现可以后续另行注册，不能看到结果后换当前预期。

真实权限、完整进程树失权、路径竞争、快照和引用持久性尚须 G2/G3 真实环境验证。external_change 与 observe 类动作仅注入独立 fixture 观察，不是安全性证明。本批动作词仅用于有限模拟，不新增产品 DSL、命令或业务状态。

draft-1 的自然语言意图保留在每例 scenario_explanation；draft-2 只在实现前展开可执行判据。交叉审查冻结后方可实现模拟，任何标准更正需保存原因与旧版本。

## 共享操作语义

- `execute`：授权并唯一解析 target 或 location；校验登记对象身份；从 Runtime target profile 固定环境、身份与写对象，解释有限 write/cd 指令，输出 status/target/environment/identity/profile/handles/denied_writes。写禁止对象为逐条 denied_writes；请求本身可执行且允许部分合法效果。cd 不改变环境。非法目标 rejected 且无 host fallback。
- `external_change`：仅注入预先列明的外部输入变化，按 path 更新对象/别名/授权方配置/版本可用性。禁止修改 observations、预期、counter 或判据；此动作不是产品 API，也不是模型证明该外部变化已发生。
- `prepare_execution`：保存请求及核验时对象身份，不产生写效果。
- `execute_prepared`：实际使用前核对当前对象与先前授权对象；本批身份变化即 rejected。
- `start_process`：按 target 允许继承句柄与 parent_handles 交集建立进程，记录身份及句柄，不传递其他父句柄。
- `start_child`：仅继承已经受限的父进程能力，记录子进程，不恢复启动者原始能力。
- `use_handle`：同时检查进程持有句柄与句柄动作授权；允许返回 allowed，禁止返回 rejected。无句柄泄漏时不修改 registry。
- `change_owner_record`：只更改控制归属记录，不更改 effective_writers。
- `request_takeover`：对 resource 独立检查旧 effective_writers；存在其他写者则 blocked，否则设置唯一新写者并 granted。不能用 owner 或其他 Surface 锁替代。
- `attempt_write`：仅 effective_writers 中该 resource 的写者可修改 objects.resource.value，返回 allowed 或 rejected。
- `observe_revocation`：独立 fixture 给出的已实际撤销写能力见证；只移除指定 resource 的指定旧写者。不能由 lease/owner 变更自行调用此操作。
- `request_cancel`：记录取消请求并返回 requested，不推导任何进程或写能力已停止。
- `observe_process_exit`：独立观察到指定进程退出，移除该进程的写能力但不推断子进程退出。
- `read_object`：读取对象内容与 revision 到 observation，不改变权威对象。
- `conditional_edit`：base_revision 等于实际 revision 时编辑并递增；否则 conflict，保持对象并向 records.rejected_edits 保存提议。
- `capture_object_version`：按 reference 保存所读实际对象内容与 revision，供版本核对。
- `begin_render`：绑定已存在的 input_set 名称及其版本化文件集合，初始化 materialized。
- `render_read`：从绑定 input_set 读取一个文件到 render.materialized，不能读取当前 mutable input 替代。
- `finish_render`：核对 materialized 与预先声明 input_set 相同；相同 complete，否则 inconsistent，禁止伪报相同版本。
- `render_all`：按绑定 input_set 完整读取后使用与 finish_render 相同检查。
- `capture_snapshot`：依据 required_references 收集全部实际依赖内容并保存清单；缺引用时 incomplete，不能仅收集 tracked 内容并冒称 complete。
- `restore_snapshot`：从已捕获 snapshot 清单恢复到 restored.snapshot；缺少必须内容则 incomplete，不从可变产物路径补成其他版本。
- `discard_volatile`：丢弃对应当前进程、连接或投影视图的临时内容；保持持久 records、input_sets、harness版本引用、snapshots 和责任。scope 不扩张为删除真实必须资源。
- `restore_domains`：按请求的 Surface/Workspace 版本组合更新 domain_versions 并向原 history 追加 rollback 记录；不改变 external_effects。
- `replay_history`：只读取历史；observation.side_effect_executions 为本操作实际产生副作用数，正确转移为 0，不清理历史。
- `submit_message`：根据 submission_grants 检查 principal 可做 application 或 register。application 仅写 app 声明，不通过名称升格；register 验证目录身份后更新 registry 并由 runtime 写确认。两者均不启动模型。
- `read_untrusted_content`：普通文本读取仅形成数据观察，control_actions 记录实际控制动作数；不由关键字或任意代码块产生动作。
- `read_input_view`：读取视图到 observation，不结清 records.pending 或删除已存结果。
- `mutate_private_view`：只修改已创建输入的私人副本；不能修改 events 权威来源或责任。
- `notify_existing_input`：重复通知只提供提示，不重建或结清独立交付责任。
- `regenerate_input_view`：由 events 中同一事件身份重建视图，不读取已篡改副本作为来源。
- `update_registration`：已授权管理输入显式更新 target 的目录身份和后续 Harness 绑定；requested_writes 不得超出原授权。
- `begin_step`：读取当前 Surface 绑定，将 Harness 版本身份写入持久 steps；不以 latest 作为模糊版本。
- `step_phase`：按 step 固定 Harness 版本读取 model/template/parser；来源不存在则 blocked，不能静默使用新版本。
- `trim_projection`：只修改模型视图并记录 truncated/source/required_context，完整 raw 和 pending/saved 保持。
- `read_source`：先检查 environment 对 reference 的 read_grants；允许返回完整 raw 版本，拒绝返回 denied；路径存在不覆盖权限或环境限制。
- `retry_operation`：存在 unknown 核对责任时 blocked，已有确认效果时 already-completed；仅已确认未启动或有已声明安全依据才可重新执行；本用例无这种未启动输入。
- `query_effect`：使用独立 fixture 的 external_effects 确认 op 真实效果；更新 saved 对应状态及责任，不增加效果。
- `project_context`：检查 required_inputs 全部可定位且保留实际 Surface/Workspace 版本区分；完整则 complete，缺失则 incomplete，不伪造空输入。

## 用例索引

| ID | 用例 | 断言数 | 主要错误机制 |
| --- | --- | --- | --- |
| G1-BND-001 | 双域授权写入与控制状态保持分离 | 10 | promote_runtime_worker |
| G1-BND-002 | 调用文本与 blocks 不得决定身份和启动权限 | 7 | caller_profile_override |
| G1-BND-003 | 无权或未登记目标必须拒绝且无宿主回退 | 7 | host_fallback_on_invalid |
| G1-BND-004 | 相同位置对应多个环境时不能选第一个匹配 | 6 | ambiguous_first_match |
| G1-BND-005 | 路径别名及授权检查后的目标变化不能穿透对象边界 | 8 | path_prefix_only |
| G1-BND-006 | 一次执行固定环境，脚本 cd 和内容不触发跨域路由 | 6 | route_from_cd |
| G1-BND-007 | 不可见目录不能代替继承端点和开放句柄隔离 | 8 | inherit_parent_handles |
| G1-BND-008 | 同 Surface 接管以旧写者实际失去写能力为前提 | 6 | owner_record_as_revocation |
| G1-BND-009 | 共享 Workspace 需要独立于 Surface 锁的写者协调 | 6 | surface_lock_is_workspace_lock |
| G1-BND-010 | 父进程退出或取消回执不足以证明整棵写者进程树停止 | 6 | parent_exit_as_tree_stop |
| G1-BND-011 | 人工编辑必须进入冲突和版本判断，不能被当作不存在 | 5 | ignore_external_edit |
| G1-BND-012 | 多文件渲染依据必须对应明确的输入内容集合 | 5 | read_latest_during_render |
| G1-BND-013 | 快照覆盖实际依赖的未跟踪文件和版本化产物引用 | 4 | tracked_only_snapshot |
| G1-BND-014 | 回退选择明确两域版本，同时保留执行历史与外部效果 | 5 | rollback_erases_history |
| G1-BND-015 | 应用同名声明与成功文本不能伪造 Runtime 确认 | 8 | event_name_is_authority |
| G1-BND-016 | 修改或读取输入视图不改变权威事实和消费责任 | 5 | view_is_authority |
| G1-BND-017 | 登记路径移动、删除和重绑定不得继续使用失效关系 | 7 | stale_registration_cache |
| G1-BND-018 | 已开始 Step 固定 Harness 的模型、模板及解析规则版本 | 6 | latest_harness_each_phase |
| G1-BND-019 | 裁剪仅改变投影，原始日志完整且可按授权取回 | 6 | trim_deletes_raw |
| G1-BND-020 | 裁剪与窗口推进不能删除未知结果的核对责任 | 6 | trim_drops_unknown |
| G1-BND-021 | 投影路径、版本与普通内容执行边界保持明确 | 7 | auto_execute_blocks |

## G1-BND-001：双域授权写入与控制状态保持分离

性质：P02, P05, P08。来源：V5-A024, V5-A025, V5-A035, V5-A036, V5-B003, V5-B004, V5-B005。

原始用例目的：

- 两次合法写入分别成功，实际身份和被改对象分别对应 S1 与 W1。
- 四次越界写入全部被拒；control、event-authority 和 S2-content 内容保持初态。
- Runtime Shell 的 Surface 编辑权限未派生出控制状态或其他 Surface 写权限。

动作序列：execute → execute → execute → execute。完整初态和参数见 JSON。

精确预期：

- `G1-BND-001-E01`：`observations.r1.status` 等于 `"executed"`。
- `G1-BND-001-E02`：`observations.r1.identity` 等于 `"runtime-worker-S1"`。
- `G1-BND-001-E03`：`observations.r2.identity` 等于 `"task-worker-W1"`。
- `G1-BND-001-E04`：`objects.S1.value` 等于 `"N1"`。
- `G1-BND-001-E05`：`objects.W1.value` 等于 `"R1"`。
- `G1-BND-001-E06`：`observations.r3.denied_writes` 等于 `["S1"]`。
- `G1-BND-001-E07`：`observations.r4.denied_writes` 等于 `["S2", "control", "event-authority"]`。
- `G1-BND-001-E08`：`objects.S2.value` 等于 `"S2-0"`。
- `G1-BND-001-E09`：`objects.control.value` 等于 `"C0"`。
- `G1-BND-001-E10`：`objects.event-authority.value` 等于 `"E0"`。

已知错误：把 Runtime Shell 等同守护进程身份，或因同 Namespace 而允许其他 Surface 写入。

失败原因：会在合法写测试通过的同时修改禁止对象，违反实际权限边界。 必须至少违反 G1-BND-001-E07, G1-BND-001-E08, G1-BND-001-E09, G1-BND-001-E10 中一条相关断言。

前提：

- 有限模型以对象身份和可写集合表示权限，所有控制对象初始有可比较内容；不指定 UID 或隔离产品。

现实缺口：

- 真实 Linux 身份、挂载、权限及对象变化需在 G2/G3 用环境外观测验证；模型授权集合本身不是 OS 隔离证据。

## G1-BND-002：调用文本与 blocks 不得决定身份和启动权限

性质：P02, P05, P08。来源：V5-B007, V5-B008, V5-A025, V5-A110。

原始用例目的：

- 含越权字段的请求可以被拒绝，或忽略不被信任的覆盖字段后仍使用 Runtime 授权配置；不能启动为更高权限。
- 进程启动前的身份、cwd、挂载、环境变量、端点、网络及资源配置均来自 Runtime 授权配置，block 文本不增加权限。
- 合法正对照使用既定身份与目标成功执行。

动作序列：execute → external_change → execute → execute。完整初态和参数见 JSON。

精确预期：

- `G1-BND-002-E01`：`observations.r1.identity` 等于 `"task-worker-W1"`。
- `G1-BND-002-E02`：`observations.r1.profile` 等于 `"restricted-task"`。
- `G1-BND-002-E03`：`observations.r1.handles` 等于 `["output-W1"]`。
- `G1-BND-002-E04`：`objects.control.value` 等于 `"C0"`。
- `G1-BND-002-E05`：`observations.r2.identity` 等于 `"task-worker-W1"`。
- `G1-BND-002-E06`：`observations.r3.status` 等于 `"executed"`。
- `G1-BND-002-E07`：`objects.W1.value` 等于 `"safe2"`。

已知错误：从用户字段或可编辑 block 覆盖实际执行配置。

失败原因：文本被当成授权源，可在进程启动前提升权限或开放控制端点。 必须至少违反 G1-BND-002-E01, G1-BND-002-E02, G1-BND-002-E03, G1-BND-002-E04 中一条相关断言。

前提：

- 超出授权的字段如何报错尚未冻结，本用例固定的是不得提升实际权限。
- 实际网络和资源限制在有限模型中仅为预声明配置身份。
- 本有限解释选择忽略非权威 claimed_profile 字段并记录既定配置；这是原文允许行为之一。拒绝式实现需另注册等价轨迹，不能自动把全部拒绝当本例通过。

现实缺口：

- 需验证实际进程启动参数、继承变量与约束生效；仅检查 Runtime 记录的配置不能证明实际落实。

## G1-BND-003：无权或未登记目标必须拒绝且无宿主回退

性质：P02, P05。来源：V5-B011, V5-B007, V5-A107。

原始用例目的：

- 三个非法请求均明确拒绝，不能以默认环境、当前目录或宿主继续执行。
- host_execution_count 始终为 0；仅合法请求产生一次 T-W1 执行。

动作序列：execute → execute → execute → execute。完整初态和参数见 JSON。

精确预期：

- `G1-BND-003-E01`：`observations.unregistered.status` 等于 `"rejected"`。
- `G1-BND-003-E02`：`observations.unauthorized.status` 等于 `"rejected"`。
- `G1-BND-003-E03`：`observations.unresolved.status` 等于 `"rejected"`。
- `G1-BND-003-E04`：`counters.host_executions` 等于 `0`。
- `G1-BND-003-E05`：`counters.executions` 等于 `1`。
- `G1-BND-003-E06`：`observations.valid.target` 等于 `"TW"`。
- `G1-BND-003-E07`：`objects.S1.value` 等于 `"S0"`。

已知错误：目标解析失败时使用当前工作目录或 host 作为 fallback。

失败原因：非法请求被真实执行，无法用路由错误日志抵消越界效果。 必须至少违反 G1-BND-003-E01, G1-BND-003-E03, G1-BND-003-E04, G1-BND-003-E05 中一条相关断言。

前提：

- 未登记或无权的判断来自预先给定登记与授权表，拒绝错误名称不冻结。

现实缺口：

- 实际适配器的异常路径、后台执行和宿主回退需在真实执行器侧检查。

## G1-BND-004：相同位置对应多个环境时不能选第一个匹配

性质：P02, P05。来源：V5-B010, V5-B011, V5-B012。

原始用例目的：

- 仅位置的请求被判为歧义并拒绝，不按登记顺序猜测环境。
- 显式获准目标 T-W1 唯一确定任务环境和身份，合法执行一次。
- 显式目标也必须通过授权核对；最后请求被拒。

动作序列：execute → execute → external_change → execute。完整初态和参数见 JSON。

精确预期：

- `G1-BND-004-E01`：`observations.ambiguous.status` 等于 `"rejected"`。
- `G1-BND-004-E02`：`observations.chosen.target` 等于 `"TW"`。
- `G1-BND-004-E03`：`observations.chosen.identity` 等于 `"task-worker-W1"`。
- `G1-BND-004-E04`：`observations.denied.status` 等于 `"rejected"`。
- `G1-BND-004-E05`：`objects.S1.value` 等于 `"S0"`。
- `G1-BND-004-E06`：`counters.host_executions` 等于 `0`。

已知错误：相同位置存在多个映射时选第一个，或认为显式目标天然已获授权。

失败原因：可能进入错误环境或借显式选择绕过授权。 必须至少违反 G1-BND-004-E01 中一条相关断言。

前提：

- 相同可见位置对应两个执行目标是有限反例，不要求生产环境采用该目录布局。

现实缺口：

- 真实跨挂载、不同环境内路径映射及目标标识如何保持无歧义需后续验证。

## G1-BND-005：路径别名及授权检查后的目标变化不能穿透对象边界

此例的 JSON 同时保存词法路径 path_strings 与实际解析对象 aliases；前缀错误变体依据统一 startswith 规则即可产生反例，不允许按别名或 case ID 硬编码行为。

性质：P02, P05。来源：V5-B010, V5-A036, V5-A048, V5-B078。

原始用例目的：

- 实际访问的对象与授权对象匹配才可写；四类别名均不能改变禁止对象。
- 授权核验后身份变化不得导致对新禁止对象执行；应拒绝或通过保持原对象绑定安全执行。
- 稳定合法对象可以被正常写入，不能仅靠全部拒绝满足本例。

动作序列：execute → execute → execute → execute → prepare_execution → external_change → execute_prepared → execute。完整初态和参数见 JSON。

精确预期：

- `G1-BND-005-E01`：`objects.control.value` 等于 `"C0"`。
- `G1-BND-005-E02`：`objects.S2.value` 等于 `"S2-0"`。
- `G1-BND-005-E03`：`observations.prefix.denied_writes` 等于 `["control"]`。
- `G1-BND-005-E04`：`observations.parent.denied_writes` 等于 `["control"]`。
- `G1-BND-005-E05`：`observations.symlink.denied_writes` 等于 `["S2"]`。
- `G1-BND-005-E06`：`observations.hardlink.denied_writes` 等于 `["control"]`。
- `G1-BND-005-E07`：`observations.after-swap.status` 等于 `"rejected"`。
- `G1-BND-005-E08`：`objects.W1.value` 等于 `"ok"`。

已知错误：只检查路径字符串前缀，或先解析授权再按可变路径重新打开执行。

失败原因：字符串合法或检查时合法不证明使用时对象合法，禁止对象会被写入。 必须至少违反 G1-BND-005-E01, G1-BND-005-E02, G1-BND-005-E03, G1-BND-005-E04, G1-BND-005-E05, G1-BND-005-E06 中一条相关断言。

附加错误机制：`check_then_reopen_alias`；prepared 请求执行时按可变别名重新打开但不核验对象身份；关联 G1-BND-005-E01, G1-BND-005-E07。

前提：

- 有限模型把路径与对象身份分开，并显式给定别名或替换事件；不假定 realpath 一次即可解决所有别名。
- 本轨迹选择发现 prepared 对象变化即拒绝；固定原对象句柄安全执行也是原文允许路线，但不在本批轨迹中自动替换预期。

现实缺口：

- 符号链接、硬链接、挂载别名、rename 与检查使用竞争须在实际 Linux 文件系统及执行边界实测。

## G1-BND-006：一次执行固定环境，脚本 cd 和内容不触发跨域路由

性质：P02, P05。来源：V5-B001, V5-B010, V5-B012, V5-B050。

原始用例目的：

- 第一次执行全程保持 task-W1 环境；Workspace 合法部分可以发生，但 Surface 写不能因 cd 自动获得另一环境权限。
- 第二次执行在 Runtime 受限环境中更新 notes，记录为独立执行且引用第一执行的实际产物。
- 第一执行的拒绝或非零退出不能抹掉已经生成的 Workspace 部分效果。

动作序列：execute → execute。完整初态和参数见 JSON。

精确预期：

- `G1-BND-006-E01`：`observations.task.environment` 等于 `"task-W1"`。
- `G1-BND-006-E02`：`observations.task.denied_writes` 等于 `["S1"]`。
- `G1-BND-006-E03`：`objects.W1.value` 等于 `"report-v1"`。
- `G1-BND-006-E04`：`observations.runtime.environment` 等于 `"runtime-S1"`。
- `G1-BND-006-E05`：`objects.S1.value` 等于 `"ref:report-v1"`。
- `G1-BND-006-E06`：`counters.executions` 等于 `2`。

已知错误：根据脚本中的 cd 或文件名把单次执行后半段改派 Runtime Shell。

失败原因：一次调用被隐式升级到另一环境，突破已锁定权限。 必须至少违反 G1-BND-006-E01, G1-BND-006-E02 中一条相关断言。

前提：

- 允许任务脚本出现部分效果；本例不承诺整段 Shell 原子性。

现实缺口：

- 真实 shell cwd、子进程继承与部分文件效果需执行器和文件侧核验。

## G1-BND-007：不可见目录不能代替继承端点和开放句柄隔离

性质：P05, P08。来源：V5-B006, V5-B013, V5-B005, V5-A056, V5-A087。

原始用例目的：

- 任务及其子进程不获得可用的控制端点、模型密钥或管理句柄；control-fd 即使目录不可见也不能被利用。
- 获准输出句柄允许合法写；受限 Runtime 上报可成功而管理操作被拒。
- 提交能力按当前范围限权，不因拥有任意一个提交句柄而拥有全部 Runtime 控制权限。

动作序列：start_process → start_child → use_handle → use_handle → use_handle → start_process → use_handle → use_handle。完整初态和参数见 JSON。

精确预期：

- `G1-BND-007-E01`：`processes.task-parent.handles` 等于 `["output-W1"]`。
- `G1-BND-007-E02`：`processes.task-child.handles` 等于 `["output-W1"]`。
- `G1-BND-007-E03`：`observations.task-control.status` 等于 `"rejected"`。
- `G1-BND-007-E04`：`observations.child-key.status` 等于 `"rejected"`。
- `G1-BND-007-E05`：`observations.output.status` 等于 `"allowed"`。
- `G1-BND-007-E06`：`observations.report.status` 等于 `"allowed"`。
- `G1-BND-007-E07`：`observations.manage.status` 等于 `"rejected"`。
- `G1-BND-007-E08`：`registry` 等于 `{}`。

已知错误：只隐藏控制目录但完整继承启动者 FD／socket／环境句柄。

失败原因：任务可经已打开通道改变控制状态，目录不可见不产生隔离保证。 必须至少违反 G1-BND-007-E01, G1-BND-007-E02, G1-BND-007-E03, G1-BND-007-E04 中一条相关断言。

前提：

- 句柄在模型中以不含秘密的符号表示；不读取真实凭据或控制端点。

现实缺口：

- 真实 FD 继承、socket 可达性、环境变量及子进程传递需目标环境实验；模型不能证明句柄不可伪造。

## G1-BND-008：同 Surface 接管以旧写者实际失去写能力为前提

性质：P03。来源：V5-A037, V5-A038, V5-A046。

原始用例目的：

- 仅 owner／租约记录变化时，不得授予 new 与 old 重叠的实际写能力；仍须等待或拒绝接管。
- 新写者开始前，effective_writers 不包含 old；接管之后 old 的延迟写被拒。
- 失权确认后 new 可以取得写能力并成功推进，避免只靠永久阻塞满足互斥。

动作序列：change_owner_record → request_takeover → attempt_write → observe_revocation → request_takeover → attempt_write → attempt_write。完整初态和参数见 JSON。

精确预期：

- `G1-BND-008-E01`：`observations.early.status` 等于 `"blocked"`。
- `G1-BND-008-E02`：`observations.old-before.status` 等于 `"allowed"`。
- `G1-BND-008-E03`：`observations.after.status` 等于 `"granted"`。
- `G1-BND-008-E04`：`observations.old-after.status` 等于 `"rejected"`。
- `G1-BND-008-E05`：`objects.S1.value` 等于 `"new"`。
- `G1-BND-008-E06`：`effective_writers.S1` 等于 `["new"]`。

已知错误：把 owner 变更、租约到期或收到取消请求当作旧写者已停止。

失败原因：实际写能力仍重叠，旧延迟写会覆盖新内容。 必须至少违反 G1-BND-008-E01, G1-BND-008-E04, G1-BND-008-E05, G1-BND-008-E06 中一条相关断言。

前提：

- effective_writers 是独立于 owner_record 的模型事实；停止／失权见证由独立输入提供，不由 owner 赋值推导。
- 这是串行写候选的有限交接场景，未冻结锁、租约或 fencing 产品。

现实缺口：

- 真实见证的权限、完整进程树及已有打开句柄的撤销效果需组件实验；模型检查仅能发现控制事实与实际能力混淆。

## G1-BND-009：共享 Workspace 需要独立于 Surface 锁的写者协调

性质：P03, P02。来源：V5-A037, V5-A038, V5-A063。

原始用例目的：

- 拥有不同 Surface 并不允许对共享 Workspace 无协调并发写；B 首次请求等待或拒绝。
- Surface owner 变更不直接改变 Workspace 实际写者集合。
- 只有 A 对 W-shared 实际失权后 B 才可独占写入，且其 Surface 可继续使用独立协调。

动作序列：request_takeover → change_owner_record → request_takeover → observe_revocation → request_takeover → attempt_write。完整初态和参数见 JSON。

精确预期：

- `G1-BND-009-E01`：`observations.early.status` 等于 `"blocked"`。
- `G1-BND-009-E02`：`observations.still-blocked.status` 等于 `"blocked"`。
- `G1-BND-009-E03`：`observations.after.status` 等于 `"granted"`。
- `G1-BND-009-E04`：`objects.W1.value` 等于 `"B-write"`。
- `G1-BND-009-E05`：`effective_writers.S1` 等于 `["A"]`。
- `G1-BND-009-E06`：`effective_writers.S2` 等于 `["B"]`。

已知错误：只锁 Surface，以为不同 Surface 即不存在共享写资源冲突。

失败原因：两个各自合法的 Surface 执行者仍可覆盖同一 Workspace。 必须至少违反 G1-BND-009-E01, G1-BND-009-E02 中一条相关断言。

前提：

- 本例采用共享 Workspace 独占写候选；资源身份 W-shared 不因两个别名而变成两份资源。

现实缺口：

- 共享存储、远程执行器和多节点资源身份一致性需要实际环境验证。

## G1-BND-010：父进程退出或取消回执不足以证明整棵写者进程树停止

性质：P03, P05。来源：V5-A038, V5-A057, V5-B017, V5-B018, V5-B013。

原始用例目的：

- 取消回执与父进程退出不能使 new_writer_allowed 变真，只要旧子进程仍有实际写能力。
- 子进程停止或其写能力确被撤销后方可接管；之后子进程写入尝试无效果。
- 取消请求、实际停止和获准新写者是可区分的记录。

动作序列：request_cancel → observe_process_exit → request_takeover → attempt_write → observe_revocation → request_takeover → attempt_write。完整初态和参数见 JSON。

精确预期：

- `G1-BND-010-E01`：`observations.cancel.status` 等于 `"requested"`。
- `G1-BND-010-E02`：`observations.early.status` 等于 `"blocked"`。
- `G1-BND-010-E03`：`observations.child-before.status` 等于 `"allowed"`。
- `G1-BND-010-E04`：`observations.after.status` 等于 `"granted"`。
- `G1-BND-010-E05`：`observations.child-after.status` 等于 `"rejected"`。
- `G1-BND-010-E06`：`effective_writers.S1` 等于 `["new"]`。

已知错误：只检测父 PID 不存在便记作任务已停止并放行接管。

失败原因：存活子进程或保留句柄仍能改文件，造成跨执行者写入重叠。 必须至少违反 G1-BND-010-E02, G1-BND-010-E05, G1-BND-010-E06 中一条相关断言。

前提：

- 进程集合在有限模型中仅含父、子两个符号；子进程写能力与父状态独立。

现实缺口：

- 真实孤儿进程、进程组、已有 FD、容器停止与不可中断任务边界需实测，模型不证明 kill 有效。

## G1-BND-011：人工编辑必须进入冲突和版本判断，不能被当作不存在

性质：P03, P04, P12。来源：V5-A047, V5-A037, V5-A039。

原始用例目的：

- 不能静默覆盖人工修改并声称没有竞争；应阻止越过协调的写、检测冲突后暂停，或按预先声明且保留双方版本的规则处理。
- 捕获或恢复记录须反映实际选用内容与版本；如果无法确定内容集合，不能报告一致输入或完整快照。
- 冲突处理后的人工修改及 Agent 提议均有去向，不用无条件覆盖制造成功。

动作序列：read_object → external_change → conditional_edit → capture_object_version → conditional_edit。完整初态和参数见 JSON。

精确预期：

- `G1-BND-011-E01`：`observations.stale.status` 等于 `"conflict"`。
- `G1-BND-011-E02`：`versions.S1-v1.value` 等于 `"human"`。
- `G1-BND-011-E03`：`records.rejected_edits.0.value` 等于 `"agent-from-R0"`。
- `G1-BND-011-E04`：`observations.resolved.status` 等于 `"applied"`。
- `G1-BND-011-E05`：`objects.S1.value` 等于 `"human+agent"`。

已知错误：只统计 Runtime 派出的写者，忽略人工文件修改并直接用旧值覆盖。

失败原因：丢失真实修改且伪造了无竞争版本历史。 必须至少违反 G1-BND-011-E01, G1-BND-011-E02, G1-BND-011-E03 中一条相关断言。

前提：

- 本例先注入一条可观察人工修改；不预设产品必须容忍绕过所有权限的无限制宿主攻击者。
- 合并、拒绝或强制加入协调的具体政策待交叉审查，只固定不得忽略实际写入。
- 本批选择版本冲突拒绝并保留提议，随后基于已知新版本显式修改；human+agent 是固定示例内容，不实现自动合并算法。

现实缺口：

- 人工编辑如何被约束或检测、未观测修改的边界以及工具兼容性需在选定存储与权限机制中验证。

## G1-BND-012：多文件渲染依据必须对应明确的输入内容集合

性质：P03, P04, P12。来源：V5-A045, V5-A047, V5-A046, V5-A090, V5-B047, V5-B046。

原始用例目的：

- 本次已声明输入集合为 R0 时，只能产生 T0+B0；若不能继续取得该集合则显式等待／失败，不能把混合 T0+B1 标为 R0。
- 允许以协调读取、稳定快照或一致性检查满足本例；不因此承诺任意普通多文件编辑原子化。
- 下一次选择 R1 的合法渲染得到 T1+B1，并且记录与实际模型输入一致。

动作序列：begin_render → render_read → external_change → external_change → render_read → finish_render → begin_render → render_all。完整初态和参数见 JSON。

精确预期：

- `G1-BND-012-E01`：`observations.r0-done.status` 等于 `"complete"`。
- `G1-BND-012-E02`：`renders.r0.materialized` 等于 `{"template": "T0", "block": "B0"}`。
- `G1-BND-012-E03`：`renders.r0.input_set` 等于 `"R0"`。
- `G1-BND-012-E04`：`renders.r1.materialized` 等于 `{"template": "T1", "block": "B1"}`。
- `G1-BND-012-E05`：`observations.r1-done.status` 等于 `"complete"`。

已知错误：逐文件读取当前内容，却仅记一个目录 HEAD 或首次读取版本为整次输入。

失败原因：会把来自不同内容集合的输入伪装成已声明版本，破坏可复现投影。 必须至少违反 G1-BND-012-E01, G1-BND-012-E02 中一条相关断言。

前提：

- T0+B0 与 T1+B1 的必要配对是此用例预先定义的输入契约，不把任意不同文件版本都视为错误。
- render_selected_revision 表示明确内容集合；不是强制产品使用单一 Git 提交。
- 本批有限解释假定 R0、R1 已保存且可读取，因此正确路径应完成对应集合，不能永久等待；现实一致性机制仍未选择。

现实缺口：

- 真实多文件一致读取、渲染期间人工改动、不可变内容可访问性和实际模型输入捕获需组件及系统验证。

## G1-BND-013：快照覆盖实际依赖的未跟踪文件和版本化产物引用

性质：P04, P12。来源：V5-A039, V5-A044, V5-A045, V5-A114, V5-B074。

原始用例目的：

- 恢复得到 tracked-template、未跟踪 block 的被验内容及 artifact-v1，全部与预定义内容匹配。
- 若必要对象未保存或不能访问，快照必须报告未完整／恢复不可完成，不能以 Git HEAD 存在报告成功。
- 产物引用能定位版本；恢复时不能用 report 当前内容 artifact-v2 替代原引用。

动作序列：capture_snapshot → external_change → discard_volatile → restore_snapshot。完整初态和参数见 JSON。

精确预期：

- `G1-BND-013-E01`：`observations.captured.status` 等于 `"complete"`。
- `G1-BND-013-E02`：`observations.restored.status` 等于 `"complete"`。
- `G1-BND-013-E03`：`restored.snap1` 等于 `{"tracked-template": "T0", "untracked-block": "B0", "artifact-v1": "REPORT1"}`。
- `G1-BND-013-E04`：`artifact_paths.report` 等于 `"artifact-v2"`。

已知错误：只保存版本库已跟踪文件及可变 report 路径。

失败原因：未跟踪依赖丢失且产物版本被静默替换，回退并未恢复承诺集合。 必须至少违反 G1-BND-013-E02, G1-BND-013-E03 中一条相关断言。

前提：

- 仅检查已明确纳入保留范围的三个对象；不承诺快照覆盖任意外部世界。

现实缺口：

- 真实快照、未跟踪文件覆盖、跨环境输出引用、内容保留和持久性需要候选机制实测。

## G1-BND-014：回退选择明确两域版本，同时保留执行历史与外部效果

性质：P04, P08。来源：V5-A035, V5-A039, V5-A040, V5-A041, V5-B050, V5-B087。

原始用例目的：

- 最终内容分别为 S0、W1，不能把 Surface 版本冒充 Workspace 版本或偷偷全域回退。
- 历史仍包含 op-1-confirmed，新增回退记录；external_counter 仍为 1。
- 读取或回放既有事实不再次执行 op-1，也不声称外部效果已被文件回退撤销。

动作序列：restore_domains → replay_history。完整初态和参数见 JSON。

精确预期：

- `G1-BND-014-E01`：`domain_versions` 等于 `{"Surface": "S0", "Workspace": "W1"}`。
- `G1-BND-014-E02`：`records.history.0` 等于 `"op1-confirmed"`。
- `G1-BND-014-E03`：`records.history.1` 等于 `{"kind": "rollback", "versions": {"Surface": "S0", "Workspace": "W1"}}`。
- `G1-BND-014-E04`：`external_effects.op1` 等于 `1`。
- `G1-BND-014-E05`：`observations.replay.side_effect_executions` 等于 `0`。

已知错误：把回退解释为整个系统回到过去，删除后续历史或重新执行回放动作。

失败原因：会掩盖已发生效果、错误重做副作用或恢复错误的两域组合。 必须至少违反 G1-BND-014-E02, G1-BND-014-E03 中一条相关断言。

前提：

- 外部计数是有限独立目标模型；本例没有授权或假定外部补偿。
- 两域组合已预先明确，未指定的组合不能被默认为等价。

现实缺口：

- 真实外部系统副作用查询、补偿及已保存模型结果恢复分别验证，不由文件模型通过推导。

## G1-BND-015：应用同名声明与成功文本不能伪造 Runtime 确认

性质：P08。来源：V5-A021, V5-A069, V5-A099, V5-A101, V5-A102, V5-B029, V5-B031。

原始用例目的：

- 同名应用声明可按应用声明保存或因保留命名规则拒绝，但不得形成 Runtime 确认事实或改登记表。
- stdout、blocks、事件名称和 success 字段都不能自动启动模型、登记对象或形成通用业务终态。
- 合法登记完成后才出现可关联真实登记的 Runtime 确认事实；消息受理不提前充当登记完成。

动作序列：submit_message → read_untrusted_content → read_untrusted_content → submit_message。完整初态和参数见 JSON。

精确预期：

- `G1-BND-015-E01`：`observations.app.record_kind` 等于 `"application"`。
- `G1-BND-015-E02`：`observations.app.registration_completed` 等于 `false`。
- `G1-BND-015-E03`：`observations.stdout.control_actions` 等于 `0`。
- `G1-BND-015-E04`：`observations.block.control_actions` 等于 `0`。
- `G1-BND-015-E05`：`observations.register.registration_completed` 等于 `true`。
- `G1-BND-015-E06`：`events.runtime.0.kind` 等于 `"registration-confirmed"`。
- `G1-BND-015-E07`：`events.runtime.0.source` 等于 `"runtime"`。
- `G1-BND-015-E08`：`counters.model_launches` 等于 `0`。

已知错误：只按事件名称或 success 字段分类为 Runtime 确认，或自动解析控制文本执行登记。

失败原因：应用可以伪造控制事实并绕过受控登记过程。 必须至少违反 G1-BND-015-E01, G1-BND-015-E02 中一条相关断言。

前提：

- surface.registered 仅沿用原文候选名称；测试针对来源权限和实际登记，不冻结命名方案。

现实缺口：

- 真实提交入口、事件来源认证、权威存储权限及登记完成边界需实际组件验证。

## G1-BND-016：修改或读取输入视图不改变权威事实和消费责任

性质：P08, P12。来源：V5-A069, V5-A076, V5-A088, V5-A091, V5-A092。

原始用例目的：

- 读取不是消费完成确认；读取、断连及重复通知不删除 step1:e1 待处理责任或 result0。
- 视图修改可以被只读权限拒绝；即使允许修改独立副本，也不改变 authoritative_event 或登记事实。
- 重新生成视图得到 original，待处理关联和已存结果与原始权威记录一致。

动作序列：read_input_view → mutate_private_view → discard_volatile → notify_existing_input → regenerate_input_view。完整初态和参数见 JSON。

精确预期：

- `G1-BND-016-E01`：`events.app.0` 等于 `{"id": "e1", "body": "original"}`。
- `G1-BND-016-E02`：`input_views.v1` 等于 `{"id": "e1", "body": "original"}`。
- `G1-BND-016-E03`：`records.pending` 等于 `["step1:e1"]`。
- `G1-BND-016-E04`：`records.saved.step0` 等于 `"result0"`。
- `G1-BND-016-E05`：`events.runtime` 等于 `[]`。

已知错误：把视图文件本身当权威事件仓库，或把读到 EOF 当推进已经确认完成。

失败原因：应用可篡改事实或读文件即丢失未完成责任。 必须至少违反 G1-BND-016-E01, G1-BND-016-E02 中一条相关断言。

前提：

- 允许模型中区分只读输入视图与可写私人副本，不要求用户界面必须提供可写视图。

现实缺口：

- 真实视图权限、权威存储隔离和交付确认事务边界仍需验证。

## G1-BND-017：登记路径移动、删除和重绑定不得继续使用失效关系

性质：P02, P04, P08。来源：V5-A106, V5-A107, V5-A108, V5-B011。

原始用例目的：

- 普通内容编辑不要求重登记，登记仍对应原对象与权限。
- 任何已失效路径或对象绑定均不得沿旧关系执行；拒绝、暂停或明确完成关系更新后再执行，不能回退宿主。
- 重绑定不隐式扩大资源权限；处理后合法的新目标能够执行。

动作序列：conditional_edit → execute → external_change → execute → external_change → execute → update_registration → execute。完整初态和参数见 JSON。

精确预期：

- `G1-BND-017-E01`：`observations.edited-valid.status` 等于 `"executed"`。
- `G1-BND-017-E02`：`observations.removed.status` 等于 `"rejected"`。
- `G1-BND-017-E03`：`observations.replaced.status` 等于 `"rejected"`。
- `G1-BND-017-E04`：`observations.updated-valid.status` 等于 `"executed"`。
- `G1-BND-017-E05`：`targets.TR.writes` 等于 `["S1"]`。
- `G1-BND-017-E06`：`bindings.TR` 等于 `"H1"`。
- `G1-BND-017-E07`：`counters.host_executions` 等于 `0`。

已知错误：永久缓存路径字符串到环境映射，目录内容变化或对象替换后仍沿旧授权执行。

失败原因：可能执行无权新对象或旧 Harness 绑定，路径存在不证明原登记仍有效。 必须至少违反 G1-BND-017-E02, G1-BND-017-E03 中一条相关断言。

前提：

- 移动、删除、对象替换与重绑定是独立有限分支，不要求全部在一条轨迹发生。
- 进行中的 Step 策略版本由下一例单独约束。
- 移动和删除在本有限对象模型中都映射为旧位置不再绑定原对象，故共享明确轨迹；真实文件系统实验须分别执行移动、删除和替换。update_registration 代表已获授权的登记关系处理，不因本测试动作赋予普通任务登记权。

现实缺口：

- 目录身份、路径替换竞争、登记关系持久更新及旧执行者处理需真实组件实验。

## G1-BND-018：已开始 Step 固定 Harness 的模型、模板及解析规则版本

性质：P01, P04, P07, P08, P12。来源：V5-B027, V5-B047, V5-A108, V5-A039。

原始用例目的：

- step1 的模型、模板和输出解析均保持 H0 对应版本，不能在中途混用 H1。
- H0 所需内容无法取得时应明确暂停／报告缺失，不能静默回退当前 H1 并仍声称继续原 Step。
- 新 step2 可按新绑定使用 H1；旧记录与新记录版本可区分。

动作序列：begin_step → external_change → step_phase → step_phase → discard_volatile → step_phase → begin_step → step_phase。完整初态和参数见 JSON。

精确预期：

- `G1-BND-018-E01`：`steps.step1.harness` 等于 `"H0"`。
- `G1-BND-018-E02`：`observations.model.value` 等于 `"M0"`。
- `G1-BND-018-E03`：`observations.template.value` 等于 `"T0"`。
- `G1-BND-018-E04`：`observations.parser.value` 等于 `"P0"`。
- `G1-BND-018-E05`：`steps.step2.harness` 等于 `"H1"`。
- `G1-BND-018-E06`：`observations.new-model.value` 等于 `"M1"`。

已知错误：每次调用都重新读取当前绑定的 latest，恢复时尤其替换为新解析器。

失败原因：同一步的语义会随文件或登记更新变化，已存模型结果可能按错误规则执行。 必须至少违反 G1-BND-018-E02, G1-BND-018-E03, G1-BND-018-E04 中一条相关断言。

附加独立轨迹：`missing-pinned-harness`；独立从本例 initial_state 开始，不继承主轨迹终态。 完整动作和预期见 JSON，不能跳过。

前提：

- H0/H1 表示可识别内容版本集合，不限定打包格式、语言、模型服务或 Git。
- 只禁止静默替换；显式停止旧 Step 再建立新推进需保持新的身份和记录。
- H0 内容缺失时的暂停反例在本 JSON 的 extra_trajectories 中单独预注册，不由成功路径推断已验证。

现实缺口：

- 真实 Harness 代码／模板依赖的版本捕获、模型适配与恢复引用需要组件验证。

## G1-BND-019：裁剪仅改变投影，原始日志完整且可按授权取回

性质：P12, P04。来源：V5-B056, V5-B057, V5-B060, V5-B061, V5-A114。

原始用例目的：

- 裁剪后权威日志仍精确等于 HEAD、MIDDLE-REQUIRED、TAIL，不能只保留摘要。
- 投影明确标注裁剪，完整获授权来源在对应环境可访问，读取返回 MIDDLE-REQUIRED。
- 当前目标、必要 block、本次输入及本用例继续所需信息不因裁剪失去可用依据。

动作序列：trim_projection → read_source → discard_volatile → read_source。完整初态和参数见 JSON。

精确预期：

- `G1-BND-019-E01`：`records.raw.log-v1` 等于 `["HEAD", "MIDDLE-REQUIRED", "TAIL"]`。
- `G1-BND-019-E02`：`observations.trim.truncated` 等于 `true`。
- `G1-BND-019-E03`：`observations.trim.source` 等于 `"log-v1"`。
- `G1-BND-019-E04`：`observations.read-middle.value` 等于 `["HEAD", "MIDDLE-REQUIRED", "TAIL"]`。
- `G1-BND-019-E05`：`observations.read-again.value` 等于 `["HEAD", "MIDDLE-REQUIRED", "TAIL"]`。
- `G1-BND-019-E06`：`observations.trim.required_context` 等于 `{"goal": "G", "block": "B", "input": "e1"}`。

已知错误：用摘要覆盖原始结果，或提供仅在另一个宿主可读／会变化的来源路径。

失败原因：摘要无法还原被删中间证据，引用存在也不能证明当前环境能取回完整版本。 必须至少违反 G1-BND-019-E01, G1-BND-019-E04, G1-BND-019-E05 中一条相关断言。

前提：

- 日志与必要信息均为固定有限 fixture；不比较摘要质量或冻结历史步数与长度阈值。

现实缺口：

- 真实 Session 原始记录保留、文件授权、长日志存储和实际模型检索能力需独立验证。

## G1-BND-020：裁剪与窗口推进不能删除未知结果的核对责任

性质：P04, P07, P08, P11, P12。来源：V5-B059, V5-B061, V5-B041, V5-A040。

原始用例目的：

- op1 的身份、未知结果与核对责任仍持久存在，不因窗口变动或恢复丢失。
- 核对之前不盲目重发；本 fixture 中查询确认既有效果后不再产生第二次效果，target_effect_count 保持 1。
- 若无法查询且无安全重试依据，则明确暂停；不能让模型忘记后把旧动作当新动作执行。

动作序列：trim_projection → discard_volatile → retry_operation → query_effect → retry_operation。完整初态和参数见 JSON。

精确预期：

- `G1-BND-020-E01`：`observations.before-query.status` 等于 `"blocked"`。
- `G1-BND-020-E02`：`records.saved.op1.state` 等于 `"confirmed"`。
- `G1-BND-020-E03`：`observations.query.effect_count` 等于 `1`。
- `G1-BND-020-E04`：`observations.after-query.status` 等于 `"already-completed"`。
- `G1-BND-020-E05`：`external_effects.op1` 等于 `1`。
- `G1-BND-020-E06`：`records.raw.log-v1` 等于 `["op1-unknown", "current"]`。

已知错误：按固定最近步数同时清理持久记录，或仅依赖模型上下文记住待核对操作。

失败原因：裁剪后旧效果被遗忘，引发重复副作用。 必须至少违反 G1-BND-020-E01, G1-BND-020-E04, G1-BND-020-E05 中一条相关断言。

前提：

- 外部目标计数和查询结果为独立 fixture；不是用调用次数替代真实效果。
- 未要求 Runtime 内置通用 done/fail 业务状态。

现实缺口：

- 真实未知结果查询、幂等能力和持久记录保留需后续组件与端到端故障实验；模型不证明恰好一次。

## G1-BND-021：投影路径、版本与普通内容执行边界保持明确

性质：P02, P08, P12。来源：V5-B026, V5-B050, V5-B051, V5-B053, V5-A110, V5-A112。

原始用例目的：

- 模型输入中 Surface 状态 S1 与 Workspace 状态 W7 分别标注，不互相冒充；所有必要输入可定位。
- 引用在声称的执行环境无法访问时明确报告缺失或权限问题，不能以宿主文件存在宣称可用。
- 读取普通内容不自动执行或形成控制请求；经 Harness 约定识别且目标脚本无歧义的合法请求才进入授权执行。

动作序列：project_context → read_source → read_source → read_untrusted_content → execute。完整初态和参数见 JSON。

精确预期：

- `G1-BND-021-E01`：`observations.context.domain_versions` 等于 `{"Surface": "S1", "Workspace": "W7"}`。
- `G1-BND-021-E02`：`observations.context.status` 等于 `"complete"`。
- `G1-BND-021-E03`：`observations.wrong-env.status` 等于 `"denied"`。
- `G1-BND-021-E04`：`observations.right-env.value` 等于 `"REPORT1"`。
- `G1-BND-021-E05`：`observations.block.control_actions` 等于 `0`。
- `G1-BND-021-E06`：`objects.control.value` 等于 `"C0"`。
- `G1-BND-021-E07`：`observations.valid.status` 等于 `"executed"`。

已知错误：把 Surface HEAD 显示成项目版本；或扫描任意 block 中的代码块／控制词自动执行。

失败原因：上下文事实来源混淆且普通内容被升级为控制权限。 必须至少违反 G1-BND-021-E05, G1-BND-021-E06 中一条相关断言。

前提：

- Harness 可以自行选择合法交互格式；本例区分读取的普通内容与按所选协议识别的完整请求，不禁止 Bash 代码块作为正式适配。

现实缺口：

- 实际模型输入捕获、真实目录可访问性、输出完整性识别和执行器授权需在后续阶段分别验证。
