# E 实际 Python 验收接口（G3 待独立审查）

本文件固定验证入口及本地单进程服务 profile，不是生产实现。原 15 项在 cases.json；test_events.py 继承 input_cases.py 提供恰好 E01—E15，所有主项在真实 EventService、真实 ControlStore、真实 NATS 上执行。没有这些组件或正式 R 门槛时是 MISSING，不接受替身作为组件通过。

## 入口和有限资源

模块默认 lore.events、lore.control，可通过 LORE_EVENT_MODULE/LORE_CONTROL_MODULE 指明真实模块。ControlStore 是已约定同步库；EventService(server_url, control_store, service_profile, checkpoint=None) 的 start/close/submit/query/emit_observation/scan/prepare_input/lookup_input 为 async。close 幂等。authority 是受信宿主 profile 中 principal→namespace/role，context 参数只能是宿主调用方提供的 principal 字符串；任务或模型不能取得此库对象。context dict、来源冒充、无权 namespace 必须精确报 invalid/denied，不把异常 TypeError 当授权拒绝。

service_profile 字段由 fixture.py/profile 固定：namespaces、authority、runtime_principal、input_root、page_size、stream_max_bytes、message_limit_bytes、stream_prefix、subject_prefix、storage、discard、max_age、replicas。默认 8 MiB/namespace、64 KiB 完整编码消息；容量专例仅 1024 字节 stream，最多八次 256 字节文本尝试，既定停止界限而非 SLA。正式普通请求5秒、NATS启动10秒、故障worker15秒，子进程最多一次且复验三批顺序执行；四连接并发只用于32事件批。无真实模型/外网/凭据。

stream(namespace) 为 LORE_+namespace；单事件 subject 为 lore.<namespace>.event.<sha256(request_id UTF-8)>。namespace 使用当前授权显式 n1/n2/n3；生产一般 token 约束应服从 R ID/授权。实际 Nats-Msg-Id header 固定原 request_id。相同 ID 全局由 R 完整绑定审查，不能仅依赖 NATS subject 或 Msg-Id。NATS 文件存储、replicas=1、LimitsPolicy、DiscardNew、MaxAge=0，错误已有 stream 配置 start 精确报 configuration_error。E 不擅自清除或重建旧 stream。独立观察器不使用 E 的连接或状态。

## 事件编码、回复和拒绝

submit(context,request_id,namespace,name,payload)：原始 JSON 包络恰为 {schema_version:1,origin:"application",source:context,namespace,request_id,name,payload}。JSON UTF-8：sort_keys=True、ensure_ascii=False、separators=(comma,colon)、allow_nan=False，不加消息末尾换行。64 KiB 指完整包络字节，不是 payload 字符数。拒绝 NaN、集合、错误ID、来源保留字段伪造及超限，且在 R 受理前拒绝。应用消息名 done/fail 仍只是应用事件。

query(context,request_id) 不重新发布。正常 submit/query 返回 {status:"CONFIRMED",request_id,receipt_ref}；未知为 {status:"UNKNOWN",request_id,...原查询关联}。正 receipt_ref 恰含 owner:E、kind:event、request_id、namespace、source、sequence、subject、sha256（原消息字节）；它是 NATS 原查询定位，不把 R phase 等同 NATS 保存。同完整包络重复请求复用同结果；来源、域、名称或载荷任一改变 conflict。

实际 NATS 拒绝返回 {status:"REJECTED",request_id,receipt_ref}；receipt_ref 含 owner:E、kind:delivery_receipt、outcome:rejected、request_id/namespace/source/subject、error:{code,err_code,description}、receipt_path、sha256。receipt_path 保存实际 NATS 错误回复原 UTF-8 字节，不是竞争的事件正文。独立字节代理记录同条服务端负回复，R reference authority 对照它核验。R confirm_delivery 的 confirmed 仅表示该设施回执已保存；负回执不等于事件已入 NATS。原 ID 的负回执不可覆盖或重发；未来显式新 attempt 必须关联原 negative，UNKNOWN 不可借换 ID 绕过。本轮不增加自动 retry API。

emit_observation(context,request_id,namespace,observation_ref) 只允许 runtime 角色，并从真实登记/执行原引用构造观察。E01 的 application 原文与普通同名事件、无权调用拒绝并不独立证明 X 系统观察来源；真实跨组件观察属于 G5。

## 固定输入与真实路径

scan(context,namespace,start_sequence,filters) 返回 {events:[原包络...],range:{start_sequence,end_sequence,high_water,next_sequence},filters}；允许的有限过滤为 names 和 sources 的字符串列表，缺省 {}。先逐一验证范围内每个 sequence 实际存在，再过滤；分页按扫描的原 sequence 数计算，不能把漏掉的过滤内容当不存在。page_size 默认128；分页例为2。start=H+1 表示合法尾部空输入，start>H+1 invalid；空流 start1/end0/H0/next1。无权 denied、中段或保留前缀缺失 history_missing，不接受空列表替代错误。scan 不建立每等待 consumer/连接。

prepare_input(context,invocation_id,namespace,start_sequence,filters,target_dir,*,input_context) 的 input_context={surface_ref,previous_session_ref,execution_targets} 来自已固定控制输入，不由 E 选择 Harness 或目标。绑定 selector 为 {namespace,source,start_sequence,filters,page_size,surface_ref,previous_session_ref,execution_targets}。R 原受理 payload.input_binding 必须含这个完整 selector；R.bind_input/context/query_input 的最终签名见 R21 合同。R 仅存 selector 和输入引用，不复制 NATS 原文或重新计算 H。E 先 query 原绑定；重复调用直接复用原 H/文件，不按新消息更新同 ID。改变 source/range/filter/Session/target 之一 conflict。目录路径只决定首次发布位置；重交不能另发布一份新真相。

E 构造新目录，以固定 H 截断；完整发布并保存 R 关联后返回 input_ref={owner:E,kind:input,id:invocation_id,path:绝对实际目录,root:{dev,ino},manifest_sha256}。lookup_input(context,invocation_id) 先验证原关联、目录身份、文件集合/hash/原消息 refs；无损则复用同 ref。损坏或缺失精确报 input_invalid，责任和原引用保留，不静默重新制作。当前 profile 不提供 repair_input；未来显式修复须从原引用恢复完全相同字节并另验。

目录文件集合恰为 events.jsonl、invocation.json、execution-targets.json、manifest.json。expected_input 在独立验证器中固定编码（同上 JSON + 单个 LF）：
- events.jsonl：按 sequence 顺序，过滤后每条原包络原字节加 LF；
- invocation.json：schema_version/调用id/namespace/source/range/filters/page_size/Surface与previous Session引用；
- execution-targets.json：schema_version=1、targets=原 execution_targets 完整列表；
- manifest.json：schema_version=1、complete=true、调用id/namespace/source/range/filters、每条所选 event_ref、其余三文件长度/sha256。
manifest 不自循环列自己的摘要；input_ref 固定 manifest 字节 hash。range 的 H、end、next 来自同次真实源扫描。目录中普通文件可 cat，目标/Session 的实际 fixture 路径可达；这些 fixture 不证明 F/S 组件真实性，跨组件在 G5 验。

## 故障与独立观测

受信 async checkpoint(label,record) 只用于验证：after_dispatch_before_publish（原 R issued 提交后且尚未 publish）、after_input_highwater_before_scan（record.high_water 真值）。不得向模型开放，不能用标志代替真实持久状态。

E05 的代理解析并转发 NATS PUB/HPUB/MSG 原字节，只丢第一条实际服务端 PubAck，再 SIGKILL 独立 E worker；观察器直连 NATS，确认已存原 sequence/bytes。恢复仍走代理，直接数实际 PUB，拒绝靠 NATS dedup 隐藏重复发送。E06 在真正 issued 切点杀 worker、原 subject 查不到仍 UNKNOWN，不从验证者“知道未发送”推导系统有安全重发证据。E04 对真实 NATS PID SIGKILL，重开原 file store 三个独立批。

E09 观察 Python profile 的真实 os.fsync：包装调用先读取实际 fd dev/ino/完整字节 hash，再调用原 fsync；要求四文件完整字节、最终目录和父目录都有成功调用，不接受 SUT 的 complete/durable 声明。这不证明掉电与异构文件系统；native fsync 路径若采用必须补相应观察器，不能缺失即通过。输入文件另逐字节读；同长度改动也拒绝。测试者对自有已发布测试输入施加故障，不把这种宿主访问等同任务的写权限。

E 仅验证扫描可恢复起点；等待条件、匹配幂等和父 invocation 接续仍在 R/G5。E15 从 NATS /connz 与真实 stream consumer_count 观察连接/consumer，十二次扫描不得增长，close 后只剩独立观察器。此数量不是系统高并发或等待归零证明。

## G3 边界

正式运行必须有 LORE_R_GATE 指向的 G4 R PASS：{component:"R",stage:"G4",status:"PASS",implementation:{绝对源路径:sha256}}，含所载 R 模块且所有声明实现文件摘要重新核对。此文件必须由独立 R 验收给出，source/hash 绑定，并加载实际 E。缺组件会执行全部15项并报告 MISSING/ERROR、退出非零；没有假 E。test_oracle.py/runner负控/原生设施 preparation.py 的通过只表示验收准备可工作，不算 E 通过。真正代码错误、接口错误、超时、零项、skip、少项、缺原始证据均失败。当前 await/进程驱动主要路径尚无组件可运行；独立审查应检查协议与源码，不将准备通过扩大为产品性质已验。

R21 对齐：R.query_input(principal,invocation_id) 返回未绑定 None 或 {invocation_id,binding,input_ref}，缺失 ID 为 not_found；R.bind_input 仅 runtime 可调用。目录/manifest 已损坏时 R 的 reference_invalid 由 E 对外映射为 input_invalid，并保留原行。E 先以受信 runtime 查询原完整选择，再比较调用来源；同 ID 改为另一有权来源仍 conflict，不能把读取权交给该来源。E fixture 使用真实 R 最小目录登记及 kind=invocation/input_ref=None/input_binding；Harness 引用只是一份不执行的普通文件，属于 R reference authority 夹具，不构成 F/S 通过。准备未绑定不得交 Harness 的性质由 R21 单独验。

R20 完整控制回执以 [receipt-binding.md](receipt-binding.md) 为准：本文件上面的 event/rejected ref 仅是对应用的 facility_ref；不能直接传 confirm_delivery。
