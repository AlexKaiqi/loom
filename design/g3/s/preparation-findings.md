# S G3 准备观测与未通过范围

本记录只报告准备；没有 S 产品组件，没有 G4/G3 自批。

- public-preparation-001/002 保留两次启动失败：探针错误使用 retry.maxAttempts，Pi validateRetryPolicy 要求 enabled/maxRetries；第二次错误只调延迟未解决。源码原副本、stderr、退出 1 全保留。public-preparation-003 改用公开 enabled:false,maxRetries:0 后 7 进程/9 项观测成立，协议预期未改。
- 固定 Pi 原 JSONL 显示 provider callback 前 assistant.effect_pending/reserved responseEntryId，tool.execute 前已有完整 assistant/tool intent。公开 Session.setValue 的 lore.prep.binding 值在新进程保留。原受理/运行/查询间未另造模型历史。
- before_tool 读取原已保存 assistant，可把双 tool 整批 block+terminate，0 effect、1 provider，原双请求保留。单 tool 的 after_tool terminate 保存结果，1 effect、1 provider；无守卫负对照产生 2 effect、2 provider。不能从中推断多工具逐个释放或并发 inbox 安全。
- 原保存 step 新进程 query 的结果与 JSONL 全字节一致，0 provider/tool。孤立 pending 新进程 query 无结果且 0 provider；public drive 沿原 reserved ID 保存 interrupted/error 且 0 新 provider，并不消费可信 cache。准备 probe 未实现 wire cache/产品暂停状态；该状态须由 R/S 独立案例 S-015 验收。
- container-preparation-001 失败：沿用的 TSX tsconfig.baseUrl 是实际绝对路径，而容器重映射到 /lore，core import 找不到；Node 本身成功加载。002 对精确只读挂载保留相同容器虚拟绝对路径，原代码/tsconfig不改；2 个顺序容器均单/双工具观测成立并按完整 ID 清理。固定镜像内 Node v24.21.0 的实际 ldd 已保存。不能挂父级 home 来掩盖路径问题。
- 容器 probe 的无密钥 Python 父进程保留私有 tmpfs 直至读取 worker 退出后的原 JSONL，再结束容器；该探针不实现 X keeper/可靠 RO exporter，也不证明进程退出后 tmpfs 自动持久。生产方案必须按 X 生命周期合同处理。
- oracle-preparation-001 基于真实 Pi accepted JSONL 读取，与 oracle 无共享 Pi reducer 代码。已出现 assistant 的坏原记录导致 FAIL；缺 source/hash/path、空跑、S 自报 origin、空断言、exit0 无 bundle 都为 INVALID。缺观察不能算负控被杀。控制只证明这些验证器能力，不自批 25 用例覆盖完整性或真实 S 行为。

当前经独立预审和上下文补件为 27 案例/150 断言，仍是 G3 草案，要求实际可信 collector 在 S 可写区外采集原 Session/原 provider audit/实际 X effect/OS observation。runner 可以执行指定外部 collector，只传 setup/actions（不传 assertions），collector 缺失/空跑退出 2。还没有产品 S/X/F；现已补可执行实时 collector，明确接真实S入口和X双向流/F原引用包装，当前缺目标/已验设施时实际MISSING。源代码/物理分离及peer接线须总接口审查后冻结，不能用 bundle 的 origin 字符串自证。D02/D04 的实际组合观察准备在此仍未最终裁定；D01/D03/D05 也须独立角色审阅。

可追溯文件：contract.md、cases.json、两份 preparation-protocol、provider-preparation.md、validation/components/s/README.md；原命令与版本摘要在每个 batch result.json。原动态状态、faux 和静态源码能力严格分开。当前停止条件与数值仅准备资源上限，不是新增产品 SLA。

新增准备：live-driver-missing-001/002保留实时driver因目标缺失MISSING/exit2、无bundle；不把它计正式用例通过。新增S-018实际feedback bootstrap，只有当前operation provider输入中原toolResult内容可证明前序结果，不以旧toolCall脚本中的相同字样代替。oracle原版本与新的自测批都保留。

独立预审发现此前S-018实际驱动的Shell未输出所需标记（原public probe中的直接Tool返回不能替代），以及S-025累计final计数、S受理ACK丢失切点、PID观察缺口。修复范围、历史与新准备校准单列 review-repair-003.md，旧记录保留；原“25用例”数字仅指旧批次。

B060主动检索和S020有用裁剪的明确遗漏已按根委派补齐，见context-supplement-findings.md；旧26/109仍有完整源/索引快照。context-preparation-001的真实普通检索与显式oracle校准共14项、oracle-context-001原9项成立，完整live-driver-context-001仍MISSING。它们不是新增正式S行为通过。
