# X 的 Node/Pi Session 执行增量

本目录是先行准备，不是产品或门槛通过。原 X28/97 与其 Python profile/预算不变；仅补原 S/G3 已要求的 Node/Pi 执行环境。来源和内容绑定见 source-bindings.json，预算/字段见 profile.json，12个独立正负问题见 cases.json。根正在运行原X全批；本轮不启动Docker、不改原X/S输入。

内部 domain=session 仅可由可信 S 调用 fixed-node-pi-session-v1。原模型 Shell 仍只有 runtime/task 两个目标；session 不是第三个模型工具。原 X 合同的 F base 在此用途明确例外：Session 原snapshot/continuation所有者是 S，X 校验可信 manifest、精确archive字节和原execution/generation，保留原 JSONL；不解释Pi语义、不把Session叫Surface、不走F双域install。普通输入/Surface/Workspace版本仍来自F。此为原X支持S原字节checkpoint职责的补全，须独立增量通过后启用。

只读依赖不能用整个仓库或整个宿主home作为便利挂载。dependencies.json以既有C04实际导入路线冻结882文件、4个明确包内链接；含Node二进制/完整LICENSE、Pi/TSX源、包解析metadata、真实esbuild二进制及Go/xsys通知。按manifest将原目录布局投影到/opt/lore，生成固定tsconfig仅重定位baseUrl，不改上游源码。原加载probe曾挂整个Pi仓库，因此不能证明这个较窄投影已能加载；如果缺实际必需文件，必须保留失败并只补有依据闭包及许可证，不能退回全仓库挂载。S实际新增provider桥或Harness模块依赖也必须逐项固定，不能用旧faux闭包宣称完整兼容。

依赖挂载前核真实文件类型、精确全成员、内容SHA、target、只读位、原来源与当前授权。入口实际ExecInspect必须是普通Node argv；不得以任意Python/shell包装改变脚本语义。Harness和input是本次固定内容，/input、/workspace在S容器只读；工具另在其已授权双域执行。任务私有/work与有界/tmp/shm之外不得写入；镜像根RO、UID1000/cap0/NNP/固定seccomp/networknone。禁止host DB/socket/key/继承控制FD；Node内代码仍不被宿主Python导入。X保存完整请求包含profile、Node/Pi/Harness/input manifest与挂载映射；同ID任一变化conflict，真实失ACK按原ID核对。

资源从共享契约推导。S512+工具128+helper128=768MiB/3对象，helper串行共用，不另开第四个；S .5、tool .25、helper .25合每slot1CPU，8slot合8CPU。旧probe CPU1仅探针，不推广。为保存两个重叠checkpoint，在128MiB原slot上限内先分配Swork16、tmp32、shm1、streams2、两个archive各18MiB；工具work6/tmp1/shm1/archive8/streams0.125MiB；helpertmp/shm共2MiB；控制spool4MiB，合109.125MiB，保留18.875MiB余量但仍计总账。inode实际所有卷/spool合不得超8192。旧加载probe tmp64只是历史探针上限，改32是本次先行预算，未称已可用。所有历史档案复制/重叠实际字节计入总20GiB证据/工作预算；活动slot保留版本必须按128MiB记账，不能以移动目录规避。超过则停止/保留未知与已有字节，不能丢原唯一确认快照或擅增预算。实际F输入配置也须显式：F默认64entry/1MiB不覆盖S027的512文件，较大limits在本增量用真实F原件测试后使用。

JsonPort每次subprocess.run创建新短peer；原X JSONL adapter持有Engine duplex socket、reader线程与buffer。须由一个可信共享X桥保有通道，短peer仅按原execution_id/container/exec/object_generation/channel_id请求原持有者，不能靠每次启动新X对象或重attach伪装延续。桥只承担字节传输/原回执，不运行Pi或外部Harness。短peer退出不自动close_stdin；close只沿明确原通道请求。实际发送后ACK丢不自动重写；缺明确重试身份时返回UNKNOWN并保留原字节/调用事实。桥重启若不能有据恢复原通道则暂停并按原Engine身份核对/停止，绝不把断管当业务成功或自动新execute。所有活跃通道关闭/封存后共享桥不得按每wait保留进程；等待驻留另由G5验证。

本阶段可做非Docker投影/引用/预算/空证据拒绝控制。真实Node/Pi、只读边界、duplex、限额、freeze/export/stop、共享slot及F规模均仍需要实际已验X/F增量driver和独立外部观察。oracle仅读取外部原件，候选status/pass不产生事实。原正负场景、预算与失败必须保留；缺依赖保持MISSING。
