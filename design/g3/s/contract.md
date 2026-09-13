# S：原 Pi Session 与外部 Harness 契约 v0.1

状态：DRAFT_FOR_INDEPENDENT_G3_REVIEW。G2 已通过；本文件不批准 G4，不声明任何运行时性质通过。职责和有限 M 配置拟定；公开钩子/容器交接仍以准备探针和独立审查裁定。

## 1. 责任与依赖

S 复用固定 Pi commit 71dca871bc80b6bc97be37f0ca3189399d651fff（agent-core 0.85.1）的原 JSONL Session、模型记录、工具调用、Lane.accept/drive/getResult/restoreSession。外部 Harness 用普通代码决定投影、交互解析、工具定义与继续提议。S 薄适配仅补完整身份关联、可查询持久确认、受控管道和版本绑定；不另写模型—工具 loop，不以 Runtime 表重建竞争的 Session 真相。

R 持有登记、授权、输入边界、稳定请求/决定、未结清交付责任；X 提供真实受限执行、原工具结果、实际停止与有界冻结导出；F 提供普通目录版本和内容引用；E 提供固定事件视图。S 返回原 Session 引用和外部策略提议，Pi operation completed 不能自动成为整个任务完成。R 不根据 Shell 成功、event 名称或候选返回的 success 自生继续策略。

采用 Python 控制端 → Node/Pi 短命进程的严格 JSON 管道，属于内部接口；模型仍使用 native tool 调用和普通 Shell/Python。Node/Pi 与 Harness 均在 X 受限容器，禁止候选代码导入可信 Python 宿主。只允许当前 Session 私有工作副本及明确只读输入、Harness 与固定依赖，不挂凭据、控制数据库、任意宿主目录、Docker socket。网络默认无；provider 请求和工具委托由可信 bridge 按当前身份、目标、预算逐项验证。Session 可写区有容量/inode/输出限制；不得拥有宿主权威 Session 的无限写入能力。

## 2. 引用、完整关联和调用

输入建议为 {protocol:"lore.s/1", action, session_ref, operation_id, harness_ref, input_ref, source_result_ref, capability_ref}；action 仅 accept/query/drive/export_read。实际 driver 控制帧与 provider/tool 子调用分别有类型和父调用身份，长度有界、单 JSON 帧完整解码；stdout 的任意文本不构成请求或回执，stderr 不可变控制消息。未知字段/类型、越权 ref 或错误代次在无 effect 前拒绝。具体字段与 R/X 总接口冻结前合并。

session_ref 指明 owner=S、Session 稳定 ID、原 Pi 格式/固定源码版本及已确认原始 snapshot 引用；input_ref 是固定本轮输入 manifest，含 Surface 版本、事件来源/范围/完整可读时点、前序 Session/X 反馈、两个真实工作位置与用途、获准 targets 和限制。harness_ref 绑定代码、模板渲染、解析规则、模型标识/协议及配置内容摘要；已开始推进不得静默换版。引用解析到本次环境的真实可读位置，拒绝仅存在于旧容器的不可达路径。source_result_ref 可为首步 null，其余为准确旧 Session 结果/工具结果关联。

完整 binding=(session ID, operation ID, Harness 内容版本, input 内容版本, source result, capability/targets 与模型/解析配置版本)。同 ID 同 binding 重交返回原受理/结果；只改变任一字段必须 conflict，原关联及结果不变。缺失 binding 不得靠 prompt 相同猜测。Pi 本身完成后同 ID 允许重新 accept，因此适配必须在调用 accept 前检查原 Session 内的非 pi 命名空间绑定；禁止覆盖原 pi.* 历史。公开 Session.mutate 可扩展值的可行性和绑定-only 崩溃间隙仍需 G4 验证；R 可保留绑定和原引用，但不能复制语义历史来规避原 Session 缺口。

accept 必须不启动模型/工具；仅准备字节不等于受理。query/export_read 必须不调用模型、工具、业务钩子或再次 accept；只读指定原身份和版本。drive 必须有已确认接受的完整关联；完成态返回原结果，不再 drive。并发写需 R/X 对该 Session 实际唯一写者/代次，单进程 Map 或租约自述不是跨进程排他证据。

回复返回 original_session_snapshot_ref、operation_result_ref、assistant_entry_ref、tool_result_refs 及 boundary_kind（accepted、tool_feedback_saved、answer_saved、paused_unknown、paused_reconciliation_required、blocked_invalid、stopped_limit）；缺少原结果时不得返回伪造引用。decision_proposal 来自固定 Harness，带 source result/版本/稳定决定 ID 与内容；仅 R 受理后构成交付责任。普通非恒定代码不能在 R 已接受 A 后重算为 B。S 不承担 R 的持久等待/下一步启动职责。

## 3. 实际可用公开入口与限制

| 入口 | 已查事实 | 本合同用法/待验证 |
|---|---|---|
| JsonlSessionRepo、createAgentHarness、Lane.accept/drive/getResult | 固定源码及 G2 新进程实际运行 | 原 Session 唯一语义记录；JSONL append 未提供 fsync，持久 ACK 需可信导出持久屏障 |
| custom model provider / models.setProvider | 固定 faux 入口实际执行，generation.ts132–171 先写 assistant.effect_pending 含 responseEntryId，再 streamSimple | 容器内 callback 经管道请求可信 provider；需增量协议映射准备，不把 faux 当真实模型 |
| transform_context / entryProjectors / toProviderMessages | 源码公开投影入口 | 模板/blocks、事件与前序结果由外部代码组装；真实模型所收 payload 由可信 provider collector 核验 |
| before_tool + delegated tool.execute | tools.ts436–504 先校验，再写工具 effect_pending，后执行 | 从已保存 assistant entry 检查完整性/批量数；只允许一个合法 native tool 请求，并发/异常不越过 bridge |
| after_tool terminate:true | G2 step-001 与 step-independent-001 保存一个 tool 后停止，0 额外 provider | 限单 tool/no inbox/no followUp；多 tool batch 不是每 tool 截断，不能推广 |
| after_response | response.ts85–94 在正式 assistant entry publish 前调用，允许改 message | 不能拿它证明完整结果已存；参考 Harness 不在此解释/改写动作或 final。实际 tool 前/最终 result 后读原完整 entry |
| before_run_end | 公开 followUp 钩子 | M 禁止内部 followUp，外部继续经 R 新 operation；以后策略需另定容量/释放边界 |

M 参考 Harness 是有限单步配置：一个固定输入、最多一个完整模型响应、最多一个 native tool 调用、无 inbox/steering/followUp/自动 compaction/隐式 provider retry；关停这些能力的实际配置须验证，不靠文档断言。预算限制停止须保留已有结果与原因，不能写成成功。普通最终回答没有 tool 且 stop/完整性/格式符合固定 Harness，保存后不再登记下一 Step。多工具、未完成 native tool、length/error/aborted/未知 stop、格式错误均不得 final；即使 Pi 返回 completed 也无例外。多工具应在任何 X effect 前拒绝并可释放；用完整原 assistant entry + before_tool 阻断全 batch 的可行性是准备探针目标，不要求修改 Pi 源码。

## 4. 原 Session 的持久交接与恢复

X 的私有有界写区是活跃副本。可信 Python 收到 framed provider/tool intent 后，请 X 暂停整个 namespace，导出同一 exec/generation 的原 Session 文件 manifest 与精确字节；核验及外部持久化后再恢复并交付调用。pause 不是失权；旧进程尚存不得接管。保存工具/assistant/result 后同样导出原字节，最终 seal 必须导出确认、实际 kill/退出、无剩余进程后才能宣告任务资源已释放。F 的受控发布与 R 的引用 ACK 不假定跨组件原子事务。

关键切点：绑定-only；accept 已写但外部 ACK 丢；assistant.effect_pending 已保存但 provider 未提交；provider 已完成但 Pi 未保存；assistant entry 已保存但工具未提交；工具外部效果已发生但回执/原结果未存；工具结果已保存但新决定未登记；结果导出后但进程尚未停止。每条保留旧 ID 与未决责任，先按原身份查询，不默认失败，不新推理替代旧结果，不重复未知副作用。

provider 接收完整回复至 Pi 保存之间，需要可信桥的同 request ID 未决传输回执缓存（原 wire bytes/摘要/完整结束、原 responseEntryId，范围限交付责任，不建第二模型语义历史），或具有等价查询能力。已收可信完整回复必须能原样交还同 Pi 操作；无该能力时明确暂停并把自动接续缺口保留，不能宣称无损恢复。R 已接受此窄缓存职责。固定源码 recovery.ts43–83 对孤立 assistant.effect_pending 从原 frames 合成 interrupted/error，未调用 provider，暂无公开接口消费缓存到原 pending。故当前已取得完整 wire receipt 的未保存窗口必须保留缓存/原 ID 并标为 paused_reconciliation_required（回复内容可核对，原 Pi pending 不能经公开 API 确认为成功），不宣称缓存可自动导入原 Session；若将来要求自动闭合，先论证公开能力再改独立契约。该限制绝不适用于已保存 Pi 结果：它们仍须原查询、零新调用。缓存不能让 R 编造 assistant entry；正式结果仍以 Pi 原记录为准。

工具 delegate 的 invocationId/operation/turn/source 稳定关联 X execution ID，未知结果须查询 X 原记录或暂停。replay 标签不能被模型/外部文本任意改成 safe。Pi 的“interrupted unsafe tool”文字不是实际 X 结果，不能因此继续调用模型。已确认的 step 在新容器恢复原 Session 字节后查询精确旧 entry/result，provider/tool 次数均不增加，再通过 R 已受理的新 operation 接续；不靠重新生成相同文本。

## 5. 投影、普通目录与裁剪

M 必须实际读模板、选定 block files、固定事件视图、原 Session/X 反馈；provider 的真实收到输入应含目标、必要笔记、对应事件来源及结果内容/可达引用。Surface 版本与 Workspace 版本/位置分开，两个工作位置和同一通用工具的 target/script 用法清楚。文本 code fence 或控制字样只是内容，不自动执行。普通文件变更在下一次明确投影体现，本次 input manifest 不随新事件/文件漂移。

裁剪只影响模型视图。提供 clipped=true、被裁剪范围/摘要或片段、原 owner/ref/版本/字节数/hash 与当前获授权取完整内容的方法；完整取回后必须按原字节/hash 比较，同长度替换也失败。原始结果、未知执行身份/核对责任与恢复依据不得删除。不能用截断的 assistant 文本充当最终答案。必要历史不是固定最近 1—3 步，选择由 Harness 外部规则决定。授权范围外、保留期失效、缺失/损坏明确报告，不能退回摘要当完整成功。

M 的合法两域工具、报告 sum=10、notes 与事件往返由 S+R/E/X/F+V 的组合案例验收；S 组件不独立自批全系统闭环。后续多 Surface 等待、策略 A/B/影子隔离及真实负载仍属 X 里程碑，S 必须提供版本可替换/可追溯的公开输入输出，不把单工具 M 变成整任务终点。

## 6. 验收与未决

见 cases.json、provider-preparation.md 及 validation/components/s/README.md。正式运行只接受真实 Pi/Node、受限环境、可信外部采集的原文件/调用/效果/OS 证据。faux 是模型机制夹具，不能认证 provider 兼容或真实模型价值。独立 oracle 不采信 S 自报 PASS/completed，缺证据/缺 case/零执行为 INVALID，不算负控 killed。验证器自测与 G3 环境探针独立批次，只证明验收准备。

准备探针已观察到固定容器加载、Session 公共 binding 存取、关停 retry/compaction 的当前配置、双工具整批阻断且无第二 provider、原保存结果零调用查询。仍未证明：完整绑定/跨代幂等；受限 writer 的可靠 checkpoint/发布屏障；全部队列拒绝的受控接口；真实 provider 协议和限权桥；真实 X 委托与各故障切点。provider 回执到原 pending 无公开自动成功恢复能力，按上文保留有依据暂停。均先行定义用例；任何无法用公开接口达成的阻断应修正边界并重新独立冻结，不能 G4 偷改 oracle 或 fork 上游掩盖。

准备与差异记录见 preparation-findings.md；X 的 keeper/RO exporter 生命周期设计尚属待验合同，直接 worker 退出不能作为持久卷存活依据。

## 预审修复003的准备限定

独立审查S-R01—04见 design/g3/reviews/s-pre-review.md，旧输入完整保存 history/pre-review-003。新增S026独立切点为原accept+完整binding外部持久后、外部admission ACK交付前丢失；先从原JSONL的lore.s.binding读取完整关联，再重建实际环境并同ID重交，不能把正常S003或model/tool失ACK拼接代替。初始原Pi受理结果帧仅是等待外部barrier的provisional结果。

正式S单slot预算明确引用design/g3/system/contract.md的3对象/768MiB（S512/tool128/helper128），helper串行共用；原probe上限只约束旧探针。S025恢复新增final与前序已确认final分开保留；S018必须真实工具stdout进入原toolResult，不能由fixture造返回；S009/17/26独立观察实际原PID namespace并另查对象inventory。修复后的driver仍等待真实S/X/F组件，缺target/gate非零，不能自批G3/G4。

最终accept/结果/fault-stop导出后保持冻结到seal；只有中间provider/tool意图屏障明确resume同对象。旧冻结receipt在已resume后不能作为新的最终保存证明。

## 上下文补件004：默认外部Harness的按需检索与有用裁剪

来源 v5 §6.4 / V5-B060：不预先展开全量目录树、所有文件和长篇 diff；先给模型正确路径和执行位置，允许在获授权环境使用普通工具主动检索。这是外部 Harness 的默认投影策略，Runtime 只提供授权的普通文件、路径、原版本和执行能力，不得硬编码忽略目录或禁止检索。

S027以64目录×8普通文件和4096行diff固定有限输入：首provider保留目标、笔记、事件、反馈与/workspace，用32KiB规范JSON payload上限及未选树名/文件内容/diff内容canary明确不全展开。第一步固定provider只请求一个普通workspace Python脚本，实际glob/read/hash读取所需片段；完整文件和diff仍以原input_ref+相对路径+字节数+sha256可定位。原X stdout须完整进入原Pi native toolResult，下一operation从它取得反馈；F不能直接把预期片段塞进provider输入。必要旧反馈在此为真实普通输入文件夹具，不冒充另一执行已确认结果；实际跨S/X结果还由S018及G5验证。

S020有限默认Harness选定原log首78字节和末44字节，原source共73850字节，区间为[0,78)、[73806,73850)。目标模型视图中有意义首尾片段和对应精确范围都必须实际出现。为使该参考策略可独立核对，使用一个普通JSON文本context块，字段clipped、owner、read_path、source_ref、source_sha256、source_bytes、retained_ranges、fragments；source_ref是真实F原引用，读取路径/input/originals/log，原F实体/hash/完整召回另核。不要求其他Harness使用此格式或固定首尾算法。UNKNOWN_EXEC17仍只表示S投影保留该输入，不能证明Runtime未决责任或真实effect未重发；相关M05/G5必须联合验证。

先行协议context-supplement-004.json；旧26例/109断言及全部当前源保存在history/before-retrieval-004。新增驱动与oracle均只是G3准备，真实S/X/F缺失保持MISSING。
