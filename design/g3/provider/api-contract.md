# Provider wire Python API 与事实归属（实施前附录1）

根已确认此窄接口方向。`lore_provider.WireClient(endpoint, scope, evidence_dir, timeout=2.0).complete(intent)` 只负责一个有限请求的编码、一次 HTTP、先保存实际已收原件、严格映射。没有工具执行接口、业务 final 接口、Session 循环、自动重试或模型选择策略。

`endpoint` 是可信构造参数 `{scheme, host, port}`；测试只注入 `http/127.0.0.1/本批实际监听端口`。它不是 intent 字段，容器/模型不能指定 endpoint、headers、认证或预算。此 fixture 约束不固化为产品永久只可 localhost；未来真实代理的可信配置、认证、TLS/物理隔离和 Pi 接线仍须按 S 第3/4项另验，本批不能证明它们。当前不提供、不读取认证密钥。

`scope` 是可信方固定的完整 Session/operation/response_entry_id/input_ref/harness_ref/capability_ref；必须与 intent.binding 精确一致。intent 只有 binding/model/max_completion_tokens/context，context 只有 systemPrompt/messages/tools；原9个请求样本定义允许值与拒绝。固定 shell schema、UTF8 JSON 编码顺序和分隔由三个原 request.raw 样本决定；映射不得将原工具反馈遗失、替换原 ID 或调换顺序。

`evidence_dir` 是可信新目录，普通模型无法选择。complete 不接受 expected/case ID。每次创建独立收据目录并保存 `request.body`（仅已验证且将发送的请求）、`response.body`（实际已收全部或前缀）、`transport.json` 与 `association.json`。先持久保存原件与 transport/association 再返回解析成功或失败；解析失败不删除 wire。短响应只保留实际前缀，不补字节、不改 complete；超限时保存有界前缀并标完整性未知/false，不声称全 body。

返回形状：成功 `{accepted:true, normalized:{message,wire,pricing}, request:{sha256,size,method,path}, transport:{http_status,content_length,received_size,complete}, artifacts:{request_path,response_path,transport_path,association_path}}`。normalized 与既有成功 fixture 的完整对象严格比较；不从 message 丢字段或补不明 usage。失败 `{accepted:false,reason,request,transport,artifacts}`：拒绝请求 reason=invalid_request 且后三类值均为null，实际 HTTP connect/request 均0；已发送后的失败 reason 沿原24样本，仍返回真实请求、传输与已收前缀 artifacts。没有完整服务响应时不伪造 normalized。

association.json 保存完整原 binding、可信 scope、已编码 request sha256 与实际 response sha256；transport.json 保存与返回 transport 相同的真实长度/状态事实。wire.sha256/size 必须匹配实际 response.body，不从服务提供的 id 或组件声明推断。外部 collector 直接核文件、实际 localhost socket 收到的请求与发出/关闭记录。原件保存不替代 Pi 的原 Session 保存，也不将此映射的调用与费用占位提升为业务确认。

单请求 timeout 最多2秒，response<=1MiB，编码 request<=65536 bytes；响应及 native arguments JSON 容器深度分别<=32。完整 batch<=32实际请求、45秒、64MiB原输入输出、1 server / <=2活动TCP连接。外部驱动强制超界失败，保留已收证据，不放宽原样本。
