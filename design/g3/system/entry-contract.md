# Runtime 与 M01 的最小 Python 接口

根审已接受；这是现有 R/E/X/F/S 的组合入口，不是新的业务协议。当前实现/真实设施装配尚未完成，不表示 M01 通过。

```python
rt = Runtime(config, session_service=..., provider_bridge=..., checkpoint=None)
await rt.open()
rt.register(principal, *, request_id, resource_id, namespace, kind,
            path, harness_ref, grants)
rt.start(principal, request)
await rt.drive_until(principal, request_id, *, deadline_monotonic)
rt.query(principal, request_id)
await rt.close()
```

register 参数/返回直接沿用 R.register；目录由调用者创建，surface/workspace 登记不启动。start 只向 R 受理原 {id, namespace, kind:"invocation", payload}，不调用模型或工具。payload 保留 resource_id/resource_revision/harness_ref/input_ref/input_binding，并绑定 S 的 session_ref/source_result_ref/capability_ref。同身份不同完整内容仍拒绝。输入选择器原字段不变；execution_targets 必须用已登记 resource_id，不能以 id 替代。E 保存唯一输入 ref 并由 R.bind_input 确认后才交给 Harness。

drive_until 使用现有公平 R.claim/renew，不能假装按指定 ID claim；request_id 用于观察该原请求及已受理 successors 的边界。只实施外部 Harness 已接受决定，沿原 holder/release/install/restore/wait 记录恢复；未知效果原身份查询或暂停，不重推理或重发。原 stop_ref、waiting、paused 或 deadline 使本次调用返回当前 query 快照，不产生业务 success/done/fail。已接受后继不得绕过当前 holder 停止、F 安装及 R 确认。query 只读原 R schema2 记录和引用，不触发 S.drive、capture 或新效果；可返回 requests/decisions/waits/holders/releases/installations 原记录的集合，不保存另一份账本。close 关闭共享句柄，不把它当作实际 release 证据。

config 仅含原设施参数：control_db、files_dir、execution_dir、session_dir、nats_url、engine_endpoint、authority、worker_id、event_profile、组件 limits 和原 system slot 预约。event_profile 原样沿 E 参数。session_service/provider_bridge 是可信宿主实例，密钥不入序列化配置或受限 Harness；各组件 authority/reference checker 由可信原件解析连接。模型、模板、投影、输出解释和继续策略属于固定 harness_ref。checkpoint 只给观察时机，不生成成功事实。

## M01 调用与观察

validation/system/m01.py 的 execute_sample(rt, sample, config, initial_refs, observer) 实际执行上述链。这里 config 是该次受信调用配置：principal、registration_principal、namespace、grants、page_size、start_sequence、filters；initial_refs 固定 harness_ref/session_ref/source_result_ref/capability_ref/surface_ref/previous_session_ref/execution_targets。所有引用由真实设施准备，不是测试代码自造可确认 ref。外部装配可先为合法 F 初始捕获完成同一登记；函数按同一 request_id 重交，沿 R 原幂等语义而不换身份。样本 ID 决定登记和首次 invocation 的稳定本地 ID，不进入 Runtime 业务判断。

observer 是独立验收代码，提供两个有限调用：begin(sample, registration_ids) 在 Runtime 操作前启动原设施采集；collect_m01(sample, request_id) 在 Runtime 停止/关闭后读原件，返回 artifact_files 的 report_path/notes_path/report_location 及原观察。前者异常不启动；后者缺失/异常明确失败。此函数不因其返回或 Runtime query 的声明给出 PASS；先调用原 sum_files，并返回 UNVERIFIED_PENDING_INTEGRATION_ORACLE，待实际观察器按原 M01 全部判据验收。

观察器直接读取 R SQLite mode=ro 的原请求/决定/输入/安装/holder/release；读取 F 原 Git manifest/archive，核双 SHA 与完整版本及当前授权后给产物副本；独立 provider 原请求响应、S 原 JSONL、X 原记录/实际 Engine、单独 NATS 连接的 seq 原正文共同证明两域执行、一次通知及下一 Step 输入。业务内容正确不能替代这些观察。

固定两输入×三次、真实与固定响应分批、模型/步数/token/300 秒及原资源预算不变。CLI 仅在实际 Runtime/S/provider 装配、F 历史解析、独立原设施 observer 三处接好后才可执行真实样本；目前 MISSING/0，不造 factory 平台或 fake result。
