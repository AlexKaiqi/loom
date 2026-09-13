# 原 S 结果引用的只读解析

状态：先行契约；仅新增 `lore_session/references.py`，不修改原 S27 标准或既有产品。

`resolve_original(snapshots, confirmation_request_id, original_ref, expected_binding)`：snapshots 是已配置的可信 SnapshotStore；确认 ID 与完整 expected_binding 来自受理关联，不能由待验 ref 反推。调用原 `SnapshotStore.query` 后只读确认 archive；无新缓存、文件写入、registry 更新、Node/provider/tool/Harness 执行。正常 query 拒绝的原件（包括隔离坏 Session）不能作为健康来源。

返回 `{reference, binding, operation_result, boundary, snapshot_ref, owner_record_ref, storage_charge_ref}`，均为原数据的独立副本。失败为 SnapshotError(code='reference_invalid')，调用方可以保留异常原因；不得将任意代码异常视为预期拒绝。此模块验证来源，不解释 final/continue、不生成 R body 或业务终态。

依据是原 Node `bindingFor`、`OriginalSession.locator` 与 adapter 保存 boundary 的顺序。original_ref 必须完整且字段精确；scope/session/op 与外部完整 binding 一致。session_range 必须 `[0, session_bytes]`，界限落在完整原 JSONL 事务行末；hash 验该原前缀，而不是后续 archive 中的整份 JSONL。严格解析原 metadata/header/transactions、绑定与 pi.result；result hash 从原事务 `value` JSON 字节范围取，不排序重序列化。prefix 中目标 result 已保存、原操作 pending 已清；后来另 operation 的合法记录不能使旧 result 失效，目标 result/binding 本身不得被覆盖或删除。

若目标 `lore.s.boundary` 已保存，必须在该前缀之后且引用完全相同 locator；若有提议，source_result_ref/harness_ref/input_ref须与原关联一致，返回原提议不重算。若 boundary 尚未保存，仍返回实际已存 result、boundary=None；调用者不得据此受理不存在的决定。最后的业务停止/继续与 R checker 适配由 Runtime 另接。

用例与固定真实原件见 `validation/session_references/protocol.json`；入口 `python3 -B validation/session_references/run.py --batch NAME`。使用真实 S003/S018 confirmed 原件，以及明确标注的私有存储故障副本；不把这些派生副本当新 X 物理保存证据。缺产品记录 MISSING/0，错误实现/源漂移/任意非预期异常不能通过。作者运行只作开发验证，根 Agent 另独立复跑。
