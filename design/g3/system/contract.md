# 共享契约与 M/X 组合验收准备 v1

状态：DRAFT_FOR_INDEPENDENT_REVIEW。全量原目标仍为244条；本稿先冻结组合问题、样本、预算与判据，不声称组件或系统通过。对应组件G4独立通过之后才能执行组合。实际集成driver在G5产品组合前准备并独立复查；G3先补全相互依赖的输入输出、恢复和资源合同，不凭文档代替可执行用例。

## Runtime 的有限组合职责

唯一可信控制进程组合R/E/X/F/S，恢复时读取各原设施。它只接受/实施外部Harness的明确决定，没有参考任务、sum/notes、ready/done/fail或某策略名称分支。登记/明确启动/驱动一个受理责任/按原ID查询/核对待交接/按外部条件唤起，是共享底座调用；策略不得自己持有数据库、NATS、Docker或provider key。模型原生工具只见一个普通Shell入口及获准target/script，另可在Runtime Shell使用一个有限emit包装。

依赖图：可信控制进程→R以及E/X/F/S适配；E→R与NATS；S→原Pi/X/F与可信provider桥；X/F各持原执行/文件事实，R持引用。参考Harness与业务验收器不被Runtime导入。Harness代码仅在受限S环境运行；orchestration条件同为版本固定普通代码，在按需受限环境求值，不常驻每个等待任务。

组合顺序固定：R登记并授权真实F对象→显式受理invocation与原Harness/input selector→E固定H并保存四文件输入→R关联原input_ref后才交付S→S/X真实隔离执行原Pi→每个provider/tool外部效果前保存原身份与原pending字节→原结果保存后由外部Harness提议下一责任→R事务接受决定/下一责任→X确认保存并真正seal→F按原base和R安装意图发布→R确认同resource新物理根。等待以R已保存condition/input起点、必要S/F/X版本及实际release为边界，不能以早期cancel或策略文本标为已归零。受理下一责任只保存推进义务，不授予立即写入资格：依赖同一Surface/Workspace/Session的新责任必须等原holder实际停止、F安装布局核对及R confirm/release完成后，才取得当前有效base和输入。原input已经固定但目录版本变化时按原引用重建/明确拒绝，不用新可变路径替换旧输入。没有安全查询依据的未知窗口保留暂停，不重发效果。

输入关联补件G3-RE-03由R/E共同冻结：R只保留原selector+唯一input_ref；H、事件正文和输入manifest分别归E/NATS。原invocation要求input时，在缺少有效input_ref前不向Harness claim；不让读文件自动结清责任。明确负设施receipt表示原尝试被服务拒绝；未知不是拒绝，同原ID不能覆盖旧negative再发。

文件安装补件G3-RF-01保持旧根/新根与完整base/execution/generation，失交换ACK先观察两根，禁止再交换。完整RestorePlan由控制调用明确Surface版本、Workspace版本、原Session continuation边界与保留的事件起点/未决责任/外部效果引用；分别只回退S或W也要在原计划记录其他域保持何状态，不改写已发生的原Session/NATS/X记录。M06还须逐项核对回退动作自身：原restore请求/完整plan受理在首个安装前已持久保存，每个实际F安装回执按原资源/版本/代次关联，失回执与部分安装保持可查询、不会再次交换或伪装整个计划原子完成。R最小引用补件由独立覆盖发现后另行定义并验收。

## 所有活动对象的资源预约

一个活动推进slot同时可能持有S Node/Pi容器、一个双域工具容器以及一个只读导出helper。预约按最坏重叠量而非平均值：S 512MiB、工具128MiB、helper128MiB，共768MiB，最多3个容器对象；keeper属于对应容器，不另计容器但计其PID。S pids64，工具32，helper32；每容器显式CPU额度、只读根、no-new-privileges、有限/tmp/shm/私有volume/输出。网络none，宿主key/控制句柄不入容器。绝不为了等待导出才临时要求一个无法获得的helper槽位。

G4 X自己的2容器/256MiB只约束独立X批次，G4 S及G5正式组合另按本3对象/768MiB预约。S的export与工具export串行共享slot内helper；两个主要容器可暂时冻结，但未seal不释放配额。宿主观察器不变成每个wait的常驻对象。

当前16CPU/约32GiB开发环境下，系统正式最大8活动slot：24个产品活动容器、6GiB容器memory配额；另保留最多1个共享只读观察容器128MiB。所有任务/helper CPU配额总和不超过8CPU；共享Runtime/NATS及观察进程额外预算2GiB，总验收RSS/配额预算不超过10GiB。工作目录与证据预算20GiB。每slot全部私有可写卷/日志/归档/Session合计上限128MiB、inode8192；固定依赖/镜像RO另计版本。操作有界超时，任一全局预算超出使该样本失败并保留归属证据，不放开权限或追加未预约对象。数字源于3对象生命周期和当前硬件的保守份额，不是运行后选择的SLA。

## 固定组合检查

M01：v5 [2,3,5]及独立固定seed输入，读取真实report总和、notes准确可解析的历史报告引用、实际两域执行及原provider/Pi/tool记录、一次获准通知与下一Step事件输入。固定响应接线和真实gpt-5.6-terra分批，每输入真实重复3次；每例最多6次模型响应/6步、单回复2048token、总15360输入token、300秒，错误或预算终止不能冒充任务成功。报告/notes在两个真实普通目录；模型收到的投影确有模板/blocks/位置/事件/反馈。

M05必须另有与M03联合的实际轨迹：真实X外部效果已发生而原回执未确认→R保留原执行ID与未知核对责任→Harness裁剪该长反馈→释放全部旧环境→新环境按原ID查询或有据暂停，原外部效果计数仍为1，R未决责任不因裁剪文字或读取引用而丢。S的UNKNOWN_EXEC_17标记仅检验模型视图，不能代替本联合观察。

M02—M10：组合越权与身份伪造；失accept/provider/tool/decision/install回执；结果保存后旧容器销毁新容器零额外调用查询；任务长输出裁剪并完整取回；单域/双域RestorePlan及外部效果计数保留；普通人工编辑在capture/install窗口被察觉；受理后Harness换版与坏引用拒绝；事件正文/代码fence不能控制调度；原pending不能因已读文件/连接断开丢失。每个高风险边界受控故障3次，使用实际进程/Engine/NATS/原文件观察；不能用全系统重跑相同答案替恢复。

X01多Surface：3个普通Surface互传不可变产物引用，条件为外部Python函数，覆盖事件在等待前/登记间/已等待后3种时序、通知丢失及Runtime重启；每种3次。实际目标、原事件seq/source、输入range、唯一后继受理和真实产物逐项核对。禁止消费者读取后来变化的同名路径冒充原版本；不引入任务图DSL。

X02多策略：同一底座二份外部普通Harness，A投影完整必要上下文，B以显式摘要/原来源引用投影并增加一次自检策略。6份固定整数输入×2策略×2重复=24实际模型样本；同模型/环境/输入/权限与最多6步的共同预算，固定交替AB/BA顺序。这24个样本按同一输入/重复的A/B两成员组成12个并发对，AB/BA表示交替发起顺序而非串行运行。独立driver在第一个S已载入固定输入的受信准备切点暂扣交付，直到第二个S也真实启动，再同时放行；直接记录两个不同Harness版本的原Engine exec/namespace同时活动，不能仅靠R状态标识。各自独立Surface/Workspace/Session/事件范围和副作用命名空间；影子策略仅写自己的副本。24份都要有正确产物和完整观察才证明该有限样本可运行；另原样报告所有失败/耗时/token/工具数，不宣称统计优越性或挑最好一份。策略差异须从实际provider输入/继续行为观察；Runtime源版本与配置契约保持相同。

X03等待驻留：1/100/1000/10000个等待责任，分8个共享Namespace；每个普通Surface保留至少goal/notes，原输入/条件/Session版本可查，不启动每等待对象的进程。各阶梯稳定30秒、1Hz采样，并重启共享Runtime后再采样；实际任务专属容器/PID/连接/活跃volume均为0，原等待责任计数完全相符。共享Runtime+NATS进程/连接数不得随任务数一对一增加；新增常驻共享RSS不超过512MiB，静态工作集新增不超过4GiB，记录全部实际字节与文件数。10000用来实测跨4个数量级静态驻留，不外推百万/无限并发。共享事件客户端≤4且不为每wait建持久consumer。随机固定seed抽取32个等待对象用真实事件唤起，30秒内获得原目标的新责任，随后产物正确且重新归零；30秒来自1秒共享历史扫描上限+预约/恢复余量，非用户SLA。

X04活跃吞吐：固定64个相同规模CPU/文件工作任务，使用原Pi的确定性provider夹具隔离网络模型噪声，仍执行真实X/F/R/E/S全部路径。每任务普通Python进行固定500000次整数混合运算并输出独立可核算的值，再一次Runtime Shell记录引用。并发1/2/4/8，固定顺序[1,4,2,8]各3批；报告总完成数/秒、p50/p95/p99受理到完成时长、queue与执行时间、峰值实际资源、全部错误。每批64/64产物正确、1800秒内收敛、资源不越上述预约；8并发中位吞吐至少1并发2倍，基于8slot/8CPU预约检验实际可伸缩性，未满足即待修复，不能运行后调低。固定响应吞吐不包装为真实模型吞吐；真实模型24样本另报网络/token影响，模型费用只在有实际价目可用时计算，否则直接报token和call，不编金额。

## 验收观察与限制

M/X产物oracle读取独立源输入，不复用Harness求和代码或其claimed sum；实际report内容、notes的历史可访问引用、source hash/原Session/原NATS/Engine和Linux过程事实共同构成断言。程序或模型说PASS不能替代任何一项。正式批次缺组件、缺case或缺实际采样时保持UNVERIFIED/FAIL。

当前Linux范围是记录的WSL内核与Docker Linux Engine；可复现启动不要求Windows特性，部署目标为兼容Linux内核/Engine并先跑环境前置验证。不能把WSL测试外推到未测发行版、远端失联、多副本/power-loss或无上限保留。
