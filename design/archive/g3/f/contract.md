# F：普通目录、受管理版本与引用契约（草案2，G3）

F 不实现文件系统、内容 CRUD 或新的用户命令。Surface/Workspace 仍由获授权 Shell/编辑器直接操作普通目录；R 管登记、授权、协调与已接受恢复/发布责任，X 管真实执行身份、停止和稳定导出，S/E 保存自身原始事实。F 只验证受管理集合、保留版本、提供有授权的历史内容与准备/安装普通目录。

来源：v5 §3、§4.1、§5.2、§5.3、§6.2/6.4、§7.2；G1 top-level-contracts §2/6/7；G2 synthesis F、git-files及独立GF-R01。正式用例覆盖映射另列。当前不包含生产F；通过G3只允许进入对应独立实现。

## 边界与普通编辑

登记资源包含 resource_id、domain(surface/workspace)、R binding_generation、当前规范位置和真实根对象(dev,ino)、获准主体；路径只是位置，不是权限。创建未登记目录仍只需获授权父位置上的普通mkdir/编辑，再经R接入，不要求.git。移动/替换根、绑定或权限变化必须使旧登记失效或完成显式协调更新。

R.acquire(resource_id, original_exec_id, base_ref)提供资源级排他协调。人工编辑可以在同一协调范围内用普通编辑器；不要求每次写文件调用F。只认可协调控制的写者静止/停止边界。未知旧写能力时不捕获/发布确认。

宿主不受协调的编辑不能被generation掩盖：候选以真实全集合与base比对、根对象核验及捕获/发布窗口的既有Linux变化监测共同拒绝未确认状态。仅两遍hash不证明任意并发一致；inotify本身也不能充分观测mmap写。设施批facilities-001已验证当前ext4上的read lease拒绝旧写FD和仍存活writable mmap；具体确认算法和正式反例见下节，探针不等于组件已实现。

## 受管理集合与元数据

每资源选择明确完整的受管理根，递归包括未跟踪、被.gitignore忽略、隐藏文件、用户.git及.gitattributes本身；不得让Git ignore/clean-smudge/export-ignore/hooks决定集合或执行用户过滤器。不默默跳过读失败。目录之外的引用内容不是通过跟随symlink自动纳管。

候选保留范围：普通文件原字节、目录（含空目录）、symlink目标字节和hardlink关系；POSIX路径名按原字节标识；文件/目录的mode所有许可/特殊位、mtime纳秒、原uid/gid、user xattrs与POSIX ACL（当前ext4+GNU pax tar设施已实测；逐环境能力profile仍须核验）。inode数值、atime、ctime、birthtime不作为可重建值；hardlink同一性是树内关系而非旧inode编号。稀疏分配不等于逻辑字节；是否保留hole布局不是初始恢复承诺，但逻辑字节与资源限额均不可省略。

所有权在归档中保留原身份数值；跨执行环境的身份映射由X/R明确指定并验证，F不得悄悄normalize权限/owner。当前同机验证用恒等映射。不可读对象、未知metadata、超出受支持身份映射或设施不能保真的状态显式UNSUPPORTED/UNREADABLE，不能确认丢失后版本。FIFO/socket/device及未知security/trusted属性默认拒绝；支持范围和必要失败用例须在探针后冻结，不将拒绝记为已恢复。

symlink是数据：捕获/清单/历史读取不跟随；历史API可返回链接目标或拒绝将其当普通内容，不能借此读取另一资源。恢复只对新建、受控、身份已核验的staging目录；先完整验证归档成员，拒绝绝对路径、..、冲突/重复路径、通过先前链接落地的子成员、越界或未定义hardlink目标，拒绝设备与超预算。host控制目录不作为extract目标。

## 内部操作与结果

这些是组件调用语义，不是模型DSL；最终Python函数签名可按同义窄接口实现。

| 操作 | 必需输入 | 输出/确认边界 |
| --- | --- | --- |
| inspect_scope | R授权资源、根对象/代次、受管理profile、预算 | 实际完整集合与精确错误；不写业务内容、不授予权限 |
| prepare_version | 协调token、base_ref与实际base集合、稳定source/export对象、original_exec/generation、必要执行引用、profile/预算 | 不可变PreparedVersion（归档摘要、成员描述、来源、base、域）；还不是当前版本发布 |
| publish_version | 原PreparedVersion、R已接受发布身份、原exec/generation真实stop依据、当前授权/代次与base实际集合 | 既有Git rooted版本可查询，R发布对账材料；只有所需持久保存+安装/绑定核对后才返回CONFIRMED |
| materialize | 授权(version,resource,domain,path范围)、不可变版本、合法目标对象/身份映射、预算 | 新普通目录或显式错误；不跟随不可信归档路径，不就地覆盖控制目录 |
| resolve_reference | 当前R授权+原resource/domain/version/content path与预期类型/digest | 对应版本的真实字节/类型、可交X的只读来源；无权/丢失/损坏不伪装空内容 |
| retain/release | R对仍被接受责任引用的保留关系，授权释放依据 | Git可达根保留；不可在仍有pin时按TTL/清理建议删除 |

Version至少绑定resource/domain、不可变Git对象引用、归档SHA256、profile与成员范围、必要来源/base/execution引用。历史引用不能只有可变目录名。系统控制/授权、Session、事件、外部效果记录不进入可随Surface/Workspace回退的归档。

R负责稳定发布/恢复请求身份及完整内容冲突。F同一请求查原Prepared/Published结果，不生成新身份逃避未确认结果。若Git对象已存而R回执丢失，按原身份和不可变对象核对；没有确切未发生依据不得重复安装。

## X导出与R发布衔接

X可用普通私有工作副本，F不规定零复制或Docker cp。prepare输入来自X固定generation：任务只写有界私有目录；X冻结实际写者后经既有copy/archive设施导出，返回prepared产物和冻结依据。pause不证明宿主人工编辑被冻住。kill后tmpfs会丢，先保存成功再停止；未确认临时修改丢失必须标明partial/unsaved，不能偷换为已确认版本恢复。

F不能凭freeze标志发布：先确认原exec/generation停止/失去当前资源写能力，再核验X导出完整性、R资源授权与base实际集合不变。X原对象不明、代次错配、导出不完整或宿主base变化均拒绝发布；旧确认版本保持可查。

恢复组合由已接受RestorePlan明确：选中的Surface/Workspace版本（不恢复的域也明确current）、Harness/模板版本、输入起点、Session/执行引用、环境/依赖版本、未结责任与外部效果引用。F只改变指定文件域；R记录回退事实，已有模型/执行/事件/外部效果仍保留。不能把文件回退、重新调用模型和外部补偿合并。

安装新普通目录与R绑定没有天然跨设施事务。需要R先持久接受安装意图、目标/旧对象身份，F使用既有同文件系统原子目录操作，R按实际对象对账。root交换/确认前后故障时资源仍不可领新写者；原请求可查询“未装/已装待确认/确认/冲突”，不以缺回执推定没装。采用已实测的同文件系统renameat2(RENAME_EXCHANGE)；跨文件系统拒绝。它不撤销旧FD：旧对象保持受保护直到对账/保留责任解除，不在G3写产品实现。

## 失败与预算

显式失败至少包括UNAUTHORIZED、STALE_BINDING、BASE_CHANGED、WRITER_NOT_QUIESCENT、CHANGE_OBSERVED/OBSERVATION_LOST、UNSUPPORTED、UNREADABLE、ARCHIVE_INVALID、LIMIT_EXCEEDED、VERSION_MISSING/CORRUPT、PUBLICATION_UNKNOWN与PERSISTENCE_FAILED。未知不是成功；已确认版本损失是违反合同，不能只返回“无法确认”掩盖。

每次调用有entry数、逻辑字节、归档/输出字节和时间预算；超限拒绝/中止且不确认部分版本。共享持久容量和活跃pin由R总预算/保留协调，F不能删恢复依据腾空间。普通压缩不作为无限扩容承诺；初始采用不压缩tar便于直接检查声明大小与实收大小。阈值作为验证profile预先登记，不从一次测量倒推出SLA。

## 独立验证与替身

F可独立依赖真实普通文件、GNU tar与GitCLI；验证器在组件外读取实际目录、archive及Git rooted对象，预期来自固定fixture和原契约。controlled writer port仅替代R协调输入，不能证明实际X撤权/冻结或跨设施持久性。真实X与R组合证据在G5另验。

G3必须先证明oracle会拒绝漏ignored/空目录/模式、错误域/旧可变引用、坏archive/越界链接、丢pin/GC、缺旧写者停止/漏外部编辑、缺恢复事实以及组件缺失；生产F不存在时runner必须MISSING/不通过，不能空跑green。

## 有界捕获与普通外部编辑协议

当前host profile限定Linux本地文件系统、同一受信owner可获取read lease且元数据可精确保留。捕获前覆盖根父目录和所有子目录的inotify观察；遍历不跟随symlink，逐regular inode获取F_RDLCK并持有到必要核对结束。已开写FD或writable mmap导致lease拒绝，返回WRITER_NOT_QUIESCENT；不通过关掉监测或忽略文件继续。硬链按实际inode去重，树外alias不能绕开同inode lease。再次核对完整路径/类型/关系/原字节/声明metadata、根dev/ino以及R固定base。

任何SIGIO、修改/属性/目录结构事件、观察溢出/失效/进程重启、lease被打破/文件消失，都使本窗口不可确认。own rename交换只允许与固定old/staged对象和实际cookie/name相符的一次结构事件，不能普遍屏蔽MOVE/ATTRIB；交换后仍检查原观察队列与两个实际布局。现有/proc/sys/fs/lease-break-time=45秒；初始窗口最多10秒，并要求实际内核break上限大于该窗口、全程校验lease状态。超时或无法满足能力条件显式拒绝，不修改系统配置。此机制必须由G4真实外部进程+FD/mmap/目录变更/溢出注入用例验证，不能拿设施单文件例推断递归实现正确。

base在X执行期间保持普通可查看目录；普通未协调修改使本次发布BASE_CHANGED而不是被输出覆盖。若变化恰在交换边界或重启期间，两个目录对象均保留，返回PUBLICATION_UNKNOWN/BASE_CHANGED并让R保持占用和pending_reconcile；不能删除旧对象中的人工编辑。该失败是未确认安装失效，不是业务成功或旧版本丢失。恶意同UID宿主管理员篡改监测/控制库不在威胁范围。

## 与R的安装对账（G3-RF-01修订）

R.prepare_install先持久绑定原request_id/resource/execution/expected_revision/base_ref、old_root与staged_root的真实(dev,ino)、staged版本及原stop引用。F以原request_id记录并执行至多一次exchange，query_install(request_id)返回原意图、实际布局枚举(not_installed / installed_pending_confirmation / confirmed / conflicting / unknown)、current和retired/staged实际dev/ino、版本/归档hash、原stop_ref与未结保护关系。它从当前对象和持久意图对账，不以“请求已存”当成已安装。

R.confirm_install只在配置F authority验证原request_id的真实安装引用且无冲突后，事务更新同一resource的root identity/binding revision。不是重新注册资源。安装后R未确认时resolve为pending_reconcile，holder不释放。重启查询只能匹配“old在current/staged在stage”或“staged在current/old在retired”的已接受两种布局；任何未知第三对象拒绝，不按缺回执再次交换。R更新后回执丢失仍用原ID查询，F所有者不能自行提升R授权。

## 现有设施结论与跨环境界限

facilities-001验证13成员的普通目录→GNU pax tar→普通目录精确相等（含ACL/user xattr）；受显式Git commit/ref保护的archive在gc --prune=now后保留，未root对照消失。Linux lease及rename是实际内核调用，但只验证原语，不代表并发算法通过。只读独立核对X storage-preparation-001表明直接tmpfs docker cp会exit0导出空目录，不能采用；named私有tmpfs+暂停+RO可信exporter保留8成员，mode000由独立DAC exporter读取，mtime必须用PAX十进制字符串/Decimal而非float。

当前X tmpfs对user xattr返回ENOTSUP、ACL未验证；F host profile保留它们并不意味着X可运行此输入。X.prepare必须在任务启动前核对每个实际输入的capability profile，不能支持时返回UNSUPPORTED而不是抹掉属性。原版本仍可存档/查询，不把拒绝说成已恢复。当前host非特权进程不能读mode000或保留其他owner的输入会显式UNREADABLE/UNSUPPORTED；可信受限helper能力属于X或后续独立设施profile，不能让普通任务获得控制侧权限。


## FG01/FG02 authority-context v1 authoritative local revision

The historical two-argument callback examples above are superseded by [mandatory authority context](authority-context.md) and its exact [schema](authority-context.json). Both authorization_checker and reference_checker require actual operation context as their third argument; no legacy success fallback. Original F01-F19 obligations remain. New independent FS01-FS12 scope cases are required before this local preparation gate is revalidated. Old source/fixture/gate snapshots remain under history/authority-context-001.
