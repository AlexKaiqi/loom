# 实时独立 S collector 接口 v1（G3草案）

入口为 runner.py --driver validation/components/s/collector.py --run-dir <new>，collector 接 --plan/--output；可用 --target 或 LORE_S_TARGET 指定可信目标配置。默认 target.json 不存在，当前实际执行必须 MISSING/退出2，无 bundle、无组件PASS。collector.py 创建真实文件与动作，collector_actions.py 解释先行操作词，live_ports.py 只管受限字节/原始引用/真实Engine观察。无 case ID 控制分支；S仅获正常调用与合法fixture引用，不获期望/assertion。

target.json 来自受信配置（例子 target.example.json 故意空且不能运行）：sut_argv 是已经挂进Session执行profile的真实Node/Pi适配入口；x_command/f_command 为独立测试包装命令，其组件必须有内容摘要绑定的 G4 E gate。每个gate明确component X/F、stage G4、PASS；不能拿G2或准备PASS替代。fixture_authority 是外部给予的有限测试身份；不从模型JSON导出。artifact_roots 是可信外部已保存输出的明确根，不能为/、/home、/home/alex；原引用在读取前核实际path/size/hash和根范围，S不能诱导读取任意宿主文件。

JSON peer命令每次stdin收 {protocol:LORE_COMPONENT_TEST/1,fixture_root,method,params}，stdout给 {result:...} 或 {status:MISSING}。fixture_root将每个案例的真实R/F/X测试状态隔开，adapter不把它传给候选。stderr/非零/缺字段/非法消息不会当成功。peer侧的fixture包装不等于新产品API，不得返回生成的checks或预期；当前实际组件/包装均未存在，缺依赖必须报MISSING。

X低层方法采用已协调合同：execute(request,authority,io_mode=duplex)→execution_binding+channel_binding。execute先固定原exec身份后启动；channel_write/read/close_stdin为可信测试层的base64字节封装。read含stdout/stderr分片及EOF，每流/总量仍服从实际X限制；普通任务仅有自己的stdio，无控制fd。checkpoint/resume/seal/release关联原execution/generation与receipt；准备archive由可信RO exporter生成，collector另读真实archive、抽取恰一原PiJSONL并用独立reader解析。callbacks出现时先checkpoint原意图，恢复同一对象后才交付provider/tool；初始/最终/失回执边界原记录全部保存。暂停不等于失权。执行器测试包装还需 test_fault_input（仅毁损本次待恢复副本）及test_cleanup（按完整真实ID清理），不能改已确认原件。

S最小帧：请求 lore.s/1 + action accept/query/drive/export_read + session_ref/operation_id/harness_ref/input_ref/source_result_ref/capability_ref；export_read另有read_ref。S发provider.request必须含session_id/operation_id/effect_id/response_entry_id/payload；tool.request含同一身份、invocation_id/source_result_ref/request.target/script。collector核原Session effect_pending中的真实reserved ID；回复provider.reply/tool.reply只沿该ID。effect.query/provider.query按原effect身份查询，真实outage可明确注入无法取得回执，不能启动新effect。result帧带operation_id/boundary_kind/原结果ref/可选decision_proposal/error；原框架记录与物理效果不从这些字段推导。

R在本S组件测试中不实现。固定provider fixture真正生成的完整wire字节及原responseEntryId单独持久存入test receipts；它只是R运输回执输入替身，不是语义模型历史或R调度证明。S-017只验S保存/释放/原查询，R11/R12与G5接缝另担已接受决定A；S普通final无继续提议从实际帧观察，不能靠空假R队列。

F测试包装只把collector建立的真实普通文件映射到已验F方法，不从expected编造数据：
- prepare_fixture_input：真实surface/workspace/input/originals目录及版本/profile→F不可变输入、Harness与外部fixture授权ref。M路径映射为/input/surface、/workspace等实际环境位置；同时传具体用途和版本，不泄漏宿主控制根。
- prepare_alternate_fixture_binding：从实际存在、仍获授权的另一个版本/关联返回完整ref，用于同ID单字段冲突；不得只返回“changed-only”畸形值。
- prepare_fixture_limit_binding：在明确fixture权限/profile中绑定更小max_steps，不能实现Runtime调度。
- fixture_full_output_reference/resolve_fixture_original/resolve_fixture_output：返回原不可变文件及可访问字节引用，成功要有path/bytes/sha；普通可变路径不能冒充版本。
- read_fixture_effects：从真实X结果及实际产物读数据，不能使用X自报success制造effect。返回新增本次真实effect记录，不能重复累计前次效果。
- test_corrupt_fixture_read：只改选定读取副本一个字节而保持长度，原Git/归档完整来源保留。真实resolve_reference必须报告完整性错误，不能通过此包装绕过F校验。

F正式ref字段沿对方合同：resource_id/domain/git_ref/archive_sha256/manifest_sha256/profile；内容增加path、kind、sha256与当前授权。collector只读取实际输出，不创造CONFIRMED F ref。wrapper尚未接实际F/X时D02运行呈MISSING；接口现在先行可执行并可独立审，不能到G4按实现改变预期。物理来源仍须独立审查测试adapter源码及受限mount；origin字符串仅作索引，不认证来源。

当前driver还没有被真实S/X/F全路径运行；所需字段/包装方法必须随三方合同独立冻结。准备只执行missing入口和byte/oracle负控，不用伪peer全绿伪装真实main路径。正式S实施前，S驱动入口和已验设施接线仍是明确门槛。

## 独立预审修复003的明确接口

S-026 的原接受完整binding存放于原Pi非pi命名空间值 `lore.s.binding[operation_id]`，至少含 session_id/operation_id/harness_ref/input_ref/source_result_ref/capability_ref 原内容。观察器从实际原JSONL解析后逐字段核对，而非接受S自报binding。Pi provisional result帧到达不等于外部durable admission ACK；观察器完成checkpoint并fsync外部恢复描述后，在交付ACK前真正截断/停止。新调用从该磁盘描述与原archive恢复，不能沿内存accepted Map猜测。S026仍是R接收方运输夹具，真实R失ACK责任接缝由G5验证。

X薄测试包装增加 resolve_result_stdout(original_result_ref,authority)：只解析该原执行不可变stdout引用，返回当前artifact_roots内path/bytes/sha256；不新执行、不从期望生成stdout。tool.reply携带原result_ref和相同stdout的 {data_b64,bytes,sha256}，经原Pi native toolResult保存。S018 bootstrap真实普通工具只向stdout输出 `ORIGINAL_TOOL_RESULT_雪\n`，观察器另存实际原stdout并在下一operation原toolResult角色核对。

S025保留累计accepted_finals=1，仅新增recovery_finals计坏Session恢复区间final=0；不清空先前事实。OS观察由physical_witness.py在每次S运行开始核实际Engine exec完整argv/container/PID+generation，并分别以固定UID0/1000只读观察实际原namespace；seal/release后重新枚举同namespace。container/volume inventory另入remaining_execution_objects，不与PID混称。

G4 S资源采用 design/g3/system/contract.md 的单slot S512MiB+工具128MiB+共享串行helper128MiB，最多3个活动容器/768MiB，所有keeper计PID。此值为共同先行预约，不取自准备probe统计，不改独立X测试2/256预算。target配置必须给resource_contract及其sha256；resource_reservation包含max_objects=3、memory_bytes=805306368、session_memory_bytes=536870912、tool_memory_bytes=134217728、helper_memory_bytes=134217728。S的export、工具export和本observer helper串行占预留helper，不能另开第4个slot内对象；开始观察只在S初始callback前，停止观察在S所有调用已seal之后。每份正式profile还须绑定系统合同的/tmp/shm/volume/inode/CPU/输出/时长上限。

最终保存/停止必须维持同一冻结代：中间provider/tool checkpoint明确resume=True；accept/final和fault-stop checkpoint为resume=False，保持整个namespace冻结直到seal。不得先resume再拿旧冻结receipt声明保存后的实际停止；对中间callback后的故障停止先重新checkpoint并保持冻结。

## 上下文补件004的有限接线

prepare_fixture_input在originals存在log时，除原三ref还返回original_refs.log（真实F完整不可变内容引用），并在input_ref的获授权原来源元数据中提供相同ref、owner=F、read_path=/input/originals/log、实际hash/bytes。包装只提供实际原来源元数据，不计算首尾片段或裁剪结果；由外部Harness读取并投影，可信provider观察器核实际context。完整log在普通Runtime读域可达。

context_fixtures.py只生成有限普通文件和固定provider的普通Python脚本，不是Runtime/Harness实现。lazy-materials真实建立64×8文件和4096行diff；脚本glob查找请求的文件并read/hash文件和diff，stdout包含原片段与完整input_ref/path/bytes/sha256。input_ref来自该次已验F/X调用绑定，作为普通Python字面参数传入，不从assertions生成。collector把实际stdout存bytes:retrieval_stdout，另严格解析为journal:retrieval_output；原Pi及下一provider的native_tool_text须包含完整同一stdout。next_from_saved_result仅让测试接收方用实际已存operation_result_ref创建新operation，不模拟Runtime正式调度责任。

独立reader对实际provider payload读取完整JSON文本context块中的clipped对象（不接受S独立self-report），同原source比hash/bytes/ref并核精确range/fragments。native_tool_text只拼接tool/toolResult角色的文本块；普通user提示或旧toolCall脚本同字样不能满足。payload_bytes为实际捕获payload按UTF8规范JSON编码的长度，32768阈值仅是这个有限默认Harness投影样本，不是所有策略通用上限。
