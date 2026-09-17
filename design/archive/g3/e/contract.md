# E：受控事件与固定文件输入合同 v1 草案

状态：G3 DRAFT，尚无生产适配。依据 v5 §4.4/5.1/5.4/6.5、G1 §3—5，P06/P08/P09/P10/P12。依赖 R 的已验完整受理/引用接口、真实 NATS JetStream 及普通 Linux 文件，不实现消息存储、文件锁队列或新业务终态。

## 所有权与服务边界

NATS 持有完整事件与 stream sequence；R 持有提交身份、全内容绑定、已交出/已确认引用、输入关联和待核对责任。输入文件仅是一次调用的固定只读视图。E 提供普通库 EventService(server_url, control_store, service_profile)，可信宿主连接 NATS；任务/模型不接收 NATS/管理凭据或该对象。

服务采用固定 G2 NATS 二进制与 nats-py2.15.0，file storage、sync_interval=always、replicas=1、每 namespace 独立 stream，LimitsPolicy + DiscardNew，MaxAge=0、不自动 purge/delete。排序是本 namespace stream 的保存顺序，不是跨 namespace 的全局因果。每 namespace 的容量受配置限制，达到上限明确拒绝新存储并保留原历史；不得为让新请求成功删除恢复依赖。首个验证 profile 为8 MiB/namespace、最多64 KiB的完整消息、最多128个namespace；数字是有限本机试验的容量/破坏预算，不是用户 SLA 或超大等待容量结论。默认交付 profile 在 G5 部署/负载协议中明确，所有限额可配置且受准入，总预算不能通过新增无限namespace绕过。

承诺成功确认后进程 SIGKILL/server重开仍有原字节；不声称当前实验覆盖实际掉电/磁盘损坏/多副本网络分区。任何历史必要序号缺失、错误服务配置、消息正文校验失败必须显式报错；不能因没读到就返回空事件。已受理工作依赖的范围不得被 E 的保留管理删除。当前版本不提供自动删除接口；运维手工篡改不在自动修复承诺，但读取必须发现缺口。长期保留到配置存储耗尽后拒绝新工作，扩容由外部明确操作。

## 发布和回执

- submit(context, request_id, namespace, name, payload)：context 来自实际已授权入口，不能从payload中的principal/system字段继承。完整信封包含 server-assigned origin（application 或 runtime observation）、authenticated source、namespace、request_id、name、payload 及格式版本。应用可以声明名称为 done/fail，但不能提升为 Runtime 已确认事实；保留系统事实专用 origin/来源，伪造 origin 或保留系统提交类型拒绝。
- 完整输入校验、来源/namespace权限及实际字节限额在受理前执行。拒绝是 REJECTED 且没有新消息；校验后 R 持久接受时为 ACCEPTED，只有 NATS PubAck 或原消息查询确认并保存引用后为 CONFIRMED。此确认只说明消息已存，不表示系统登记/执行/业务任务完成。
- 同一 request_id 绑定完整信封和调用来源。完整相同复用原受理/事件引用，不重复 publish；任一内容/namespace/source/name改变拒绝并保留原事实。原生 NATS Msg-Id 去重不承担该冲突检查。
- publish 前持久标记原请求已交出，按稳定单消息 subject 和 Msg-Id 提交；丢回执时 query(request_id) 向 NATS 读原 exact subject，核对完整原字节/headers，再补原sequence引用。不得重新生成ID、相信Msg-Id窗口永续或把连接断开视为未发出。
- 已交出但原消息暂时不可查/连接不可用时为 UNKNOWN，保留原责任并暂停核对；不自动重发可能已发生事件。只有原状态明确尚未交出时才可按原身份首次交付；服务端明确negative回执固定为REJECTED，同ID复用原回执且不重发，未来新attempt须显式关联原negative。query 不产生新消息，恢复批直接核生产端stream中实际条数。
- 可信 Runtime 观察入口 emit_observation 只由宿主拥有，依据已验登记或执行对象形成系统来源；不能把任意应用同名消息升级。注册消息先被保存也不自动等于资源登记完成。

## 固定输入视图

prepare_input(context, invocation_id, namespace, start_sequence, filters, target_dir) 在开始时固定高水位 H，选择显式范围 [start_sequence, end_sequence]；end 为 H 或配置的分页边界。start 的含义是包含该序号；空流 start=1/H=0 是显式空范围。多页只保证本页约定范围完整，metadata 同时给出高水位与 next_sequence，不能把部分页标为整个历史。过滤条件只做该范围内的授权选择，保留过滤器/来源/包含与排除计数。模型不直接访问底层SDK。

实现先逐实际序号核对完整历史，再选择允许的事件；每个应该存在的原序号缺失都报 HistoryMissing，即使缺失消息可能本来会被过滤。start 早于承诺保留首位同样报缺失，start>H+1 为不合法起点。超出授权namespace或source不能静默返回空集合。固定批期间新消息留给下一明确输入。

在全新临时目录完整写 events.jsonl、invocation.json、manifest.json 和 execution-targets.json，fsync所需文件/目录后发布不可变目录并在 R 关联 invocation→input_ref；尚未完整/损坏/摘要不匹配的目录不交付给 Harness。实际参数 RUNTIME_INPUT_DIR 或同义显式参数给当前环境可访问路径，readonly挂载由 X/S 实测。元数据列事件范围/筛选/authenticated source/输入完成状态/原event refs/文件长度与hash/当前Surface及前序Session引用。跨环境路径是解析后的授权位置，不能含宿主密钥路径。

lookup_input(invocation_id) 返回原已确认视图和绑定，新进程仍是同一内容；同invocation改range/filter/source冲突。读取、cat、修改未授权副本或删除客户端副本不确认消费、不能消除推进责任。权威输入丢失时lookup_input精确input_invalid并保留原责任/引用，不静默重建。未来显式repair_input若提供，只能按原范围/refs恢复完全相同字节并另验；当前profile无隐式修复。

## 等待与持续交付

E 提供历史扫描，不为每个等待创建消费者、连接、线程或进程。共享连接可以常驻；条件判断由外部固定代码、静态wait范围和起点给出，R承担匹配交付的事务关联。事件早于等待登记、发生于扫描/订阅间隙、通知丢失都可从原起点重读。代码条件不等同事件名称。真正多 Surface 的唤起和静态驻留在G5另用全部真实组件验收。

## 独立预期和失败域

实际NATS server使用每批独立临时存储、随机空闲localhost端口及明确PID。oracle从独立连接查 stream_info/get_msg 及实际文件字节，不用E自身列表生成预期。故障用真实SIGKILL、保存后丢回执、重连查询与服务端删除指定已知消息（仅测试独立stream）。需真实R后才可做完整E正式批；G3可运行NATS准备/损坏与缺失oracle，R测试替身只能用于接口准备，不能被算完整E持久交接通过。

固定正式功能矩阵含两个namespace、每域三个有独立正文的事件，边界额外填满独立8MiB或更小显式测试profile验证DiscardNew与完整旧消息保留；不得改成DiscardOld。服务启动等待最多10秒、单调用5秒是验证停止条件，超时失败不是忽略。正确性每例一次，故障交接预定3次新目录独立批；并发发布4连接各8事件总32，独立检查唯一身份和每保存序号对应原字节，不凭提交时间推顺序。性能/极高驻留在G5另冻结规模和评估方法。

R/E交付接线按G3-RE-01：E以原应用principal/完整event请求调用R.accept(kind=event)，可信E服务身份调用mark_dispatched(owner=E)取得唯一fresh许可，再对NATS发布。取得原PubAck或查询原消息后由confirm_delivery保存对应消息引用，只确认这条事件提交，不结清父invocation。接受记录与确认不是Harness通用终态。


## G3-E 语义澄清 002（保留前文历史，不追溯通过）

原 contract 副本保留于 validation/components/e/history/contract-before-clarification-002.md。由根独立确认的两项最小 profile 澄清：R.confirm_delivery 可保存权威 negative 设施回执，但 E 外部状态始终 REJECTED，不表示事件保存或父 invocation 结清；同原 ID 不重发/不覆盖原 negative。真正 UNKNOWN 保留原身份，不能伪造拒绝证明或换 ID。

lookup_input 在损坏或缺失时必须 input_invalid，保留原责任、NATS和文件引用。旧文允许的字节重建不在隐式 lookup 中执行；未来如提供 repair_input 须显式新操作、相同原引用恢复完全相同字节并另验。当前不要求新修复 API，也不把报告损坏当作删除已确认责任。具体字段/编码/切点固定于 interface.md，原十五项仍全部 UNVERIFIED。

## ER01 与 R20 的完整交付回执

[receipt-binding.md](receipt-binding.md) 固定原受理请求→generic delivery_receipt→原设施引用的唯一绑定。对应用原 event/rejected ref 不变，R confirmed 不等于事件保存。旧稿保存在 validation/components/e/history/before-receipt-wrapper-004。
