# E-R20 回执绑定修订（实现前）

ER01：原 E 正 event_ref 与 rejected 设施 ref 不能直接传 R.confirm_delivery；它们缺少完整 request_digest 等 R20 字段。旧接口、driver 与索引已在 history/before-receipt-wrapper-004 原样保留。既有原生 NATS 准备仍仅证明设施，不能证明该接缝通过。

E 对应用的 CONFIRMED/REJECTED/UNKNOWN 及原 receipt_ref 形状不变。E 给 R.confirm_delivery 的另为窄控制包装：owner=E、kind=delivery_receipt、id=request_id+'.receipt'、request_id、namespace、source、delivery_owner=E、request_digest、outcome=positive|negative、definite=true、facility_ref、sha256。包装 sha256 为除 sha256 外全部字段的规范 JSON UTF-8 摘要；它不代替设施证据。request_digest 严格按 R20 原 {principal,id,namespace,kind,payload} 规范编码计算。原 E 受理请求 kind=event，payload 必须含 subject、event_sha256、event_bytes，分别绑定完整原包络的目标、摘要和字节数；不把消息正文复制到 R。其他合法控制关联若存在也纳入完整 digest。

positive 的 facility_ref 是原 NATS event_ref，negative 的 facility_ref 是原 rejected ref。E query 读取 R 原包装并核设施，向应用返回原 facility_ref，不把 negative 说成 NATS 保存。包装不能复用另一请求、namespace、来源或正文的设施证据；UNKNOWN/断线/查无不生成 definite negative。负回执重启后仍可原查询，同 ID 不重新发布。父 invocation 的策略责任不因 effect confirmed 结清。

独立 R reference authority 按 purpose=receipt：从只读 SQLite 原 requests 的 id/principal/namespace/kind/payload_json 重建完整原请求，核完整包装和 expected 关联。positive 用另一 OS 进程、另一直接 NATS 连接读取原 sequence 原正文、subject、Nats-Msg-Id，与原受理摘要/字节数核对。negative 读原错误文件，并核可信字节代理实际观测的同 PUB 回复：原 PUB subject/完整包络 hash/bytes/source/namespace/id 全部吻合，错误字节精确相等。仅匹配实际负 PubAck，不接受无关查询 API 错误。代理在转发前持久追加观察日志并 fsync；新进程读取该观察记录，不依赖原 proxy Python 对象。此日志仅验收设施，不是产品 E 的额外历史。真实产品的错误原件由 E 保存，authority 在 G4 注入核验；测试日志不进入产品事实模型。

新增准备批仅验证该 authority：真实 NATS 正常/容量拒绝 + 明确标记的 SQLite 原请求夹具（没有 ControlStore 或 EventService 替身）；正例必须可接受，全关联/坏设施/缺失/空包装负控必须拒绝。正式 E03/E05/E07 将从真实 ControlStore 核包装，并从独立原请求与 NATS/代理读证据。缺组件仍 15 项 MISSING，不计 E 通过。
