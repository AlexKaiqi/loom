# E 可信系统观察的窄补件（实现前待独立审查）

来源：v5 §4.4/5.1 要求系统事实由原登记/执行对象确认；E contract 与 interface 的 emit_observation 正向语义已有要求，但 E01 只验证应用拒绝与 application 来源。不得把永远拒绝 runtime 输入当作已实现正向观察。原十五项和九项准备完全保留，本补件只预注册第一个可实际核验的 R 登记来源。

保持 `emit_observation(context, request_id, namespace, observation_ref)`。context 仍是受信入口字符串；E 根据 profile.authority 的 namespaces/roles 要求 runtime。payload 不能提供 principal、origin 或名称提升权限。复用 ControlStore 已有可信 `reference_checker(ref, purpose, expected)` 回调，purpose 为 observation；无回调/返回非 True/原来源错误均在 R event 受理与 NATS publish 前 reference_invalid。不是新增观察事实库。

首个支持映射是 R 原 surface register 完成记录。observation_ref 恰为 `{owner:"R",kind:"registration",id:<原 register request_id>,namespace,resource_id,revision,sha256}`。sha256 取 R.operations.response_json 的原 UTF-8 字节；这些字节原由 register 的提交事务持久保存，必须直接读取，不能把当前返回值重新拼接冒充原件。id 定位原 operation，原 binding_json 必须 op=register，且原 response 的 namespace/resource id/revision/kind=surface 与绑定一致。注册记录代表原登记动作已完成，不保证该资源永久存在或当前版本未改变。当前适配不合成 X/S 的未知事实格式，后续对应原 owner 映射仍须先行契约。

E 对可信 checker 传入 expected 恰为 `{namespace:<入口原namespace>,source:<已授权context>,event_name:"surface.registered"}`。checker 必须核 ref.owner/kind，并绑定原 register 主体、namespace、resource id、revision、原哈希和成功 response；不能仅按 E 传来的 expected 或 ref 自报内容返回 true。本 profile 原登记主体须与 observation 的受信 runtime source 一致。

通过后发出的原消息恰为 `{schema_version:1,origin:"runtime",source:context,namespace,request_id,name:"surface.registered",payload:{observation_ref:<完整原ref>}}`，用原 E 规范 JSON 编码，无末尾换行。其后走原 E/R20 发布与完整包装，event_ref 对外形状不变。无权应用 `submit(name="surface.registered")` 仍是 application；一般应用名称不受业务终态规则影响。同 ID 完整相同复用原回执，任一 ref/来源/namespace 改变冲突。

独立正向用真实已验 R.register 保存一份 Surface 登记，oracle 直接读 SQLite 两段原文本并保存原字节，再从独立 NATS 连接核原消息、headers/sequence 与 R 完整 receipt。错误对照使用真实但不匹配的另外 namespace/资源/workspace 登记，以及 wrong owner/ref/hash、缺原 operation。不得仅通过不存在文件制造全部反例；各拒绝均观察 R event 请求、NATS 原 stream 与实际 proxy PUB 不增加。另保留字节/身份 oracle 的合成坏样本校准，与真实 SUT 分开。

补充入口/固定样本/资源预算见 observation-protocol.json。真实 R gate 缺失为 MISSING；真实 E 缺失也为 MISSING。真实 R 来源是组件依赖；Harness 文件 authority 仍为非执行的 F 夹具，不宣称 F/X/S 或系统组合已验。

根预审澄清：同 namespace 的第二个真实 Surface 原登记本身也是合法事实。EO06 拒绝的是“id 指向第二个真实 operation，但 resource/revision/hash 仍属于第一个”的混合绑定；随后必须用第二个原登记的完整 ref 正向发布成功。调用参数没有另一个独立目标资源字段，因此不能凭测试者偏好只许第一个 Surface。E request_id 是这条事件的交付身份；原登记关联只来自完整 observation_ref 指向的 R 原 operation，其事实由独立只读 SQLite 原字节决定。trusted expected 的 source/namespace 来自已授权入口上下文，事件名称来自窄固定映射，绝不从 observation_ref 或应用 payload 取得 principal/权限。

EO06 追加完整同 ID 冲突：第二个完整真实合法 Surface ref 使用原 observation-1 调用身份时，必须 conflict；独立比对原 R 请求/receipt、NATS 原 sequence 字节和实际 PUB 计数全部不变，然后才以 observation-2 新身份发布该第二个真实登记。原 E03 的 application submit 不能替代这个 runtime 入口。旧补件及缺组件证据保存在 design/g4/e-author-observation-before-conflict-001；最多 15 次调用、2 条已存消息的有限预算保持。
