# AgentFS：数据库文件视图可恢复，版本集合与不回退历史仍须外部契约

状态：G2 限定 SDK 机制实测完成；不是普通 Shell/FUSE 或系统恢复验收。固定 `0a014ebd4918615baff589ed17486e557e7c6a23`，官方 Turso 仓库；实际安装克隆的 Python SDK0.6.4 与其固定依赖 pyturso0.4.4，见 [identity.json](identity.json)。

## 问题与职责

H06/H07/H08：已保存内容是否能由新进程恢复；普通的逐文件变化能否自动成为一致版本；文件回退与已发生外部动作的历史是否分属不同责任。

- [AgentFS.open/open_with](https://github.com/tursodatabase/agentfs/blob/0a014ebd4918615baff589ed17486e557e7c6a23/sdk/python/agentfs_sdk/agentfs.py#L36) 用显式路径打开 Turso 数据库，共用连接初始化 Filesystem、KV、ToolCalls。目录/文件/调用记录是同一 DB 的不同表，不自动构成不同版本域或不可回退 ledger。
- [Filesystem.write_file](https://github.com/tursodatabase/agentfs/blob/0a014ebd4918615baff589ed17486e557e7c6a23/sdk/python/agentfs_sdk/filesystem.py#L357) 解析 inode/dentry，数据分块写入 fs_data，再更新 inode size/mtime 并 commit（L410–443）。SDK 记录真实内容，不只是路径；这些单次写入不能自动表示跨文件的应用一致版本。
- [ToolCalls.record](https://github.com/tursodatabase/agentfs/blob/0a014ebd4918615baff589ed17486e557e7c6a23/sdk/python/agentfs_sdk/toolcalls.py#L209) 保存调用者提供的 name/parameters/result/status 并 commit。它是记录 API，不独立执行或核验外部动作，应用写 success 不能成为 Runtime 权威确认。
- [Rust OverlayFS](https://github.com/tursodatabase/agentfs/blob/0a014ebd4918615baff589ed17486e557e7c6a23/sdk/rust/src/filesystem/overlayfs.rs#L39) 使用只读 base 与可写 AgentFS delta，并有 inode/origin/whiteout 映射。若要用 delta 恢复完整版本，base 内容与身份也必须可获得且固定；只保存 DB 路径不足。
- [Linux CLI sandbox](https://github.com/tursodatabase/agentfs/blob/0a014ebd4918615baff589ed17486e557e7c6a23/cli/src/sandbox/linux.rs#L1) 是 FUSE+mount namespace，不是本批执行的 SDK。它为了 base 访问保留 cwd FD（L13–16），默认可写缓存/config 列表包括 `.claude/.codex/.local`（L55–68）。这些默认目录不应直接成为本系统模型代码的权限范围；需真实句柄和目录适配验证。

## 协议与真实执行

[protocol.json](protocol.json) 已在实验前保存。[experiment.py](experiment.py) 的每次命令都使用真实 SDK 和引擎；研究驱动只负责创建已知文件值、在 SDK 关闭连接后复制 DB、启动新 OS 进程和读取外部 fixture。不自造虚拟 FS 或快照返回值。DB 字节复制是明确标注的停写夹具操作，**不是声称 AgentFS 提供内置 snapshot API**。

复现：`python3 /path/to/loom/research/agentfs/run_experiment.py <新的批次名>`。每一步命令、退出码、原始 JSON/stdout/stderr 和实际 DB 文件保留在 [experiment-001](evidence/experiment-001/run.json)；汇合的对象观察为 [observations.json](evidence/experiment-001/observations.json)。

| 输入/动作 | 新进程与独立对象观察 | 能力边界 |
| --- | --- | --- |
| SDK 写 template=T0、未跟踪 block=B0、artifact=REPORT0；关闭、复制为v0；再改当前内容 | 新 Python 进程打开v0获得三个精确原值，当前库为T1/B1/REPORT1 | 此受管理 DB 范围内内容可恢复；不依赖 Git tracked 集合。 |
| template已写T1，block仍B0 时关闭/复制 | 该副本为 T1/B0/REPORT0，KV input_version 仍R0 | SDK 没有替应用证明这是一组一致输入。需要协调快照边界或受验证事务/版本集合。 |
| v0之后，外部 fixture 发生op1效果，SDK.tools记录op1成功；打开旧v0 | 当前库有工具记录，旧库为空；外部对象计数仍1 | 整库回退会连同工具历史退掉，不能把被回退库本身作为不回退的唯一确认历史。 |

外部效果由研究侧文件独立计数；SDK.tools 的 success 是待对照记录。实验只检验回退时两者的关系，没有模拟 SDK 自动产生了真实远端效果，也不声称查询/幂等能力已解决。

## 可复用组件、缺口与不采纳

- 可复用候选：DB 内文件内容/metadata、版本化资源容器的 SDK 接口、base+delta 的机制设计。独立组件可验证“给定受管理版本集合，完整内容在新环境中可取”。
- H06 适配：Surface/Workspace 的版本身份与允许组合、真实依赖闭包、artifact 固定引用、停写/一致读取边界、base 镜像/目录版本必须明确；本批库复制只证明一个受限场景。
- H07 适配：已发生操作、已接受决定、未知结果责任与回退事件必须保存在不会随工作文件回退而消失的权威记录中；工具数据不能因字符串 `success` 获得确认权。
- H04/H05 适配：若选择 FUSE/ptrace 普通 Shell 路径，需独立验证已有 FD、子进程、mount 逃逸、内核失败和写者交接，不能用 Python SDK 的路径表读写替代。
- 不采纳：整库回退等于外部效果回滚、单 DB/单 HEAD 自动代表一致组合、保存 delta 而不固定 base、把 ToolCalls 表当自行验证的 Runtime 事实。

## 许可与依赖未决项

Python pyproject 声明 MIT，但此固定 checkout 根目录没有 LICENSE/ LICENSE.md，README 的 MIT badge 链接指向不存在的根 LICENSE.md；实际仅有 fuser/nfsserve 的第三方许可文件。记录为**声明可见、完整许可文本/归属需补核**，不把缺文件解释为已获完整生产再分发确认。若采用源码，应先明确 canonical MIT 条款与归属；不因此降低系统范围。SDK 通过 pyturso 原生 wheel 访问数据库，未执行 CLI、FUSE、ptrace、加密、远端同步或断电持久性测试。
