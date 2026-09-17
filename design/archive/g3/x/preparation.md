# X G3 准备交付

状态：READY_FOR_INDEPENDENT_REVIEW；未运行正式 X 组件，未自行通过 G3。核心来源、性质与 28 组正式用例（展开为 97 次参数运行）见 cases.json；每例包含独立可反驳判据、错误机制名和实际/fixture 依赖。

## D01—D05 对照

| 门槛 | 已准备资产与实际证据 | 保留边界 |
|---|---|---|
| D01 抽象/契约 | contract.md 明确 R/X/F/S 所有者、完整输入绑定、实际身份与路径、双向流、原ID查询、两维状态、输出保留、冻结/停止/交接、资源和错误 | 不生成 Runtime 业务终态；F 发布与 R 授权仍各自所有 |
| D02 用例与可执行环境 | cases.json 28组/97次；run.py 预写97次动作编排、真实进程kill故障点与恢复、collector.py 直接Engine Unix ExecInspect/两UID namespace/目标只读cgroup/真实同卷归档/原blob读取，fixtures.py 仅无害普通代码与授权供给 | 没有目标时实际 MISSING_COMPONENT rc4；F交接适配未给时 MISSING_DEPENDENCY，不补理想替身 |
| D03 判据有效性 | oracle-preparation-004 实际26项校准：旧准备raw正控、逐一缺失、空cp/不可读mode000/错卷/RW helper/旧PID仍在/配额错误/keeper可kill等错误观测、missing target、真实always-green进程；均预期检出 | 错误观测变更是oracle校准，不是每个正式known_bad的真实生产变异。G4需每个错误机制通过同一真实collector检出 |
| D04 真实设施/替身边界 | 固定Linux Engine/image/seccomp；storage/lifecycle真实quota、tar、UID、namespace；collector-preparation-005/006直接运行新正式collector，9字段判据+2数值判据通过 | R/F的授权/版本输入为明确fixture；原Pi/模型流程由S另验；没有生产X行为通过结论 |
| D05 数值与失败保留 | contract.md预定2/6MiB、64/128inode、128MiB/32pids、CPU.25/.5、输出64KiB每流/96KiB总、导出8MiB/展开12MiB；配额/旧写者固定3次，资源时长8秒、普通20秒、单控制调用10秒/整例120秒 | 这些为独立验证样本，不是容量或SLA；003测得collector三个阶段约6秒后在正式执行前把资源样本从2秒改为8秒，为独立采样留窗口；未拿运行结果倒改产品承诺 |

## 实质决策与明确否决

直接 RW bind 权威目录不能限制总宿主磁盘分配，否决。直接 tmpfs+docker cp 真实返回0但只给空根目录，同样否决。选定首个候选为每代私有 named tmpfs，真实字节/inode上限，whole-container pause 后同一实际卷RO exporter。普通UID导出mode000失败；固定UID0仅DAC_OVERRIDE的可信RO导出器能保存，真实尝试写卷返回EROFS。任务UID1000/cap0不能杀root/cap0 keeper；命令自然退出仍保留卷直到保存/停止。

当前tmpfs user xattr=ENOTSUP，ACL未证明，必须在接受需要这些属性的输入前明确UNSUPPORTED，不能运行后剥落属性。F host profile可更完整；X子集不缩F原承诺。导出保留普通字节/目录/空目录/软硬链接/mtime_ns/mode/uidgid，安全处理不跟随外部软链，不解包任意宿主路径。

Engine exec身份在start前保存；ExecInspect不支持重读丢失的stdout。完整EOF+外部持久原blob才COMPLETE；观察丢失明确INCOMPLETE_OBSERVATION，超限明确INCOMPLETE_LIMIT并保存收到的前缀。不得将它们伪称视图裁剪但原始完整。checkpoint为PREPARED；中间S原Session前缀可resume同对象，不能作接管证据。最终F发布另需同对象实际停止、当前base/代和R写协调token；pause不控制外部人工编辑。

## 原始证据与修订

- storage-preparation-001：原协议后真实4MiB与128inode耗尽；rc0空cp、普通UID归档exit2均保留；RO可信导出两代、heartbeat增长、原namespace PID到空。
- lifecycle-preparation-002：真实EPERM杀keeper、正常命令退出后mode000文件还在、RO helper写EROFS；固定对象清理。
- collector-preparation-003：新真实collector的UID/namespace/归档/停止7判据通过；主动复查cgroup={}，不作资源观察通过。
- collector-preparation-004/005/006：先行amendment后读取实际keeper /proc/PID/root/sys/fs/cgroup 的只读内核挂载；目标memory.failcnt、pids.current/max、CPU配额明确存在，005/006还核原解释器+脚本确实是Engine exec的实际argv。observer未读取宿主凭据/任务env。
- oracle-preparation-001：正控因Docker把cap名称规范成CAP_DAC_OVERRIDE而误拒绝。保留原失败，解析只规范可选CAP_前缀、不扩权；002—004全26校准通过。

完整原始文件、脚本/协议输入快照均在 validation/components/x/evidence/；preparation-index.json 绑定当前准备输入及所有批次文件hash。旧失败不会被新批次覆盖。

## 执行与实际边界

在 WSL Ubuntu /path/to/loom：

```text
python3 -B validation/components/x/run.py --batch NEW --component-json '["/absolute/path/to/test-adapter"]'
python3 -B validation/components/x/selftest.py NEW-CALIBRATION
python3 -B validation/components/x/probe_collector.py NEW-PREFLIGHT
```

不传目标得到MISSING_COMPONENT并非零。--case只允许局部诊断并标PARTIAL，不能当全量覆盖。--variant传已注册错误机制给可信测试context，SUT永远不接收case ID/expected。测试adapter会收到自建credential-like canary和已打开自建文件/socket，以检查其是否错误继承到任务；这不是任何真实key。collector自己从内核/Engine/字节读取，任务JSON位于独立json字段，不能覆盖原字节hash/mode等观察。

Docker配置、完整ID和同卷Source仍是受信设施事实，不是抵抗恶意daemon/内核管理员的证明。首个API选择直接Engine exec解释器+脚本；如果以后加入外层可信wrapper，须先修订独立交付证明。不同执行ID/域不共享可写卷；复制必需依赖、只读输入与全部写入目录预算需G4实际组件实现通过。

为了避免观察器自己超预算，每次helper启动前检查本fixture新增实际对象数与配置内存；最多任务+helper两个/256MiB。停止后不再重挂已卸载tmpfs读文件。发现其他并行对象变化会失败或不可确认，清理只按确切fixture标签或亲自创建的ID，不能删除其他任务对象。当前helper是测试观察者；真实X exporter同样计入运行预算。

恢复正向能力补件见restore-supplement-findings.md/restore-supplement-001.json；原门槛已由根局部失效并留历史。X028实际新身份冷恢复与X024真正坏源负例仍未运行正式组件；新增11项恢复准备校准、旧26项回归和真实collector preflight分别保留，不能从绿色准备结果自批X恢复。
