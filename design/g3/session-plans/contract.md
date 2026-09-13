# 可信 SessionPlans（NoEngine 先行契约）

仅产品化现 ExecutionPlans.session；不执行 X/Node/NATS、工具、调度或策略。依赖已验 R/F/S owner 与 X NodeProfile；原 session/tool/system 标准不改。Runtime 调用前实际 await E.lookup_input/prepare_input 核原 NATS；本模块再读 R 原绑定与 E 四文件/manifest，不选新 H。

API：`SessionPlans(control, files, snapshots, host, resolve_reference, register)`；`prepare(principal, invocation_id, *, execution_id)` 返回 `node_request`（权威 lore.s/1 原 accept 帧）及 `request/authority/node_config/original_request/input_view/snapshot_bundle`。`session(node_request, *, execution_id)` 使用固定 host.principal 与原 operation_id 找 R invocation，逐字段比较完整原 Node binding，仅允许 accept/query/drive/export_read；export_read 的 read_ref 必须在原 capability 授权的 original_refs 中并经 resolver 核验。调用者不能另给 snapshot/scope/target/path 替代原 R 来源。

host 是可信构造参数，固定 principal/namespace/plan_root/event_input_root/state_root、X trusted_config_ref/profile_ref/request_template_ref、deps_mount/slot_ref/authority_root、F authorization/model。完整配置均保留既有格式；X config 和 profile 的实际 SHA 被读验。register 只采用原 X immutable-full-ref-registration/v1 的 kind/fullref/scope，写往已配置 authority root；不是新 catalogue。NodeModel keyless，固定四 RO 角色和 Node --config 原入口，原预算不变。

resolve_reference(full_ref,purpose,expected) 是现 owner 解析接缝，expected 含原 R invocation、原 selector/registration，不从待验 ref 自取期望。F descriptor 返回原 raw bytes；F-view 返回实际原 bundle/materialized；S session 返回原 scope 与 confirmation_request_id（初始为None）；source-result/original-file 返回原 raw bytes。每个返回仍核 fullref/范围及实际 F Git/read 或 S.query。它们仅是原件的 Python 投影，不落新索引。R payload.session_ref/Harness/capability 的本体保持已接受完整原ref；Node compact {id,sha256}由原 F descriptor/ref和原bytes计算，不替代 R E.input_ref。capability 可保留原授权 original_refs（源full F file_ref/read_path），不接受 Node 增添。

执行目标来自原 selector.execution_targets（含resource_id与version_ref），逐项 R.resolve 检查当前实际根、kind/namespace/授权；Surface必须是原 invocation资源及selector.surface_ref对应完整F版本，Workspace独立。源 F bundle/materialization真实读取；不依赖 fixture index/Peer.allow。复制完整 Surface 与原 E files/feedback/originals 成普通派生 input，加入唯一 node-config.json 后真实 F.capture/materialize，原件来源记入实际 capture coordination/provenance；路径冲突明确拒绝，不重写原档案。当前 H/cap refs只取本次 R payload。

S初态只由 SnapshotStore.empty 创建；已有 source 必须 S.query 原健康 confirmation，完整 scope/owner/archive/charge核合，隔离坏 Session或任意自报snapshot拒。scope 来源原R session_ref的trusted resolver；与原 Surface/namespace/Session引用交叉核。稳定 execution_id来自可信 Runtime原调用，生成路径/捕获/注册身份从原输入确定；同调用不随机换原件或重复capture新版本。计划文件若保留仅含原 F/X 引用的可重建传输投影，不成为决定/执行账本。

固定五组：SP01 真实 R受理/E文件publish+bind/F完整源/S初态 → 实际 NodeProfile.prepare/role_slot 合法，配置内容与原完整树独立比较；SP02 未绑定E、错principal/namespace、stale registration和越权targets拒；SP03 原F引用/字节/目录被替换或Host profile/预算篡改拒，真实合法来源正控先存在；SP04 健康原owner恢复正控、错Session/任意snapshot/坏原件拒；SP05 同调用稳定、四Node action合法，改任一完整binding/read_ref拒，node_request不能选新ref或scope。

入口 `research/.venvs/runtime-research/bin/python -B validation/session_plans_probe.py --batch NAME`。仅使用已装nats-py以导入E原文件模块，不连接NATS；E空范围实际packet/publish/validate是文件边界夹具，不宣称新NATS范围验证。正例实际F Git/原文件与X真实validator，无Engine。先MISSING/exit2/0；坏实现/省略原字段必须明确FAIL；复制源与原F树、旧失败保留。作者不授予独立或系统通过。

既有 export_read 薄口：`resolve_read(original_full_F_ref, node_descriptor)` 仅在本对象已核 `.session` 后可用；只保存重查用 invocation/execution ID，每次从原 R/E/capability/F 重新解析。按原授权 original_refs 与实际派生 F input 映射 `/input/...`，核 Node descriptor 的原 bytes/hash/path，再返回实际 host path/bytes/sha256；不打开 Node 自报宿主路径、不增 catalogue。SP05包含真实原F读正例和错路径/hash拒绝。

同 op 修订先行：SP05用同一原 invocation 的第二个可信 X execution ID 验原 Node compact input/h/cap/source/session 绑定保持；派生配置路径可变，原输入 descriptor 必须仅按 invocation 固定。已通过 author-001 未覆盖此跨执行ID反例，保留为有限范围。R本步 accept→drive owner 来源缺口与该稳定绑定缺口分别保留，不计完整接续已验。

本步 owner 来源修订：R设施ID= `s-exec-`+sha(canonical([parent invocation,accept/drive]))，kind execution，payload精确 parent_id/action/execution_id/node_request；正常确认ID=`s-`+sha(canonical([execution_id,s-service-final]))。drive只从本步accept confirmed原R设施及实际S确认选源；query/export_read已有drive时必须选该已确认原件，issued/unknown不退回accept。R已有receipt checker必须重验原facility_ref，S query完整结果和原checkpoint EXEC元组与原released/stopped响应binding均核合。resolver(session-source)只返回facility_id/confirmation_request_id；不提供新快照原件。Node.session_ref须是所选正常session_reference envelope，其他原binding保持不变。SP04以明确X-shaped NoEngine文件fixture、真实R SQLite与S确认/查询验证选源、旧owner拒绝，不声明物理Node/Engine接续；真实链交根M01。

Runtime context 小增量：按 ../s/runtime-policy-contract.md，在原 SP01/所有verify路径先检查config.runtime_context精确集合及原R五字段语义、真实S完整node_binding、原selector/E原manifest.range（含未改next_sequence）、本次execution_id和预分配同父drive的confirmation locator。locator只是逻辑地址，不能授权或跳过S query；accept/query等配置也指同父drive终态。先保存原候选缺字段失败再实现，既有5组数目/其余预期不改。

Context 互操作更正：context-author-001只验证Python自拟映射，未发现context.execution_id用了当次accept而locator指drive的不一致。原真实Runtime.create/decideControl互操作在context-interop-before-fix-001拒绝该配置；修订后context.execution_id恒为同父drive ID（实际X request.execution_id保持各action原ID）。将实际Runtime模块+minimal委托纳原SP01验证入口；Pi后端仅inert fixture，不调用模型/Engine。facility_ref显式保留confirmation_request_id并核等于既有确定ID。原失败与旧通过范围保留。
