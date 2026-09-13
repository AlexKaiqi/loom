# Daytona 最后公开实现：命令 Session 与 sandbox 生命周期须分开

状态：G2 历史公开源码机制实测完成；不包含现商业能力，也不裁定组件通过。主研究版本为 `v0.190.0 / 01c502bb1f1ff8f2885d0cd490e043736083dca8`（2026-06-23）。固定身份见 [identity.json](identity.json)。

## 版本选择与公开范围

当前 main `ec4c21b2d597091ac09ecc278f3bcc172575a987`（2026-06-25）只剩 README/assets；[该固定归档说明](https://github.com/daytonaio/daytona/blob/ec4c21b2d597091ac09ecc278f3bcc172575a987/README.md) 明确 June2026 core moved private，许可链接指向 v0.190.0。故选择它指向的最后公开 AI sandbox 实现，没有将当前网站的专有隔离/快照承诺当作本批能力。

首轮发现曾取 v0.53.0（2025-02-07，`dfb50e8a…`）；该版围绕 workspace/target、开发环境和 agent toolbox。较近公开版本已经拆为 NestJS API control plane、runner compute plane、daemon toolbox/session、snapshot-manager、SDK。旧版本只作为职责迁移记录保留，**未用较旧且易跑的实现冒充2026候选**。两次 fetch/checkout、标签原始输出均在 discovery-001。

## 职责、状态与调用链

H02/H05/H08：候选 Session 接受命令后保存何种身份/结果，进程退出与删除分别带走什么，Delete 是否足以证明全部旧写能力消失。

- [SessionService](https://github.com/daytonaio/daytona/blob/01c502bb1f1ff8f2885d0cd490e043736083dca8/apps/daemon/pkg/session/service.go#L14) 的 session/command 索引位于内存 concurrent-map；configDir 保存每条 command 的脚本、log、exit_code。
- [Create](https://github.com/daytonaio/daytona/blob/01c502bb1f1ff8f2885d0cd490e043736083dca8/apps/daemon/pkg/session/create.go#L22) 创建真实 shell、继承 daemon 环境、Setpgid；此层不分配独立 uid/namespace，权限来自外层实际环境，不能直接当双 Shell 授权器。
- [Execute](https://github.com/daytonaio/daytona/blob/01c502bb1f1ff8f2885d0cd490e043736083dca8/apps/daemon/pkg/session/execute.go#L23) 支持指定 command ID；已存在 ID 一律冲突，不比较内容后复用。wrapper 先等 labeler 刷完 log 再写 exit_code，避免已完成状态早于输出可读；这是有价值的有限保存顺序。
- [GetSessionCommand](https://github.com/daytonaio/daytona/blob/01c502bb1f1ff8f2885d0cd490e043736083dca8/apps/daemon/pkg/session/command.go#L39) 先查内存 session/command，随后读 exit_code。仅保存物理 log 不足以让新 service 查询同 ID。
- [Delete](https://github.com/daytonaio/daytona/blob/01c502bb1f1ff8f2885d0cd490e043736083dca8/apps/daemon/pkg/session/delete.go#L18) 向进程组与可枚举树发信号；即使 terminate 返回错误也继续清理目录与 map。其 waitForTermination 观察 parent/children，不能覆盖已经脱离树且保持 FD 的进程。
- 更外层 [runner Docker Stop](https://github.com/daytonaio/daytona/blob/01c502bb1f1ff8f2885d0cd490e043736083dca8/apps/runner/pkg/docker/stop.go#L15) 是另一条链：ContainerStop/Kill 后 ContainerWait(NotRunning)；API sandbox service 使用 state/desiredState 等持久控制对象。**本批没有运行这个容器停止后端，daemon Session 的失败不等于整个 sandbox Stop 的失败**。它的容器边界/独立内核以及 snapshot 能力仍需对应后端实测。

## 先行实验与原始结果

[protocol.json](protocol.json) 在实验前保存；[experiment.go](experiment.go) 直接导入固定源码 `apps/daemon/pkg/session`，并由真实 shell/Python 子进程写自建对象。没有替代 SessionService、进程树或文件返回值。使用 root 已验证的原生 Go1.27.1，原 go.work 本地模块、局部模块/编译缓存，CGO=0。本实验使用局部工具，不改现有宿主配置；没有执行上游开发说明中的 Nix/direnv 全局配置。

复现：`python3 /path/to/loom/research/daytona/run_experiment.py <新的批次名>`。完整命令、退出码、构建日志、stdout/stderr、物理日志/文件在 [experiment-001](evidence/experiment-001/run.json)，由 raw 提取的 [observations.json](evidence/experiment-001/observations.json) 便于逐事件检查。

| 轨迹 | 原始观察 | 对本系统的影响 |
| --- | --- | --- |
| Create persist → Execute command-1 → GetSessionCommand | 实际 uid1000、产物 REAL-RESULT、stdout RAW-RESULT、原 ID exit0 | 同活 service 能关联命令/产物。 |
| 相同 ID 相同内容重交，再相同 ID 不同内容重交 | 两者都 conflict | 不能原样承担“同内容复用、异内容冲突”的受理契约；需要持久幂等适配。 |
| 退出旧程序，另一个 OS 进程使用同 configDir 新建 service 查询 | session/command not found，但原 physical log 和产物仍在 | SessionService 本身没有按落盘结果重建索引；需要独立结果/责任恢复机制。 |
| 正常 child 已开 FD，Delete 后触发写 | Delete nil，文件保持 ORIGINAL | 此有限正常进程树停止对照成立。 |
| child setsid 并孤儿化、预开 FD，Delete 后触发写 | Delete nil，API已无法查 session，但文件出现 LATE-FD | 删除逻辑记录与失去写能力并不等价；不可用此 Delete 返回作为新写者接管门禁。 |

被测子写者的 ready JSON 保存了 PID/PPID/PGID/SID；对象内容由研究进程读取。全部不利结果保留，未把错误当成 SDK 使用姿势问题而删例。

## 可复用与不采纳

- 保留机制：每命令日志/exit 标记的顺序，显式 command ID、stdout/stderr demux；可作为局部执行适配参考。正式组件需验证崩溃切点和完整归属，不能仅复用 SessionService 的内存索引。
- 保留待测后端：runner 的 ContainerWait、snapshot-manager/volume 对持久环境的分工；若采用，应以独立容器、挂载和效果端观察验证，不从本 batch 的源码阅读升级为通过。
- 不采纳：同名 command 一律冲突替代稳定受理复用；Session Delete 成功即全树失权；从物理 log 存在推断新 daemon 原身份可查询；把当前云产品的私有能力补进历史代码结论。
- 与 OpenSandbox 普通 command 的对比揭示共同缺口：进程内执行登记≠持久请求 ledger；进程组/树杀除≠对已经脱离树的写渠道强制撤销。可独立组件应该按这两种职责拆分或选择更强整体后端，而非再套一层相同语义包装。

## 许可证与依赖

被测 daemon/core 文件 SPDX 为 AGPL-3.0，根 LICENSE 为 AGPLv3。部分 SDK/client 目录单独 LICENSE，不能把它们的许可扩展到 daemon。当前不选择直接拷贝该核心代码；保留机制参考和可独立验证接口。若未来采用/修改/分发或网络提供该代码，先按精确使用方式核对 AGPL 义务；不能按“研究开源可运行”推导所有使用方式无条件可用。实际链接模块版本在 build-module-versions.txt；NestJS/数据库/Redis/Docker/snapshot运行服务未启动，许可与机制债务按拟采用范围另核。
