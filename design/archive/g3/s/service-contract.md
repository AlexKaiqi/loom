# 生产 Session 服务的有限胶水契约

API：`SessionService(execution, snapshots, provider, plans, tools, checkpoint=None).invoke(request, *, execution_id, deadline_monotonic)`。同步可信宿主接口；`request` 原 `lore.s/1` accept/query/drive/export_read。只新增 service/transport，不修改 Pi、SessionRun、ProviderBridge 或已验 resolver；不存第二历史、不调用第二次策略。外部 Harness 的原 result/decision 帧逐字段保留，Runtime 之后按原 source 受理。

`plans.session(request, execution_id=...)` 是可信宿主 resolver，至少给出原 X `request/authority`；X 请求的 schema2/session_binding/execution_id/source_result 必须与原请求一致，所有真实 F/S refs、权限、入口和预算由 resolver 固定。Node 帧不能替换 plan/authority。单步最多一个 provider 和一个工具请求；query/accept/export_read 不交付新副作用。后续非 M 策略若需不同预算须复用 capability 中明确的配置，当前不隐式放开。

provider 使用现 `ProviderBridge.complete(original_scope, frame)` / `query(effect_id, original_scope)`；original_scope 来自已确认原 binding 与原 pending responseEntryId。仅新鲜、完整且 accepted 的原 wire normalized Message 可以回同次 pending；fresh=false 或 UNKNOWN 保留回执并报 `paused_reconciliation_required` / `paused_unknown`，不得再发或注入已失去实时调用的 pending。

工具注入口：`tools.execute(binding, frame, original_session_snapshot_ref)` → `{status:'RECEIVED', fresh:true, result_ref, stdout_ref}`；`tools.query(effect_id,binding)` 只查原 X/发布回执。executor 是可信现成 X/F/R resolver 的窄接口，负责 target/script 授权、原 effect ID 的 execute/query 与实际发布；服务核原 pi.op.state、batch/resultEntryId、原 assistant native call 和已保存 pi.op.tool_args 后才调用。stdout_ref 必须是可读完整文件 path/bytes/sha256；读取/hash 后原 bytes→tool.reply。不把 fixture fake authority 或 result Map 移入生产。

每次请求回调先 X checkpoint→S.confirm→query 原副本，核完整 binding/原 pending/稳定 effect ID；之后调用 `checkpoint(label,facts)` 切点、resume 同原对象再交付。facts 保留原 execution、confirmation request ID、full snapshot 与 callback；effect 返回亦给切点。最终结果保存后核 resolver 的原 locator/boundary，保持 frozen→seal→release；healthy 和 quarantine 分开。返回 `{frame, confirmation_request_id, original_session_snapshot_ref, checkpoint_ref, stopped, released}`，frame 不变。无有效 binding/坏 Session 只能 quarantine；失败 accept 不确认 admission，不造 empty。异常抛 `SessionServiceError(code,evidence)`，保留现存原引用及清理结果；清理失败显式记录，不声称已释放。

严格 UTF8 单 JSON 行、重复键/未知回调/完整关联不符拒绝；1MiB 单帧和 stderr 上限、64KiB 每次读取、原 call ID 与 offset 贯穿，不自动重写未确认 write。原 reader EOF 或 deadline 无帧属 transport unknown，不能伪造 Node 最终结果。`query` 不重新运行业务钩子或执行工具；Node 原 pending query 只映射到真实 owner 的只读 query。

先行入口：`python3 -B validation/session_service/run.py --batch NAME`，固定 21 项；缺 candidate 明确 MISSING/0。fixture 复用真实 S018 原 checkpoint/JSONL 与原通道帧，X/provider/tools 是显式 NoEngine 脚本端口，SnapshotStore/SessionRun/新服务实际执行。该批只验宿主胶水，不代替原 S27、真实 X 停止隔离、代理或完整 Runtime 验收。

export_read窄口：`plans.resolve_read(request.read_ref, frame.read_result_ref)` 返回经原 owner 授权核验的真实 host file ref（path/bytes/sha256）。服务只读该返回原件，与 Node descriptor 的 bytes/hash 比较；Node 原 frame 不变，另附 resolved_read_ref。不能读取 Node 自报容器 path；不能由当前 saved boundary 替换读操作帧。先行两例追加原18（不减原断言）；旧来源/evidence/before-export-read-001保留。

SS21：SessionRun.checkpoint 已获得原 X checkpoint 而 S.confirm 因坏 JSONL 拒绝时，必须通过内部 pending_confirmation / quarantine_pending(reason) 保留同一原 fullref。不得为 cleanup 再发 checkpoint 占满两份槽位。先行原失败保留；实际 SnapshotStore Q/原 owner receipt 验证同源，NoEngine 设施只统计请求次数与调用次序，不冒充真实物理停止。execution.py 此能力由根实现，本服务只消费该方法。
