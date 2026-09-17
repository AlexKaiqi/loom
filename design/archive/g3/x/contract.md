# X v1：双域 Linux 执行契约

状态：G3_REVIEW_DRAFT。只定义组件合同、独立用例及可运行验证环境；没有 X 生产实现。来源为 v5 §4.1/4.2/5.3/6.4、G1 §3/4/6/7、G2 已验机制和原 244 项映射。当前 Linux Docker 28.0.1/API1.48、固定 Python 镜像/显式 seccomp 的范围见 environment.json。X 不实现 Harness Loop、不生成 Runtime 业务终态、不持模型凭据。

## 1. 所有者、信任和依赖

R 是登记、授权、稳定受理及写入协调责任所有者；F 持有原生权威目录、版本、引用与发布；X 持有实际环境/命令执行、Engine 身份、原始输出与冻结/停止事实。S 仍持有原 Session；X 导出其原 JSONL 是字节检查点，不是第二套模型历史。X 的少量稳定执行关联是弥补 Docker exec 不提供持久调用去重/输出重读的适配，不复制 S 的历史。

不可信对象包括任务/Shell、子进程、模型文本、Surface 文件、环境变量声明、别名链接、普通资源耗尽与网络越权。可信基础为控制侧 R/X/F、固定 exporter/keeper、Docker daemon、Linux 内核和管理员；不能把同 UID 本机开发者视为安全隔离。任务身份没有 Engine API、宿主 PID 命名空间、control DB、模型 key、任意宿主目录或控制 fd。

实现候选是 Python 标准库 + 既有 Docker CLI/Engine Unix API。CLI 启动子进程必须固定 argv、白名单 env、close_fds；不得 shell=True 拼控制指令。Engine exec create 的真实 ID 必须在 start 前持久保存；任务脚本只进入已确认环境内部的普通 Shell/Python。

## 2. 内部接口与完整绑定

以下是供 R/S/F 适配的普通库方法，不是模型可见命令或 DSL。验证入口以同名 JSON 请求驱动组件，真实实现可保持库接口。

| 方法 | 输入 | 输出/效力 |
|---|---|---|
| execute | request + 独立可信 authority | 拒绝，或原 execution_id 的受理/查询结果；重试不另发效果 |
| query | execution_id + authority | 原记录、对应实际 Engine 状态及结果引用；没有创建/重做副作用 |
| restore | 新完整request + 显式source_ref + 新object_generation + authority | 从所选不可变快照准备新环境与CREATED exec，绝不自动启动旧/新命令；需后续显式dispatch |
| request_stop | execution_id、object_generation、稳定 stop_id | 只确认已保存停止请求；之后实际停止另报 |
| checkpoint | execution_id、generation、稳定 checkpoint_id、purpose | 同一对象实际冻结并导出，返回待外部 barrier 的 prepared_artifact；不能用于接管 |
| resume | 原对象+冻结代+已经保存的 checkpoint receipt | 只恢复同一实际对象；旧/失效 receipt 拒绝 |
| seal | 原对象+冻结代+已保存 prepared_artifact receipt | 杀停/回收并核对同一对象的剩余写能力，返回 stopped proof；不是 F 发布 |
| release | execution_id + 已确认输出/文件/交接引用 | 清理已保存对象及 helper；仍被承诺引用的结果不删除 |

request 至少绑定 schema_version、设施生成的 execution_id、caller/invocation/Step/source_result/Harness version、target_id、target binding generation、单一 domain、F base version/manifest、脚本原字节或不可变 blob digest+size、stdin/input references、cwd 相对位置、环境/依赖 image/version、只读输入 manifest、端点/网络策略及全部资源预算。权限来源 authority 单独传入，模型/user 字段不能创建它；不得从正文导出 UID、caps 或管理能力。相同 ID 的规范化完整内容完全一致才返回原关系，任何字段冲突都拒绝并保留原记录/实际对象。内容摘要必须由实际字节计算且指向可取回内容，不用可变路径代替。

authority 明确 namespace、调用主体、可查询对象、获准 target/父工作位置、绑定 generation、写协调 token 和配置上限；由 R 控制调用建立。测试中 authority 由独立 fixture 提供，仅测试 X 如何落实，不据此宣称 R 授权已通过。任意跨域/跨对象/过期能力均拒绝。

execute 不接受请求正文中的任意 image、uid、mount、network 或 limits 扩权；请求只是引用已获准 profile/预算。未知字段要显式拒绝，不能被转发为 Docker flags。target_selector 可以显式 target_id + 环境内 location；只有 location 时须在允许目标中唯一且实际对象匹配。真实父目录授权可用于其中新建普通子目录，未登记且无获准父级的路径仍拒绝。

## 3. 状态、原 ID 查询与故障

执行事实状态：NOT_STARTED、CREATED、RUNNING、FROZEN、STOPPED、UNKNOWN；stop_requested 为独立请求字段。输出/结果状态独立：PENDING、COMPLETE、INCOMPLETE_LIMIT、INCOMPLETE_OBSERVATION、UNKNOWN。保存了 cancel request 不得改成 STOPPED；Engine 退出码非零不撤销已经发生的文件修改。FROZEN 仍有未来可恢复的旧写能力，不得签发接管许可。

关联保存 execution_id → request_digest → container_id/private_volume_id/object_generation/Engine exec_id。每个新物理对象有不可重用 generation；同名路径、Docker name/label 不是对象身份。记录入外部持久设施之后才能 start；恢复 query 同一 Engine ID，检查实际配置和绑定。重复对象、关联冲突、Engine 不可达或启动回执丢失无法判定均保留 UNKNOWN/暂停，不猜未执行或发新 ID。

Docker ExecInspect 只给执行状态，不能重新读完整 exec stdout。观察进程崩溃后，已确认的外部输出 blob 仍须按原引用读取；尚未确认的缺失输出保持 INCOMPLETE_OBSERVATION，即使已知进程退出也不能填造完整成功。明确记录已知 exit/部分效果，不把中断解释为无效果。不为“恢复输出”自造另一套 exec loop。

COMPLETE 结果须：实际执行身份/退出原因可核对、stdout/stderr 全量 EOF、原字节 blob 与 manifest 外部持久保存及 barrier 完成。确认后的 blob、状态与引用在保留期内不得因进程/容器/文件回退丢失。保留期由仍被 R/S/F 责任引用的可达集合控制，不以任意短 TTL 删除活跃恢复依据。

## 4. 真实双域与私有普通文件

Runtime Shell 只能写当前获准 Surface/辅助临时副本；Task Shell 只能写获准 Workspace/输出/依赖副本。每次执行先固定一个域，脚本 cd、同名路径、user=root 文本和前缀都不改变它。权限/别名/绑定的核验发生在任何进程 start 之前；验证后对象变化要拒绝/重查，不使用失效路径。不存在宿主 fallback。

所选写入候选为每代私有 local-driver tmpfs named volume，强制字节与 inode 上限。任务没有宿主权威目录 RW bind；输入/固定代码可只读映射精确获准对象，禁止把 home 父目录或 Engine/socket/control 文件带入。所有可写临时、HOME/cache/依赖安装、/tmp 与 /dev/shm 都列入 profile；根镜像 readonly，环境内安装落私有目录，不以 root 全局包安装绕开预算。未来其它有总配额的成熟后端可替换，但必须重新核验相同合同。

普通命令自然返回不应销毁唯一 tmpfs 持有者。参考生命周期：固定无密钥 keeper 为 UID0/cap-drop ALL 的 PID1；实际任务为 UID1000/cap-drop ALL 的 Engine exec，且 no-new-privileges。任务不能 kill/ptrace/读取 keeper 私有 fd 或提升为其身份；keeper 不能 import/eval 用户数据。它只是短时容器存活锚点，不承担 Harness 推进或长程等待。实际文件保存后 keeper/全部 task/helper 都释放。

当前 WSL tmpfs 对 user xattr 返回 ENOTSUP。导入前必须按 F metadata profile 判断；含不支持但需要恢复的属性、类型或所有权时明确 UNSUPPORTED，不运行后剥落属性再发布。F 宿主可支持更完整 metadata，不得从 X 子集反向缩 F 原范围。ACL 未由当前探针证明；在需 ACL 的实际输入被接受前必须实测支持，否则拒绝。拒绝特殊 FIFO/socket/device 与非法 archive 不是静默漏文件。

## 5. 冻结、导出与交接

checkpoint 的独立事实必须关联 container 完整 ID、同一实际 volume Name/Source/Driver、object generation、freeze generation、F base/resource/binding、完整归档 digest/size/member manifest 与命令输入版本。可信侧执行 Docker pause 并核全 namespace 冻结，然后临时 exporter 只读挂载同一 volume。直接 docker cp(tmpfs) 已实测 rc0 却只导出空目录，禁止作为该 profile 的完整导出实现。

exporter 可为固定 UID0，仅 DAC_OVERRIDE，用于读取任务 chmod000 的必需文件；私有卷仍真实 readonly，无 host PID、外部写挂载、network/keys/Engine端点，全部资源计数。它只能运行固定扫描/归档代码，不能执行归档文件名或用户文件。输出 tar 保留 ordinary bytes/空目录/软硬链接/mode/uid/gid/mtime_ns；mtime 读取 PAX 十进制字符串，不经 float。软链接本身是数据，绝不跟随它取得未授权内容；hardlink 必须安全指向已知树内 regular。异常、未支持元数据、遗漏 mode000、重复成员、路径穿越、header 大小不符、exporter 非零、输出超限或缺 EOF 均不能出完整版本。

整个归档必须在外部流式限额与 manifest 校验后保存，再确认 checkpoint barrier。单个 sparse 文件巨大逻辑长度也计入导出/展开预算；不能因为 tmpfs 已分配 blocks 很小就展开到 host 填盘。对 FIFO/socket/device 不读流，拒绝确认。archive 不可以作为未校验任意宿主路径解包。

S 的中间 checkpoint 保存原 Session 前缀后可 resume 同一对象；这不撤权，不允许 F 发布写者交接。F 的最终路径需要先保存导出、seal 实际停止旧对象，确认整个 namespace/旧 FD 写能力消失，再将停止事实交给 F。F 还须核原 resource_id/domain/binding_generation/base_version 和 R 写协调 token，拒绝期间人工编辑/变绑定，才能发布。pause 不能冻结外部人工写者。

异常导出时保持原对象冻结/待处理，不能先 kill 再伪造保存成功；安全预算已耗尽必须强制终止时，记录具体原因与未确认修改丢失，不冒充已确认版本丢失被豁免。旧 lease 到期、观察连接断开、主 Shell 退出、F rename/exchange 都不是本对象 stopped proof。

## 6. 总资源、输出及正式数值

必须由实际 Linux/Engine 约束：memory 与 memory-swap、pids、CPU 配额、时长、volume 总分配字节/inode、tmp/shm、stdout/stderr 原字节与 exporter 归档/展开上限。helper 与 keeper 计入并发和总内存/CPU预算；R/X 要预留导出 helper 槽位，不能把预算全分给等待导出的任务形成无法 checkpoint 的死锁。超限不升级 mount/caps/用户或开放网络。

任务 Engine 日志禁用，不能让日志旁路填满 daemon disk。可信观察者流式持久保存 stdout/stderr，执行总计及每流均有限额；输入完整性/原字节大小也先验限制。到预算边界暂停/停止，保存已接收前缀的 size/hash，明确 INCOMPLETE_LIMIT 与停止原因，禁止将它当有完整来源的正常裁剪。只有完整 EOF 的输出能标 COMPLETE。未观察到的 pipe/daemon 缓冲不伪造；资源超限停止允许保留未确认输出缺口，不能抹掉已确认字节。

正式 fixture 不是容量/SLA 用户承诺。参数化样本使用 volume 2MiB 与 6MiB、inode64与128、memory128MiB、pids32、CPU0.25/0.5、stdout/stderr各64KiB与总96KiB、导出 raw/logical 各8MiB/12MiB、普通 fixture 单任务最长20秒，资源/时长故障为8秒（003实测collector三阶段约6秒，据此在正式执行前预留独立采样窗口）；独立单次调用10秒截止、整例120秒硬截止。通过依据是配置对应真实拒绝/节流/停止，成功文件数或吞吐不取自探索结果。恢复故障每个指定边界各1次受控kill；关键旧写者与配额机制各3次固定样本复验，不外推概率可靠性。每批最多2容器/合计256MiB，helper包含其中；需要更高并发的系统价值案例留G5另有预算，不能在本批偷偷增加。等待零资源由R/S/X组合另验，X单独验证release后本次ID的所有物理对象消失而静态结果仍可查。

## 7. 独立验证接口与分工

`cases.json` 为先行正式清单，明确 action/观察/oracle/known-bad。被测目标只能接收 request/context/fixture资源，不获得 expected。validation/components/x/oracle.py 不读取组件自报 passed 或 checks 作为事实；准备探针从实际 tar/raw Engine/命令文件及原字节裁定，相关 bad/missing 输入必须拒绝。实际组件入口缺失时 runner 必须非零 UNIMPLEMENTED，不能因已有探针通过而全绿。

正式G4执行器/查询/权限/输出关联须用真实Engine和物理对象；仅R/F授权token与已保存版本供给可用明确fixture，不能把fixture的stopped=true替真实撤权。结构审查检查无host fallback、无传递key/Engine句柄、无shell拼接控制命令、接受前完整绑定、stderr/异常不能吞掉，以及原保存事实不因回退被清除。已知错误通过相同独立观察路径反驳。

## 8. 可信双向流与测试驱动

S 需要真实交互式 stdin/stdout。可信库 execute(request, authority, io_mode='duplex') 返回原执行绑定和 ExecutionChannel：write_stdin(bytes)、close_stdin()、read_stdout()/read_stderr()。句柄仅可信 S bridge/控制观察者持有；不下发给模型或其他任务。任务只拥有自身标准 fd，不能从通道取得 Engine 句柄。读写必须持续受每流/总量/时长限额约束；暂停时仍可排空已在可信管道的字节，不能因未排空形成无界缓存或把 EOF 猜出来。暂停期间不向任务交付新响应，resume 后继续同一 Engine exec 的管道。静态 stdin 和轮询临时文件不能冒充双向通道。

G3 测试适配器 argv 由 --component 显式给出，为长存活 JSONL 控制进程（产品仍可普通库）；stdin 每行 {request_id, method, arguments}，stdout 一行关联响应 {request_id,binding,result,artifacts,error}。控制日志写 stderr。测试方法 channel_write/read/close_stdin 仅传 base64 原字节。根 V 不要求模型理解此测试协议。run.py 已预写动作、故障边界、外部采集及判据，不接收目标的 passed/checks 作为观察事实。实际目标缺失非零。

测试 adapter 只可在明确 test_context 中暴露 after_exec_created_before_start、after_start_before_receipt、after_effect_before_output_barrier；发 {test_barrier,binding} 后等待，由外部 driver 保存真实 Engine 观察并 kill 整个 adapter 进程组。重启沿用相同受控 state_dir。此类 barrier 不给任务权限、不做故障后的理想状态替身。await_exit 为有界测试等待，resume_dispatch 仅允许已有且明确未 start 的原 exec；query 自身从不隐式 dispatch。

测试对象必须给实际 container 与 volume 设置 lore.x.execution_id=受理ID，以供限定清理；标签仅用于本批归属，不代替完整ID/实际绑定。独立collector拒绝将本批开始前的对象冒认为新执行，记录本批新增对象。测试并行外部对象变动会造成不可确认，不静默忽略；清理仍只删除带本fixture确切标签的对象与观察器亲自创建的helper/peer，绝不按全Engine差集删除其他对象。

本首个执行适配与验收输入明确 interpreter_argv（普通 argv，例如 python -c 或 /bin/sh -c）与 script_base64，均纳入完整绑定。标准测试路径由 Engine 直接exec该解释器加原脚本，observer核 ExecInspect 的实际完整 argv；脚本文本摘要自报不能代替交付证据。若以后增加可信外层 collector wrapper，先修订独立原脚本交付/执行证据，不能保留原适配通过结论冒充新路径。归档内任务JSON保存在 observer结果的独立 json 字段，绝不覆盖 observer计算的原文件hash/size/mode等事实。

## 恢复补件001：所选原版本、新环境与原执行分离

原X024只在可变输入变动后要求恢复拒绝，不足以证明恢复可用。根已将原X门槛局部失效并保留history/rebuild-001；新增X028正例及X024明确坏源负例在产品前独立冻结。

恢复依据是调用方显式选择的不可变完整source_ref，不能从“当前目录看起来相似”推断。首个正式恢复路线选择已确认X checkpoint，包含owner/source_execution_id/source_object_generation/freeze_generation、原input_manifest、metadata_profile、原source_binding及archive_ref(path/sha256/size)。它包含任务修改、未跟踪依赖和环境配置；不是只取Git跟踪文件。调用方也可先把明确初始F版本物化为同profile的完整受保留快照，不能混用旧输入与新输出。所选快照足够且有效时，原宿主live输入目录改变不影响该版本的可恢复性；仍需要但未包含/不可达的依赖原引用必须明确拒绝，不能以最新路径替代。

restore绑定新execution_id、新object_generation和新完整request，重新核authority、域、元数据/字节/inode预算。只创建有界新私有副本、keeper以及未start的CREATED Engine exec；新命令只在额外显式resume_dispatch后运行。恢复是新物理对象，绝不重用旧container/volume/exec/generation，也不触发旧脚本、旧未知效果或新的模型调用。原exec及其已确认result/输出blob保持可查询原内容；query.result完成态信封为不可变原结果，当前物理观察另列，不能放每次变化的查询时间污染原结果。

独立driver读取候选真实checkpoint archive，逐成员同外部只读volume归档比对，并在自身受保留version store fsync原字节/引用后再seal。prepared归档及restore引用不能由目标自报manifest取代实际数据。测试cache明确为LORE_X_CACHE_DIR，与LORE_X_STATE_DIR权威原记录分开；冷启动前driver实际清空cache，杀停adapter，确认旧namespace/volume已消失。实现不能把缓存藏在其它目录躲过冷恢复验证；已声明保留的权威版本副本不称缓存。坏源试验实际隔离已登记的原archive副本并删除/改坏所选retained实体，保留观察副本；原exec记录和stdout/stderr不删除。不能在所选版本字节不成立时把可变live路径或未登记副本当恢复成功。

source复建完成后先由外部collector读整个新副本，与原member类型/bytes/hash/mode/uid/gid/mtime_ns一致；只执行新获准的只读核查脚本，原effect计数仍一。原作者及根的旧设施探针/26项校准仍只证明原范围，不为新增恢复case提供产品通过。预算继续每批2容器/256MiB，旧对象释放之后才创建新一代。

这里resume_dispatch沿用原X009已有的测试包装：对已核实CREATED且从未start的同一完整新request，显式调用execute/dispatch；并非新增模型命令或必须公开的产品API。resume只解除原对象冻结，不能启动命令。UNKNOWN或可能已start不得通过此包装盲重发。负例在adapter已停止时破坏所选registered源并清cache，然后冷重启，避免adapter先把待毁损源预读入内存使故障位置不真实。

namespace inode/PID为观察时的内核事实，销毁后可能复用，不能要求永久不同来替代新身份。X028先确认旧namespace无进程，再以新的完整container/volume/exec和严格递增generation定位新namespace；核新keeper实际存在、显式只读核查命令运行时UID1000/cap0。新旧namespace inode恰巧复用不构成原执行被重用，旧exec结果身份仍必须不变。

恢复测试adapter具体归档交付：checkpoint响应artifacts.checkpoint={path,sha256,size}指向本fixture state_dir内实际受保留tar；binding含原execution/container/exec/volume/object_generation/freeze_generation。测试调用方独立校验并保存到外部retained source_ref（无任务写权限）。restore参数source_ref及object_generation与完整request/authority同时绑定；不得以response中的checks或passed代替它们的实际字节/物理事实。
