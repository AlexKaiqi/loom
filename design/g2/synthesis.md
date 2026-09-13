# G2综合判断：从系统问题选择可独立验收的机制

状态：G2_REVIEW_BASELINE。G0/G1已通过；本文件固定G2研究判断，阶段最终裁定单独见g2-gate.json。本文不宣布组件或产品通过，也不授权越过未通过门槛。v5、244项原始要求与P01—P15范围不变，M之后的多Surface、多策略与规模验证仍为必须交付。

## 调研覆盖与证据层次

主清单12项，加既定NATS专项及Daytona历史公开版本，共14项。DBOS Py/TS为同一项目，OpenHands SDK/automation为同一研究单元；不把两份仓库凑成额外项目。每项固定源码均实际克隆，职责/状态归属、相关先行协议及运行、模块位置、依赖/许可与不采用项见research/<slug>/analysis.md和identity.json。源码声明/运行/推断分别标注，未运行的层保留边界。DeepSeek两个预判失败、SoL召回完整性、Codex缺完成事件、DBOS等同ID行为都是研究所得缺口，不因实验有输出改为该能力PASS。

Grok原项目身份未知的三个候选仍未知。本轮已有OpenClaw/OpenHands提供共享宿主与任务资源分离的源码/实际持久责任对照，没有未解关键问题需要猜测某个Grok名称；不伪称识别原项目或把三个候选都变成必须克隆项。新增的Git普通文件与Docker/Linux专题由H06、H04/H05实际缺口驱动，属于原清单允许的既有设施依据，不扩张为新产品研究计划。发现记录见research/discovery-log.json。

## 各机制的比较结论

| 系统问题 | 实际比较及关键反例 | 当前判断与边界 |
|---|---|---|
| 局部事实与外部策略 | Pi已有持久lane/operation且accept与drive分开；DeepSeek已有原始event Session/投影/真实flock；mini默认save在效果之后有丢轨迹窗口；Codex客户端不强制完整终态 | 优先验证Pi局部Session适配，DeepSeek为有依据的备选。复用原始历史/查询，不另写第二套model/tool loop或竞争真相。Pi同ID重用、后端fsync/并发与发行构建尚须补契约；DeepSeek不能默认容忍任意坏尾。 |
| 已受理推进责任 | DBOS实际新进程复用完成step，但sync recv每等待一线程，旧ID改参数返回旧结果，未确认step可重复效果；OpenHands durable PENDING与OpenClaw定义/运行态分离有实证 | 采用小范围Runtime控制记录+共享恢复驱动的路线，持久设施复用SQLite事务；局部结果只引用Session。DBOS整workflow与阻塞等待不作为当前底座，不在Harness中另建调度。SQLite语义和多worker交接仍须G3真实用例。 |
| 事件历史与等待 | NATS file stream实际崩溃/重开恢复、历史/持久consumer重交；但Msg-Id不比正文，窗口去重不是永久绑定，保留策略可删掉恢复依据 | NATS JetStream作为事件首选；受控入口在Runtime登记原请求完整绑定并核对回执。历史起点与持久条件用于恢复交付，通知只提示。不得自研文件末行/锁消息队列，也不为每个等待任务开consumer进程/连接。 |
| 执行身份与真正停止 | OpenSandbox普通Controller与Daytona SessionService：活索引可查、新进程索引丢；取消后逃离进程组的旧FD仍写。SRT能实施路径和namespace，但继承FD及旧wrapper写能力需外层处理 | Linux Docker Engine为G3双域执行首选候选：实际namespace回收、原生路径、cgroup和显式seccomp已有限验证。不能仅采用前两者普通取消或把SRT新配置视为撤权。稳定ID、输出保存、查询/暂停与写者协调是窄适配缺口。 |
| 普通文件与范围恢复 | AgentFS真SDK/DB可重开，但不是Shell/FUSE证明；整库回退删除新工具事实而外部效果不回退；Git普通目录保留文件接口，可包含ignored依赖，仍能捕获T1/B0不一致组合 | 保持原生目录，优先已有Git/归档设施保存受管理版本；协调读写后捕获、双域独立、显式版本组合。完整性、symlink/metadata/属性过滤等在G3明确，不把tree ID当一致性证明。AgentFS许可正文缺口使直接代码采用关闭。 |
| 投影与裁剪 | SoL原Session不改、分页可重建原文，但同大小篡改归档后召回仍返回坏数据；重新投影才发现hash mismatch。DeepSeek/ OpenHands分支视图也不等于全部原历史 | Harness拥有投影/裁剪选择；原文保持既有权威，用带版本/来源/hash的引用提供受控读取。缺失/损坏必须显式拒绝。暂不整套采用SoL在线压缩、融合动作或其旧Pi依赖。 |
| 持续产品与策略评测 | Codex客户端/宿主/rollout、OpenClaw Gateway/状态分工、OpenHands Server/Automation说明UI连接与运行责任分层；Harbor真独立容器直接读产物，CLI0含真实失败 | 宿主可共享常驻；任务进入等待后只留静态记录。验收器位于Runtime外，固定任务/模型/预算并隔离策略资源，直接读实际产物及失败。不能把框架COMPLETED/reward平均数或模型自述变成Runtime通用业务终态。 |

## 窄路线的选择依据

DBOS的合法备选不是只有整套长workflow：可以仅以短workflow/step+队列驱动Runtime责任，长期等待另存静态条件，局部事实仍由Session持有。这条路线可复用队列领取、调度重试和进程重启恢复，减少自有短作业驱动代码；本轮Python真实step/恢复和automation静态责任实验支持其进入候选比较，未跑DBOS短控制器与Pi的集成。

与直接SQLite控制记录相比，DBOS短路线仍需Runtime登记/授权、完整ID内容及来源/版本冲突校验、等待起点/交付关联、Session/Docker/NATS结果引用和跨设施核对。DBOS同ID改参数不拒绝，自动重试也不证明外部效果安全，这些已实测缺口不会因缩短workflow消失。当前仅需少量可索引的受理/待交接/等待记录，SQLite事务加共享定额领取/恢复扫描保持这些事实直接可见，并避免为同一外部阶段再引入第二个workflow推进位置。它增加了需要独立验证的公平领取、崩溃接管与重试调度代码；这是明确成本，不能声称天然比DBOS可靠。

因此本阶段选择SQLite控制记录作为G3优先路线，保留DBOS短控制器为备选。若正式责任/公平用例显示手写领取协议复杂度或缺陷不能以窄适配闭合，回到本判断比较引入DBOS队列；不能通过降低交接/活性标准保住SQLite。尚未选择新的消息系统，事件持久性继续由NATS承担。

S的第一独立验证粒度明确为：一次外部稳定受理operation，调用已实测Pi核心的lane.accept，再由native lane.drive运行到settled/waiting，以getResult/原entry核对。工具执行委托X；工具内部边界和unknown恢复按原稳定invocationId查询，不把Pi任意内部checkpoint改称外部决定已受理。Harness可以通过已验证hook停止/继续这次局部推进，跨operation/等待的后继由R保存。根后续按protocol-step-002先行验证公开after_tool返回terminate:true：单工具、无待处理inbox时，一次模型+实际工具后native operation保存结果即返回；新进程原结果查询0模型调用，下一operation模型上下文含原tool结果且效果不重复，无hook对照实际继续到第二次模型。原始证据step-001，独立step-independent-001及research/reviews/pi-step-boundary.md。源码还表明终止要等当前tool batch全部结束且全部terminate，queued followup也可能提前继续；因此本结果不声称任意并行batch/任意inbox状态一次drive恰好一步。G3先固定参考Harness单工具/无未处理inbox的粒度与相应输入校验，其他合法粒度按外部策略定义另验，不能把整个run改名step来规避。

当前已实跑入口是固定Pi源码通过TSX及研究路径映射导入AgentHarness/JsonlSessionRepo、harness/context与env/nodejs；未测的SQLite后端、真实provider等入口按各自合同进入G3。发行包完整构建仍失败，不将未生成catalog或SDK类型问题隐藏为已发布可用，也不要求现在修整个未采用发行物。C04边界须枚举这一具体加载入口及其传递依赖；新后端/真实provider带来的增量依赖在首次采用前补查并保留版本。

## 完整推进链与权威归属

外部授权代码登记Surface/Workspace及不可变Harness版本，明确发起调用；登记不隐式调用模型。Runtime控制记录保存受理身份、完整输入/来源/版本绑定、所需环境与待交接责任。已有Session接受该调用后持有模型消息、工具记录、原始结果与继续点，Runtime只保留对应引用和交付/执行责任。

Harness普通代码定义投影、模型适配、工具与反馈继续规则，Session已有loop负责局部执行；同一Shell工具委托通用执行器。执行器按登记目标与实际对象决定固定域，落实用户、挂载、端点、网络/资源和生命周期。它保留可按原ID查询的执行结果和原始输出引用，不能把断开观察连接当作停止。保存之后才确认相应边界；无法确认的外部效果按原ID查询或暂停。

局部结果已经保存而Runtime未登记后继时，共享恢复驱动依据既有责任扫描/查询补交接；已接受后继按原决定实施，不重新运行非确定策略来替换它。应用emit经范围受控入口提交，NATS负责其事件持久历史，Runtime持有完整受理与交付关联。Harness的等待条件由普通代码表达，Runtime持久保存起点/条件引用/继续位置，后续历史扫描能处理先发生事件与通知丢失。等待记录不附带活Session worker、连接或容器。

Surface和Workspace保持可用普通Shell读写的目录。写者停止或实际失去当前对象写能力后才交接/捕获/恢复。两个域可独立选版本，历史结果及外部效果不会随文件回退抹掉；跨Surface传递使用可解析到具体内容版本的授权引用。原始Session记录与权威事件都不放进可随Surface回退的目录。

这里描述的是G1合同到候选机制的接线依据，尚无产品代码或已通过的跨设施原子性。事务内成立的保证不得扩大到NATS/Session/Docker之间。

## 拟定独立验证边界

这些是库/适配器边界，不是新增微服务、模型命令或任务DSL。G3逐项给出正式输入输出、状态和可执行用例，G4分别通过之后才集成。

| 边界 | 最小依赖与独立观察点 | 应先拒绝的相关错误 |
|---|---|---|
| R：登记、受理和继续责任 | SQLite事务；独立sqlite读取、进程重启及关联校验；Session/event/executor用明确边界协议驱动，正式跨设施情况另用真实依赖 | 相同ID不同内容/来源/版本、丢回执后另ID重发、旧定义覆盖已接受决定、只靠通知推进、先确认后落盘 |
| E：事件提交/历史文件视图 | 实际NATS server；PubAck/stream读取、控制记录和输入文件完整范围独立核对 | 原生dedup冒充冲突拒绝、应用伪造系统事实、读文件当ACK、先查后订阅漏事件、活跃恢复依据被保留策略删除 |
| X：双域执行及写者生命周期 | 实际Linux容器Engine与原生文件；授权域/OS身份、真实进程/FD、cgroup、原ID查询与完整输出 | cd改变执行域、前缀越权、伪造user、过期路径/挂载对象、端点/FD泄漏、取消即放新写者、未知即重跑、资源配置未执行 |
| F：受管理版本和引用 | 普通目录与已有版本工具；原字节/类型/必要metadata、不可变版本、两个域及外部效果独立读取 | 漏掉ignored输入、捕获中间多文件态、只存可变路径、恢复抹执行事实、旧FD写入当前权威目录、未经协调的人工修改被当不存在 |
| S：已有Session适配及Harness绑定 | Pi固定局部Session（DeepSeek备选）；独立原记录、provider调用审计、实际工具副作用、全新进程查询 | completed ID重用、丢保存结果后重新推理、将unknown文本当成功、截断输出视为final、策略版本静默替换、另造局部真相 |
| V：外部验收与策略比较 | 固定输入/镜像/模型/预算的隔离执行；验收进程直接读取产物与原始运行记录 | 执行者SUCCESS/exit0冒充通过、遗漏case仍green、坏证据/版本不一致、shadow写同资源、失败不入统计 |

投影/裁剪属于外部Harness+引用适配，不单列一套存储服务；等待/编排属于R的通用交付机制和外部普通代码定义，不新增工作流语言或长期任务daemon。六个验证边界可以在同一Linux进程/代码库中分层实现，依赖方向与状态归属须通过G3/G4结构审查。

## 采用条件、剩余假设及停止扩展

直接候选限固定NATS、Pi局部核心、Linux容器执行接口、Git/已有归档和SQLite等成熟设施；研究借鉴的其他框架没有整套进入产品。拟使用的Pi MIT、NATS Apache2、Git GPLv2外部CLI、Moby profile Apache2等记录只覆盖对应对象，不能替第三方依赖或基础镜像一揽子背书。当前具体使用边界与实际版本/传递依赖/许可证原文及NOTICE已分别核对，见research/reuse/nats-licenses.json、pi-license-boundary.json和linux-tools-licenses.json及对应md；总入口research/reuse/README.md。当前Pi限已实跑core/JSONL+faux/TSX加载链，不包含未验证发行物、SQLite后端或真实provider。NATS为固定外部binary及默认客户端/验证器，Linux为现有工具/API/原镜像与明确复制profile。新入口、版本、构建选项或发行用途在引入前增量核查使用条件，并重验受影响接口；这不替代已完成的当前候选核查。AgentFS根正文缺口未解决故不直接采用；Daytona AGPL daemon仅历史参考不复制；SoL0.84.2不能冒充已和Pi0.85.1组合通过。

G1 H01—H10的现实前提在research/hypotheses-evidence.json逐项链接。G2探索解决路线是否值得进入独立验证的问题，不能将候选的局部成功升级成Runtime性质。所有P01—P15仍UNVERIFIED，正式门槛D/E/F/Z分别验收当前组件/组合/系统。

本轮研究收敛条件是14项原交付、机制和完整接线比较、全部主要反例/限制/许可条件及独立复核完成；不是研究所有实现细节，也不是等所有候选变绿色。下一步只围绕已明确六边界准备G3合同和正常/边界/故障用例；若真实验证否定关键前提，回到最早受影响判断和必要定向补研，不把整个项目调研无限扩大。
