# S → Runtime → M01 最短接线图

范围：对当前产品/原契约的独立只读实现定位，不是 S/G5 验收。实际包为 `lore_control / lore_events / lore_files / lore_execution / lore_session / lore_provider`；当前没有 `lore_runtime`。只完成已有 [entry-contract](../system/entry-contract.md) 的入口，不另建调度协议、Session 历史或验证平台。

## 可直接调用的真实入口

以下省略 `self`；R/F/X 同步，E 标 `await`。参数与现源码一致。

| 所有者 | 真实 API 与原件 |
|---|---|
| R 登记/责任 | `ControlStore(db_path, authority, ..., reference_checker, checkpoint)`；`register(principal, request_id, resource_id, namespace, kind, path, harness_ref, grants)`；`resolve(principal, namespace, target, access)`；`accept(principal, request)`；`claim(worker_id, now)` / `renew(id, token, now)`；`query(principal, id)` / `pending()`。原 SQLite，不含策略。见 [registration](../../../lore_control/registration.py)、[responsibilities](../../../lore_control/responsibilities.py)。 |
| R 结果/决定 | `save_result(id, token, result_ref)` → `accept_decision(parent_id, token, decision_id, source_ref, harness_ref, body)` → `apply_decision(parent_id, decision_id)`；恢复查 `query_decision(id)`，不重算已接受决定。`body` 必须恰有一项：`successors`、`wait` 或 `stop_ref`。见 [decisions](../../../lore_control/decisions.py)。 |
| R 外部交付/输入 | `mark_dispatched(principal, id, delivery_owner)` / `confirm_delivery(principal, id, receipt_ref)`；`bind_input(principal, invocation_id, binding, input_ref)` / `query_input(principal, invocation_id)`。`execution`、`provider_transport`、`event` 是设施交付；确认它们不结清父 invocation。见 [facilities](../../../lore_control/facilities.py)。 |
| E | `EventService(server_url, control_store, service_profile, checkpoint=None)`；`await start()` / `close()`；`await prepare_input(context, invocation_id, namespace, start_sequence, filters, target_dir, *, input_context)`；`await lookup_input(context, invocation_id)`；`await submit(context, request_id, namespace, name, payload)` / `query(context, request_id)`。prepare_input 已内含真实四文件发布、R.bind_input、原 NATS seq/正文复核；不要再写一套输入绑定。见 [inputs](../../../lore_events/inputs.py)、[publication](../../../lore_events/publication.py)。 |
| F + R 发布 | `FileStore(control_dir, authorization_checker, reference_checker, checkpoint=None, limits=None)`；`capture(request_id, binding, coordination, base_ref=None)`；`import_archive(request_id, binding, archive_path, source_ref, base_ref, profile)`；`materialize(request_id, version_ref, target_path, authorization, profile='host-v1')`；`read_reference(reference, authorization)`。R `acquire(resource_id, execution_id, base_ref)`、`prepare_install(principal, request_id, resource_id, execution_id, expected_revision, base_ref, staged_ref, restore_plan_id=None)`；F `install(request_id, intent, stopped_ref)` / `query_install(request_id)`；R `confirm_install(request_id, installation_ref)` / `release(resource_id, execution_id, stopped_ref, published_ref)`。 |
| X + S 宿主 | `ExecutionStore(state_dir, engine_endpoint=None, checkpoint=None, trusted_config=None, trusted_config_sha256=None)`；`SessionRun(execution, snapshots, request, authority, operation_id)` 的 `start / write(raw, fields) / read(maximum, calls) / close_stdin(fields) / checkpoint(checkpoint_id, purpose) / resume(receipt) / seal(receipt) / release()` 已包原 X API，保留 caller 原 call_id/offset。见 [execution](../../../lore_session/execution.py)。 |
| S 保存/模型运输 | `SnapshotStore(root, namespace, register, *, global_budget_bytes=...)` 的 `empty / confirm / query / receipt` 保留原 archive、owner 与 charge；`ProviderBridge(root, endpoint, model_scope, credential_provider=None, timeout=2.0).complete(original_scope, provider_frame)` / `.query(effect_id, binding)` 保留原 wire 文件，旧 ID 查询零 HTTP。见 [snapshots](../../../lore_session/snapshots.py)、[provider](../../../lore_session/provider.py)。 |

## 调用次序和持久化切点

1. 按原 Runtime entry 构造共享组件；R 登记真实两域目录和 Harness，再 F 捕获、解析已授权完整版本。明确 `start` 只调用 R.accept 原 invocation；原 selector 中 `execution_targets` 使用 `resource_id`。E.prepare_input 固定 H/range、落四文件并绑定 R 唯一 input_ref；之后 R.claim 才可能交付。公平 claim 的返回身份是真正执行身份，`drive_until(request_id)` 不能伪装指定 ID claim。
2. 可信 resolver 由原 R 登记/selector、F 完整版本、S snapshot、固定 Harness 和能力组装 X schema2 请求；启动 SessionRun，发送原 `lore.s/1` accept/query/drive。accept 的 Node 结果帧仍属临时回执；原 Pi accept + 完整 binding 经 X checkpoint → S.confirm 独立持久副本后才可确认受理。配置里的 `{id,sha256}` 仅是受控传输 descriptor，不能代替 R 的 E.input_ref 或 F 完整历史引用。
3. provider/tool 请求先查当前原 Pi pending 的 responseEntryId / resultEntryId，并 checkpoint 保存该前缀；稳定 effect ID 原样贯穿 R 设施受理/dispatch 与真正所有者。中间 checkpoint 仅在保存后 resume 同对象；ProviderBridge.complete 或原 X 工具执行后保留原回执，按原 IDs 回复 Node。失 ACK 只查原件；已保留 wire 但 Pi 仍 pending 用 `paused_reconciliation_required`，不能重发/补写成功 Pi 历史。E 的 R20 完整 receipt wrapper 已实现；X/provider 的关联只可从真实原请求/回执包装，不可照抄 E owner 或用 success 生成回执。
4. 最终原 Pi result 与 `lore.s.boundary` 已写后，SessionRun.checkpoint → SnapshotStore.confirm；确认原 result locator 指定的 JSONL 前缀/hash/结果后，R.save_result **直接保存同一个 S operation_result_ref**。R [storage._reference](../../../lore_control/storage.py) 不要求新增 R 结果格式：它只调用可信 `reference_checker(ref, 'result', None)`。resolver 必须从真实确认 archive 按 `session_range` 核写 boundary 前的 JSONL **原前缀**（不是当前 whole-file hash），严格解析原 transactions / `lore.s.binding` / `pi.result`，再查其后实际保存的 `lore.s.boundary` 是否仍引用同 locator/decision。`result_sha256` 来自 Node `JSON.stringify(result)`：须核原 pi.result value 的精确 JSON 字节范围，不能 Python sort_keys 重序列化或假定摘要等价；无需为读普通 ref 再启动 Node。不能只相信返回字段或内存缓存。原决定事务受理/实施后，最终同 freeze seal；S 真实 ownership receipt 转移最后 X checkpoint 后 release。未确认或坏 Session 不得制造有效 owner。
5. 普通工具的原 X 完整输出、checkpoint 和 stop 原件进入 F.import_archive；新版本 materialize 到独立 staging，按原 R holder/base → prepare_install → F.install → R.confirm_install → R.release 完成权威根发布。F 失交换 ACK 先 query_install，不能重新交换。下一责任即使已受理，也须等本次 holder/安装完成，不能先写新目录。等待/恢复继续用 R 原 waits、release ledger、RestorePlan，不新增业务终态。

## 仅剩的薄产品接线

**外部决定：不需要第二次策略执行。** 当前 [minimal Harness](../../../harnesses/minimal/index.mts) 的一次 `decide(result, original, source)` 已得到原 source/binding，并将提议保存进原 Session；但它目前只输出 `{final:{content}}` / `{continue:true}`，R 不接受这两种 body。给同次受限 Harness 加入已固定的原 invocation/selector/可验证引用上下文，由它直接产出稳定 `decision_id` 与 R 原型 `body`；原 final/continue 可保留为 S27 兼容观察字段。宿主只核原 body、source/harness 并提交，禁止由 boundary_kind/final/continue 自行补 stop 或 successor。stop_ref 指向本次已保存的原完整回答/外部停止决定证据；可信 resolver 用 R 给出的 parent/source/harness 核同一个原 boundary。无需新 Node decide action、R-ref 真相或第三个 loop。

这里有一个必须接实的数据点：R 在受理 successor 时已校验 resource_revision，R.confirm_install 又会增加 revision。Harness 构造下一请求所用的 revision、Surface/Workspace/F 引用须来自当次可信原输入或真实已发布工具反馈；Runtime 不能事后改写 body、把旧路径冒充新版本。现 [tool_results](../../../validation/components/s/tool_results.py) 只有 F.import_archive + 另目录 materialize，既不 install 登记根，也不提供完整 R 安装关联。最薄实现是补实际工具发布与反馈引用，让 Harness 明确使用对应状态；若选择在决定后安装，须明确该先行 successor 绑定如何与后续版本成立，不能宣称现胶水已经解决。

**可信 Session/工具装配。** 复用 SessionRun、SnapshotStore、ProviderBridge；把 [collector](../../../validation/components/s/collector.py) 中有限帧收发/pending 校验调用次序抽成宿主 S service，把 [ExecutionPlans](../../../validation/components/s/execution_plans.py) 的真实 X 请求形状交给生产 R/F resolver。不要把 fixture `Peer.allow`、固定输入/response 分支、test_cleanup 或 `self.tools` Map 当生产 authority/recovery。同一 X owner 持续服务，短 caller EOF 不杀原 owner；原 X query/receipt/hash 才是工具查询依据。F 返回 `current_root/retired_root/original_intent`，R.confirm_install 要 `current/retired` 及原完整请求关联；需要依据实际 F 回执做字段适配和 authority 核验，不能把两个返回字典直接互传。

**Runtime 与 emit。** 落已有 entry-contract 的 Runtime 外壳，装共享 R/E/X/F/S 和上述 resolver；不在 Runtime 导入 Harness 或 sum/notes 验收逻辑。普通 Runtime Shell 的有限 emit 到 E.submit 的实际受控传输尚不存在，必须接上原授权 source/namespace/name/payload/稳定 ID；普通 stdout 或任务文字不能冒充 emit 控制帧。E 已内建真实 publish/负回执/query，不另建消息库；下一显式 Step 用 E.prepare_input/lookup_input 读同一原事件范围。具体传输尚未实现，不以 S 固定 events.jsonl 夹具冒充这项通过。

## 原 M01 的直接观察点

现 [m01.execute_sample(rt, sample, config, initial_refs, observer)](../../../validation/system/m01.py) 已实际按接口调用；CLI 当前仍 MISSING/0。只补真实装配和已有 observer 两个方法 `begin / collect_m01`，复用原 `artifact_oracles.sum_files`，不重写产物算法。

| 原 M01 必须项 | 直接原件及现入口 |
|---|---|
| 两输入 × 三次，正确 report / notes 历史链接 | 原只读 numbers + F.read_reference 原 report/notes；F Git manifest/archive 双 SHA、真实 materialized 历史路径和当前授权核过后才交 `sum_files`。不能拿 current 同名文件或 `tool_results` 临时目录代替历史绑定。 |
| 两域真实执行/目录发布 | 独立读 R resources/holders/releases/installations 和 F query_install 原布局；X 原 request/result/两流/checkpoint/Engine 事实证明 target、完整 base、执行代次及真实停止。 |
| 真正模型/native tool 与投影 | ProviderBridge 原 request/response/usage + S 原 JSONL 的 assistant/toolResult 和 Harness 版本；核模板/blocks/位置/事件/反馈确实进入原 provider 请求。固定响应接线与真实模型六样本分批。 |
| 一次获准通知进入下一 Step | 独立 NATS 连接读原 seq/subject/正文，与 R 原 event receipt 完整 binding、E input manifest 的 H/range/event_refs 和 events.jsonl 逐字节相合；读取不确认父 invocation。 |
| 决定/预算/资源 | SQLite mode=ro 读原 requests/decisions/inputs（source/body 与原 S 提议相等）；真实 provider 数/token、步骤与300秒、原 slot/Engine/PID/volume观察。不能由 Runtime stopped 或模型 final 单独判业务成功。 |

本次未运行产品、Docker、模型或 M01；上述是原 API 与缺口定位，不把现 S27 诊断或组件通过升级成系统通过。
