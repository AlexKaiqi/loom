# R：登记与持久运行责任合同 v2 局部修订草案

范围：R 的控制事实库和事务接口；不证明真实模型、事件服务、文件快照或 Linux 撤权。G2 gate 是前提，D01—D05 未裁定，尚无生产实现。来源：v5 §4.1—4.4、§5.1—5.4、§7.2，G1 顶层合同§2—5；P01/P03/P06—P11。原 244 候选映射仍需总接口完整性核对。

## 责任与输入

采用 Python3.10 标准库 sqlite3，外部真实 SQLite 文件。存登记、授权、完整受理关联、待执行/待核对/待决定责任、已接受外部决定、后继、静态等待和资源占用记录。禁止复制 Session 模型正文/工具历史或 NATS 事件正文作为竞争真相。实际正文由各所有者保存，R 存不可变引用及交付关系。

ControlStore(db_path, authority, lease_seconds=30) 是受信宿主库。authority 是宿主配置提供的 principal→namespace/role 集合，不能由来自模型的 JSON 重建或提升。每次调用显式 principal；模型和普通任务没有 db_path、此对象或控制端点，实际物理隔离由 X/S 验证。R 防止通过载荷字段伪造调用 principal 或 system 身份；不是防御恶意宿主同 UID 管理员。

请求对象为 {id, namespace, kind, payload}；id 由调用设施生成，1—128 个 ASCII 字母、数字、点、下划线或连字符；kind 为内部调用类别，payload 是有限 JSON 数据，拒绝 NaN/Infinity/过深嵌套和超过配置字节预算。完整绑定包含 principal、namespace、kind、全部 payload（包括 input_ref/source_ref/harness_ref/target 等实际字段），使用类型明确的确定 JSON 编码；不得只比较正文的一部分。相同 ID 完整相同返回原关系；任何关联不同报 Conflict，不能覆盖或换新身份逃避。默认 256 KiB 请求上限是控制记录的资源预算，足以容纳引用/参数而不承担原日志存储；可配置且变更须复验。边界测恰好上限与超过上限，不是用户 SLA。

## Python 内部调用面

下列方法是普通库接口，字段表是持久记录结构，不是面向模型的业务 DSL，也不解释 done/fail 或工具成功的业务含义。验证入口以显式模块工厂创建实例。

- register(principal, request_id, resource_id, namespace, kind, path, harness_ref, grants)：管理员登记已存在普通目录，记录 realpath/dev/ino 和绑定修订号；重复完整相同幂等，差异冲突。kind 为 surface/workspace/parent；普通编辑不改登记。调用不启动模型或创建运行责任。
- resolve(principal, namespace, target, access)：target 是登记 ID 或显式绝对位置；重验目录对象真实身份、授权及唯一匹配；无权、缺失、替换、未登记、重叠歧义显式拒绝，无宿主回退。普通目录内容变化仍有效。允许在已授权 parent 下由普通 Shell 创建新目录再登记。
- rebind(principal, request_id, resource_id, expected_revision, harness_ref) / relocate(..., new_path, expected_revision) / unregister(..., expected_revision)：显式变更登记，旧路径不可继续使用；开始调用保留原不可变绑定，不受后续 rebind 影响。已受理责任的历史不删除。移动需指向原 dev/ino，替换对象需新的登记身份。并发修订不覆盖。
- accept(principal, request)：校验、事务受理并返回原 binding 与 phase；成功回执在事务提交后。payload 中针对登记资源的 invocation 须把实际 resource revision/harness_ref 固定进完整绑定，不能使用自由填写的新策略覆盖登记。query(principal,id) 可在全新进程读取原关系。
- claim(worker_id, now)：公平领取 ready 责任；同 namespace 内按接受顺序，namespace 间按最近领取次序轮转。返回 claim_token、原请求、mode。新受理为 execute；已交出的执行者失联/租约到期只能是 reconcile，不自动重做外部副作用。时钟跳变可提前核对或推迟发现，但不能释放真实写者或更改结果。续期和更新都校验 token。
- save_result(id, token, result_ref)：结果引用保存后 phase=decide，原责任仍未结清；普通工具结果不能直接终结调用。result_ref 必须是可校验的原所有者引用；真实性由调用方通过已验组件查询，R 的独立用例以显式 reference authority port 核验，真实跨设施另验。
- accept_decision(parent_id, token, decision_id, source_ref, harness_ref, body)：在实施任何后继前保存完整外部决定关联；同身份变更任何来源/版本/body 冲突。R 不运行策略生成 body。body 记录外部代码已决定的后继请求、等待安排或 stop_ref；不是可执行表达式。
- apply_decision(parent_id, decision_id)：一个 SQLite 事务内受理决定列明的后继/等待或引用已保存 stop_ref，然后结清旧责任；不得有删除旧责任且没有可恢复后继的窗口。重复 apply 返回原后继身份。stop_ref 表示本次完整回答/有依据停止的原记录，不能由工具成功临时制造。引用丢失显式报错，保持旧责任未结清。
- pause(id, token, reason, query_ref)：明确未知/无安全继续依据，保存未决和原查询身份；不是确认状态丢失的遮掩，也不算业务成功。重新核对仍用原身份。
- waits(namespace=None)：只查询静态等待；等待对象包含稳定 ID、原 parent、目标/策略版本、condition code ref、事件范围/起点、参数/输入/产物引用以及交付关联。claim 不为未满足等待返回任务执行。条件由外部普通代码运行，R 不猜事件名。satisfy_wait(wait_id, event_ref, successor_request)：事务保存同一匹配交付与后继，重复同一匹配不重复建立责任。
- acquire(resource_id, execution_id, base_ref)：资源独占写责任；并发只有一个成功，控制 worker 租约过期不释放该记录。release(resource_id, execution_id, stopped_ref, published_ref)：仅在配置的真实执行/文件 reference authority 核验旧执行者实际停止且保存范围对应后释放；取消请求、任意文本或错误执行 ID 不能作为证明。R 不实现 Linux 停止，也不把 token 当物理撤权。

## 状态、原子范围及故障

每个 API 仅承诺其 SQLite 事务原子；WAL+FULL、外部权威目录持久保存，成功 ACK 后 SIGKILL 重开必须保留原值。首次建库/目录同样需持久化边界。范围是进程崩溃、任务容器消失及连接断开；不宣称当前 WSL 实验验证了掉电、磁盘损坏、共享网络文件系统或多节点共识。磁盘/事务错误不得成功 ACK，原已确认记录不能默默替成空库。

R 可以同时有旧责任和新记录引用，但不可同时缺失。交付前先保存已接受身份和责任；外部结果失回执时 query/reconcile，明确不知道不等于可安全重发。保存结果后无后继仍为待决定。所有已接受决定完整版本在重启后不变，不再次跑非确定策略替代它。等待归零是 X/S/系统的实际释放门槛，R 只能在有效释放引用后确认 waiting 状态，不因表中写 waiting 就自证。

## 规模与验证范围

本组件正确性批固定 4 个控制 worker、3 个 namespace、每域 12 个唯一请求，共36项；另有4 worker竞争同一12身份，确保每身份只受理一次。每个并发批预定重复3次，保留所有错误。公平判据是同时 ready 的3域在3次连续成功领取内各得到1次，域内接受次序保持；这是所选轮转算法的功能性质，不是吞吐 SLA。SQLite 锁等待设10秒只是测试停止/死锁告警，超时判失败，不能把未运行项跳过。X 的等待驻留/活跃性能数量另在实现其负载支持前以系统协议冻结，不能用此36项外推极高并发。

真实依赖：Python sqlite3、ext4、真实子进程/SIGKILL、独立连接读原 DB 和目录对象。reference authority 测试替身仅控制合法/错误引用判定，不能证明 X/F/S 真结果；跨设施必须在各组件通过后用真实结果组合验证。数据库被管理员修改/丢失不在自动恢复承诺，但完整性校验不得默默成功。

## 可执行验证接口补充（草案，随独立审查冻结）

构造器的可配置测试/宿主参数为 request_limit_bytes=262144、transaction_timeout=10、reference_checker(ref,purpose,expected_binding)、checkpoint(label,record)。checkpoint 只供受信验证注入，不向模型暴露；在 after_commit_before_reply 等真实事务切点调用，不能先伪造ACK。每个返回对象是字典；query含 id/principal/namespace/kind/payload/phase/result_ref（可空），claim另有token/mode；query_decision返回parent_id/source_ref/harness_ref/body/applied。API异常有精确code：invalid、denied、conflict、not_found、stale、ambiguous、busy、reference_invalid、storage_error、pending_reconcile。类型/签名错误不能被测试当预期拒绝。

持久审计表 requests 至少可由独立sqlite连接读取 id,principal,namespace,kind,payload_json,phase,result_ref_json；decisions 可读 id,parent_id,source_ref_json,harness_ref_json,body_json,applied；waits 和 holders 的稳定id/关联可独立查询。它们是本版本控制表可观察约定，不面向模型，schema迁移必须保留已确认语义并复验。pending() 返回所有未结清引用（含decide/reconcile/paused/waiting）；已确认历史不能因不再pending而消失。

外部决定body固定为三种仅用于内部记录的事务参数之一：{"successors":[完整request...]}; {"wait":{id,namespace,target,harness_ref,condition_ref,start_sequence,filters,refs}}; {"stop_ref":原S完整回答或有依据停止引用}。该表不含表达式/条件语言，不定义业务成功。condition_ref指向普通代码，R不解释。apply只能实施所存原body。等待进入前还必须有本次资源release_refs，通过reference_checker核验实际释放；未核验只能pending_wait而不能waiting。satisfy_wait还需expected_condition_ref，防止恢复用新条件代码覆盖已接受旧安排。

reference_checker的expected_binding包含本次所需execution_id/resource_id/base等关联；仅判断ref.kind或引用存在不足以释放不同执行者。正式case必须有错execution/base但真实存在的ref，不能只有缺失引用。

## G3-RF-01：受控安装更新原目录对象

F 的合法 renameat2 exchange 会改变当前路径的 dev/ino，不能强制创建新resource或把正常版本安装当无意替换。新增 prepare_install(principal,request_id,resource_id,execution_id,expected_revision,base_ref,staged_ref)：在交换前持久保存原root和staged实际对象/版本、原holder、base及完整意图；无holder、错误代次/无权或不匹配base拒绝。confirm_install(request_id,installation_ref)经F reference authority原身份查询确认实际安装布局后，一个SQLite事务更新同resource root身份和revision，保留原登记/Harness/授权及安装历史。旧holder仍须经真实停止/保存依据release，不能因路径换掉自动释放。

处于pending_install时resolve为pending_reconcile，直到真实布局明确；既不盲按旧路径执行，也不将新对象当新登记。交换已完成但R未更新的恢复读取原install身份和两份目录布局，核对已保存staged/old devino及版本后确认；禁止再交换一次或删除另一份目录。没真正安装不能仅凭prepare回执改登记。与任意外部路径替换区别在先行已接受的完整安装意图和F实际证据。R19是本组件的窄关联/事务验证；跨F真实交换/崩溃窗口在F独立与G5组合用例核验。

大小限额计算对象精确定为JSON编码 {principal,id,namespace,kind,payload} 的UTF-8字节，sort_keys=True、ensure_ascii=False、separators=(comma,colon)、allow_nan=False；例如恰好4096字节的测试profile请求接受、4097拒绝。不得将base64/字符数或未含关联字段的载荷大小当整请求字节。


R16原引用负控补充：stop证明与published版本须绑定holder的resource_id/execution_id/base_ref；真实存在且字节正确但原执行或base不同仍拒绝。R14重复匹配必须同时保持原condition_ref/event_ref/完整successor，任一改变冲突，不能仅靠wait_id忽略来源关联。R18锁案例只收具体action/request_id的storage_error及观察端仍持BEGIN IMMEDIATE事实，非零退出不是判据。

同一责任的已保存result_ref完整不变：相同原ref重交幂等，另一个真实存在但不同的结果ref冲突；不能覆盖旧已确认反馈。外部决定的source_ref必须等于该责任已保存的原结果引用，harness_ref等于已受理版本，不能接受另一真实来源的首次决定。

## G3-RE-01：设施交付确认不结清策略责任

事件发布、X执行和provider传输是有限设施交付，不要求额外Harness决定才能确认它们自身。其父invocation的策略责任仍独立保存。ControlStore固定delivery_kinds={event,execution,provider_transport}；这些请求受理为accepted_delivery，不进入claim的invocation就绪队列。pending仍包括它们，共享恢复可发现原身份。其余控制请求仍遵守save_result→decide→外部决定交接，不能绕过。

mark_dispatched(principal,id,delivery_owner)只有runtime角色可调用，原kind必须匹配owner（E/X/provider），事务将accepted_delivery变issued后返回{fresh:true,mode:execute}；对已issued/confirmed重交返回fresh:false以及原关系，不能授权第二次作用。进入issued先于对外请求；中间崩溃的保守未知保留核对责任。它不提供发送恰好一次保证。confirm_delivery(principal,id,receipt_ref)只确认本条设施受理关系，须reference authority核对原request_id/namespace/source及完整设施绑定；重复同ref幂等，不同ref冲突。原invocation的result/decide/后继一概不变。不得用于普通invocation或probe来伪造完成。

query返回accepted_delivery/issued/confirmed与原receipt_ref，失回执按原身份查询设施；不能查到时为未决，保留静态记录。R不复制event正文或wire模型语义历史。真正NATS/执行/provider的保存范围由E/X/S确认，本组件用显式reference authority夹具检验关联，真实交付在对应组件与G5验。

R06新invocation必须按当前resource修订/harness版本明确绑定，提交旧harness但声称新revision报stale；原已受理完整重交按原身份查询，不能在同ID重交时改成新版本。公平用例验证全部12轮三域领取，不仅首轮。R15将真实holder与同责任租约100→131接管放在同一轨迹；R16同时验证stop与published的真实错exec/base引用。R05执行用户字段不属于resolve接口，payload伪造principal/user/origin由R03来源校验拒绝，实际user/环境执行边界由X正式case覆盖。

## G3-RE-02：明确回执结果与重试身份（R20修订）

R的confirmed严格表示“本条设施调用的原权威回执已持久核对”，不表示正效果、消息已存或业务成功。receipt_ref必须由真实设施所有者给出完整原request_id/namespace/source/delivery_owner/request_digest关联，outcome为positive或negative。request_digest是原受理完整{principal,id,namespace,kind,payload}确定JSON UTF8的SHA256。positive表示设施声明的正回执，negative只允许明确definite=true的服务端拒绝/明确未实施回执。reference_checker仍必须核原字节及完整关联；R不推断NATS状态或读取事件正文。unknown/断线/超时/仅没查到结果不能写作negative；即使该unknown观察本身真实存在，也不是可confirm_delivery的确定回执。

正/负回执皆同ID相同完整ref幂等、任一关联或ref变化冲突；重新打开仍是原结果。父invocation的result/decide/后继保持不变。E对外CONFIRMED仍只表示NATS正PubAck/原消息查询证实已存；服务端明确negative对应用是REJECTED，须同时说明Runtime先前已接受而设施拒绝，不能复用R的confirmed字段作为消息成功。

已确认negative的原请求再次mark_dispatched仍fresh=false，不允许同ID第二次作用。以后确需重试，由外部已授权普通代码显式accept一个新ID的设施attempt，payload.retry_of={request_id,receipt_ref}关联旧negative；R核原请求same principal/namespace/kind、原phase=confirmed、原receipt_ref完整相同且definite negative。新请求仍完整绑定并获得自身首次dispatch，旧negative不可覆盖/删除。issued/unknown、缺失或伪造negative不能经retry_of绕过核对责任；R不自动创建重试、不判断业务是否应重试。这只是显式attempt关系校验，不允许靠不同ID躲开未知原作用。

## G3-RE-03：E固定输入的唯一控制关联（R21）

新增窄接口bind_input(principal,invocation_id,binding,input_ref)与query_input(principal,invocation_id)。只保存控制关联，不复制events正文、不生成H或过滤结果、不写E输入文件。原accept请求的payload.input_binding先固定完整selector：{namespace,source,start_sequence,filters,page_size,surface_ref,previous_session_ref,execution_targets}；source为原受理principal，namespace为原请求namespace。target/Surface/Session均不可变权威ref，未有前序Session时显式null。page_size是有限正整数，filters和目标列表使用原确定JSON；全部受原大小/授权检查约束。

binding必须逐字段等于原已接受selector。bind_input只允许拥有该namespace且具runtime角色的受信服务；模型载荷不得指定更高principal。input_ref={owner:"E",kind:"input",id:invocation_id,path,root:{dev,ino},manifest_sha256}固定权威普通目录及完整manifest原字节。E已保存四个文件与完整manifest后，reference_checker(input_ref,"input",expected_binding)检查原invocation/selector、真实目录身份和manifest/四文件原字节；R成功返回在本地事务提交之后。同完整binding/ref重复返回原关联；任一字段/ref变更conflict，未知invocation not_found，无权denied，原件缺失/损坏/来源不符reference_invalid，不能把缺件记为空输入或删原关联。

H/end/next_sequence、纳入的event_refs、文件长度/hash和完整范围事实由E原manifest唯一持有。R通过manifest_sha256及原selector固定该结果，不重抓H或存另一套可变范围真相。query_input校验当前调用者原namespace读取权限，并限制为原受理principal或该namespace的受信runtime/admin；另一个仅submit的同namespace用户不能读取原输入，并经authority重验原ref；缺失显式报错，原SQLite关联仍保留供E按原manifest恢复。查询返回{invocation_id,binding,input_ref}，不改变原request payload、模型结果或推进责任。

仅对kind=invocation且明确声明input_binding的请求，claim的执行资格要求已存在有效原input关联；绑定前不交给Harness执行，pending仍返回该已接受责任及原selector，供共享E准备入口按原ID继续。不存在input_binding的invocation、原普通probe和其他明确请求保持既有资格规则；不把所有请求隐式改成需要E输入。不增加业务终态；bind成功只是满足既有调用输入前提，不结清调用。R21采用真实登记+此invocation路径验证；E无完整Runtime也可构造这一最小边界。

独立SQL观察约定新增inputs表：invocation_id唯一主键、binding_json、input_ref_json；原requests.payload_json保持不变。R21在当前21个unit内含全新进程query_input/原DB独立读取；原23个进程伴随场景不删减。真实E/NATS文件生成和跨X只读挂载仍属E/S/X及G5。

RE-03参数精确补充：reference_checker在purpose="input"时expected_binding为{invocation_id,binding}，不得省略而只检查目录hash。query_input对已授权存在但尚未绑定的invocation返回None；未知invocation为not_found，已绑定但原件缺失为reference_invalid，三者不混用。accept时显式selector的source/namespace与原principal/namespace矛盾报denied。

## G3-RF-02：不可变 RestorePlan 与回退事实（R22）

`accept(principal,{id,namespace,kind:"restore_plan",payload:plan})`复用原完整受理事务、after_commit_before_reply切点与query。仅有原namespace的admin/runtime可以提出恢复；提交者身份/namespace沿用受信调用，不由plan授予。两个登记资源均重验当前revision、实际root及相应授权：restore需write，keep需read。该内部kind不入普通Harness claim；accepted计划在pending可发现，原ID/完整请求保留。重复完整相同幂等，任一关联改动conflict。它不执行F/S/E/X、模型或补偿，不把计划受理当文件已安装。

plan严格含以下字段，缺域/缺字段invalid；所有ref均不可变且可由原所有者验证。两域resource不同且domain对应实际登记，不接受含糊字符串current；keep明确选择当时base版本。

```json
{
  "schema": "lore-restore-plan/v1",
  "domains": {
    "surface": {"action":"restore|keep","resource_id":"...","binding_revision":1,"base_ref":{},"version_ref":{},"installation":{"request_id":"...","execution_id":"...","generation":"..."}},
    "workspace": {"action":"restore|keep","resource_id":"...","binding_revision":1,"base_ref":{},"version_ref":{},"installation":null}
  },
  "session": {"session_ref":{},"operation_id":"...","boundary":"...","source_result_ref":{}},
  "event_cursor": {"namespace":"...","start_sequence":1,"source_ref":{}},
  "pending_refs": [{"owner":"R","id":"..."}],
  "effect_refs": [],
  "harness_ref": {},
  "environment_ref": {}
}
```

restore条目必须有唯一installation ID/execution ID/generation；keep条目installation必须null且version_ref严格等于base_ref，不安装/回退该域，至少一个域restore。base_ref是接受时已固定的原当前版本，version_ref是所选目标历史版本；它们的resource/domain与原条目对应。Session boundary必须是原S实际continuation引用能证明的边界；事件起点是本恢复计划明确选择的读取位置，不删除NATS历史。pending_refs可为空但不得含未知/重复R责任ID，effect_refs明确保存已知原效果引用；当前计划不改变这些原记录或把其已发生效果归零。语义上的引用集合完整性由控制调用从受影响原R/S/E/X事实构造，并在M06独立对照；R不自造或复制局部历史来推测所有外部效果。

受理时reference_checker对每个文件base/version用purpose="restore_version"、expected={resource_id,domain}核原件；对session_ref用"restore_session"、expected={operation_id,boundary,source_result_ref}；对event source_ref用"restore_events"、expected={namespace,start_sequence}；对effect_ref用"restore_effect"、expected={namespace}；environment用"environment"、Harness用原"harness"。实际引用缺失/不符reference_invalid，结构invalid，无权denied，原资源修订/根替换stale。真实引用有效但首次原域/边界关联不同也须拒绝，不能只检查引用存在。原已受理计划的查询不因后续F安装改变base而变成新计划；新动作仍重验当下权限和实际资源。

既有`prepare_install(..., staged_ref, restore_plan_id=None)`只加此可选keyword。restore_plan_id存在时，必须先有已受理原restore_plan；本install request_id准确对应其中一个restore条目，resource/revision/base/execution严格等于该条。keep域、另一计划的ID、遗漏计划或关联不同均拒绝。有关restore_plan_id的expected关系包含：{restore_plan_id,request_id,resource_id,domain,execution_id,generation,base_ref,version_ref}。该完整关系与staged根(dev,ino)及原停止引用持久存入原安装意图；install request_id不能被另一个计划复用。

restore专用staged_ref在原F staged/root结构上包含resource_id/domain/execution_id/generation/base_ref/version_ref/stopped_ref；reference_checker(staged_ref,"staged",expected关系)要核真实原F对象，另对stopped_ref用"stopped"核{resource_id,execution_id,generation,base_ref}。holder必须原resource/execution/base匹配，不能声称holder本来含generation；generation来自原计划和实际X停止/F导出安装关联。未实际停写或不同generation引用即使真实存在也reference_invalid。普通非恢复安装沿用RF-01，不受这组新增字段强迫改变。

`confirm_install(request_id,installation_ref)`仍只读取原安装意图。恢复关联要求F原安装收据同时含上述expected关系、原stopped_ref、实际current/retired对象和目标version_ref；reference authority核原已落布局及这些完整关联，元数据自报不构成真实安装。相同收据幂等，另一真实收据conflict；错误resource/base/execution/generation/plan/版本reference_invalid，不能把另一条安装抵充。确认事务同时保留该安装的restore_plan_id关联，并派生该计划的记录进度；不执行任何目录交换。

`query(principal,plan_id)`保留原完整请求，并附`restore={installations:{domain:installation_ref},remaining_install_ids:[...],kept:{domain:version_ref}}`。仅已有实际有效F安装确认的restore域进入installations；keep从原plan固定读取，不要求安装也不假称安装。剩余非空时phase仍accepted且pending；全部restore条目实际收据齐时phase=confirmed，不再pending。这里confirmed只表示计划列出的文件安装回执与R绑定已逐项核对，不能对外说整个业务完成或多域原子；不同域实际先后及全部原收据可追查。部分成功后失败/重启，已确认域不重装，缺的仍原ID待核对，原计划、Session、event、效果和未决责任都不删除。

独立SQL继续读取requests原完整payload及phase；既有installations表需可读request_id、restore_plan_id、installation_ref_json（未确认null）。无需新通用恢复状态机。R22固定两域恢复部分/全齐、分别keep域完整声明、真实错误引用/越权/冲突、after_commit_before_reply实际SIGKILL、新进程query和部分安装后重启；F真实原子交换、跨组件停止/授权/历史集合完整性及M06回退动作查验仍须组合层独立运行。

RF02错误码精确化：未知restore_plan_id为not_found；省略已被原plan预留的install关联、复用另一plan安装ID或调用参数与原条目不一致为conflict；keep域要求安装或无任何restore域为invalid；原staged/stop/installation实际引用与本次预期关联不符为reference_invalid。restore专用staged引用含原restore_plan_id/request_id关联，可由可信authority结合原F materialize材料与X stopped事实核对；F不凭这组调用元数据自证停止。query的installations/kept以域名为key，remaining_install_ids按surface、workspace固定顺序返回。


## 独立失败驱动的 RW/RA 增量

[原引用关联与等待屏障增量合同](wait-reference-supplement.md)经根确认，先于对应修复冻结。其明确的authority上下文、等待barriers及busy后原apply接续规则优先于上文旧pending_wait简述；原完整正文和旧fixture保存在history/wait-reference-001，不追溯修改旧失败。
