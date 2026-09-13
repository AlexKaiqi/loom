# OpenClaw：宿主调度记录、定义修订与运行责任

官方 openclaw/openclaw 固定提交 a023ff811043cbf8110009e218fa29dc7133eee1，源码 package 版本2026.9.4。问题为 H02/H03/H08/H09 与宿主/Session 边界；不从完整 Agent 产品的存在推导本系统底座应采用它。

## 调用链与权威状态

源码 src/cron/service.ts 是面向宿主的 CronService：create state、合并 start、stop/pause/resume、读/改 job 和运行入口，具体生命周期委派 service/ops-lifecycle.ts。后者121起在启动时加载 store、根据 queuedAtMs/runningAtMs 构造恢复提案、recoverCronRunProposal 后重新读取，发布中断尝试后才启动 catch-up、定时器。216起 stop 停定时器、不改持久 job。运行时 state/进程存活与持久责任分离是值得保留的结构；真实公平/中断恢复未在本次运行服务层测试。

源码 src/cron/store.ts 的公开 loadCronStore/saveCronStore 是兼容入口，实际权威位于共享 SQLite，而名为 jobs.json 的参数仅用于分区键。114起读定义与独立运行态；473起事务 beforeWrite→写 runtime 或 replace rows→afterWrite，提交后才 afterCommit 与 revision 通知；opts.preserveRuntimeState 和 jobsFingerprint guard 是调用者选择，不是所有调用自动具备的保证。src/state/openclaw-state-db.paths.ts:11 定位 <state>/state/openclaw.sqlite；schema SQL 和 DB 初始化、迁移、约束、事务模块是真实依赖。

## 实际机制实验

protocol.json 在实现驱动前登记。对未改源码 store.ts 及其传递依赖 esbuild 打包，运行实际 Node24 SQLite 和 Linux IO；tsconfig 将工作区包映射到原源文件，未替换任何状态/事务函数，metafile 和 source manifest 可核对实际编入文件。build-001 缺外部依赖、cron-001 缺未复制 SQL 资源均保留；补齐真正依赖/原 SQL 资源后才执行 cron-002。

在独立 OS 进程间完成10步：保存 J1 queuedAt=2000,nextRun=3000 → 退出重读完全相等；读取 F1 后另一进程改定义 → 原 F1 的 beforeWrite 被 CronJobsStoreChangedError 拒绝且新定义仍在；只并发更新运行态到 queued4000/running4001/next5000 → preserveRuntimeState 的禁用定义修订保留这些字段。每步独立 sqlite3 读取真实表行；名义 jobs.json 没有生成。

**相关错误对照**：最后用旧整份 job、无 guard/preserve 调 saveCronStore，runningAtMs 确实消失。这不是某个字段存在就有自动接管保障的接口；适配器必须把修订范围与运行责任所有权写入契约。结果见 evidence/cron-002 的 summary、原 stdout/stderr、SQLite行快照。

## 候选组件与不采纳

可独立借鉴：定义与可变运行态分表、事务后发布通知、旧快照指纹拒绝、运行态保留修订、重启从持久提案恢复而非为每个计划常驻阻塞进程。可拆为责任存储、调度恢复器与 Session 启动适配，而不是继承整套 Gateway/消息渠道/内置 agentTurn 决策。

待补真实能力：CronService 的公平界限、已排队唤醒与机会窗口、远端 receipt 稳定核对、恢复时不重放已完成副作用、工具权限记录与实际可撤销能力的对应、Session 完整重建与取消后子进程写权。当前只有 store 实测，不能把 queued/running 字段或 runtimeAuthority JSON 当实际执行授权/停止确认。Linux SQLite结果也不代替目标生产环境故障条件。

不采纳：绕过 preserve/guard 的全量旧配置覆盖、以 in-memory state/定时器替代持久责任、把 Gateway 内置 loop 变为底座不可分离策略。当前具体缺口已有源码与实测定位，不需要凭空扩到身份未知 Rakazo；该未知候选范围保持根调研清单原状。

## 身份、许可、依赖与复现

identity.json 固定官方 https://github.com/openclaw/openclaw 与 MIT LICENSE。dependencies.json 保存实际 npm 依赖精确版本/许可证元数据；仅安装所选 store 传递闭包所需包，未安装整个商业/渠道栈。build.mjs 用固定 esbuild，source-anchors.json 与 build-source-manifest.json 固定源码和 SQL。复现先按 setup-001 安装真实依赖、执行 Node build.mjs，再 `python3 -B research/openclaw/run-experiment.py --batch <新批次>`。每次进程只读取独立 fixture HOME/OPENCLAW_STATE_DIR，没有真实配置/凭据/模型调用。

## 独立覆盖审查补充：四类宿主状态的来源与持有者

原调研清单还要求分清上下文文件、记忆、Session和凭证；此前cron实验不能替代该范围。以下映射直接来自当前固定源码，不读取用户状态/密钥，不声明已运行这四类完整生命周期。

| 类别 | 固定源码与持有者 | 对本系统的边界含义 |
|---|---|---|
| 上下文文件 | src/agents/workspace.ts:64定义AGENTS/SOUL/TOOLS/IDENTITY/USER/BOOTSTRAP等，1277的loadWorkspaceBootstrapFiles负责加载；bootstrap-cache.ts:45每turn重新加载后按内容与文件身份复用Session级快照 | 原始工作区文件与投给模型的快照分开；context文本不是授权记录，缓存不能替代源版本 |
| 记忆 | src/memory/root-memory-files.ts:7、13定位规范MEMORY.md；extensions/memory-core/index.ts:225注册文件型memory插件及269/273的memory_search/memory_get，host提供state/本地服务入口 | 长期事实文件、检索派生能力与Session原始记录不同；会话回填/索引不是新原始真相，尚未验证召回完整性与权限 |
| Session | src/config/sessions/session-store-path.ts:14从agent/session key和配置解析scope，incognito单独分支；session-sqlite-target.ts:224—246将旧sessions.json名义路径解析到拥有它的openclaw-agent.sqlite，当前源码不能仍按旧JSON文件推定权威 | 需要稳定逻辑Session→物理所有者映射；与cron共享state数据库的位置和生命周期不同；本次只跑cron没有跑Session重建 |
| 凭证 | src/agents/auth-profiles/store.ts:1是持久profile、runtime snapshot、继承OAuth及外部CLI overlay的编排；paths.ts:13和path-resolve.ts:61/116按进程固定owner选择agent DB或共享state DB，刷新协调另见path-resolve.ts:140起的locks/oauth-refresh | 凭证有独立owner/读取/刷新职责；“同在SQLite”不等于能进入上下文、记忆或默认任务环境，也不证明撤权。只读源码，不读真实store/secret |

可借鉴显式来源、所有者和派生快照分层；不采纳根据文件名推断权威、把memory/context当身份授权或把runtimeAuthority JSON当实际能力。文件刷新、检索/回填、Session迁移和credential刷新/隔离尚是待验证范围，cron-002的结论不扩张。
