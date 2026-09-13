# OpenSandbox：执行身份、结果索引与停止边界

状态：G2 限定机制实测完成；不是组件或系统通过。固定 `60bca638497d9c50e948928b8b15fe22328afee3`。旧 `alibaba/OpenSandbox` 官方地址确实重定向至 `opensandbox-group/OpenSandbox`，实际重定向、时间和 clone 记录见 [identity.json](identity.json)。

## 问题、职责与源码事实

H02/H04/H05/H08：普通 Shell 以谁的身份执行、完成后何处能按执行身份查询、取消成功是否足以允许下一写者接管、销毁旧执行进程后是否能恢复同一结果。

- 生命周期 control plane 在 `server/`，对 Docker/Kubernetes 分配、停止 sandbox；容器内 `components/execd` 执行命令/管理文件/Jupyter Session。二者状态范围不同，不能把容器存在视为某次命令完成。
- [Controller 与分派](https://github.com/opensandbox-group/OpenSandbox/blob/60bca638497d9c50e948928b8b15fe22328afee3/components/execd/pkg/runtime/ctrl.go#L36)：command、bash、PTY、isolated Session 各有内存 map；`Execute` 选择后端。普通 command 后端并不自动成为 namespace 受限环境。
- [真实 credential 与命令启动](https://github.com/opensandbox-group/OpenSandbox/blob/60bca638497d9c50e948928b8b15fe22328afee3/components/execd/pkg/runtime/command.go#L104)：uid/gid 转为 `syscall.Credential`；同实际身份可免切换，其他身份需真实能力。后台命令以 `Setpgid` 启动（L402），候选先同步登记 commandKernel 再返回（L443），有利于消除受理后立即查询的内存竞态。
- [查询](https://github.com/opensandbox-group/OpenSandbox/blob/60bca638497d9c50e948928b8b15fe22328afee3/components/execd/pkg/runtime/command_status.go#L41)：`GetCommandStatus` 和输出 tail 都先找内存 kernel。stdout 文件在 `os.TempDir()/command-output…`，具体路径构造见 `command_common.go:95–118`。这不是独立于进程的 execution ledger。
- [Interrupt](https://github.com/opensandbox-group/OpenSandbox/blob/60bca638497d9c50e948928b8b15fe22328afee3/components/execd/pkg/runtime/interrupt.go#L54)：向负 PID 的进程组先 TERM 后 KILL，最终存活探测是 best effort；注释明确信号已发出后异步 teardown 不一定作为失败。该返回不能直接充当“全部旧写能力已消失”证据。

最新源码还有更强、不同的 `IsolatedRunner`，本研究没有用普通 command 的失败代替对它的结论：[LifecycleIsolator](https://github.com/opensandbox-group/OpenSandbox/blob/60bca638497d9c50e948928b8b15fe22328afee3/components/execd/pkg/isolation/isolator.go#L157) 先获得 host-visible PID、start-time 与 namespace identity，`MarkReady` 才释放 workload；注释明确此身份本身不创建 cgroup 或固定 namespace。[DeleteIsolatedSession](https://github.com/opensandbox-group/OpenSandbox/blob/60bca638497d9c50e948928b8b15fe22328afee3/components/execd/pkg/runtime/isolated_session_ctrl.go#L693) 在 teardown 超时或 FS 操作未排空时保留 map 与 upper 责任，比普通 Interrupt 更接近 H05；但删除成功后也删除该 session 的 run 记录。`bwrap_linux.go:127–140` 明确 `CommitSupported/DiffSupported/PersistAvailable=false`；`config.go:119–128` 默认 hardening/Landlock/eBPF 关闭。不能从存在 Overlay/Commit 名称推断已经有 H06/H08 恢复方案。

## 先行协议与实际实验

[protocol.json](protocol.json) 在运行前登记。`experiment.go` 直接导入固定源码 `pkg/runtime`；没有替代 Controller 或造理想执行器。Go 1.27.1、CGO=0，WSL Ubuntu ext4；所有命令及 TMPDIR 指向自建 fixture，子进程仅得到安全环境。Jupyter/SQL/容器平台未运行，不归入被验范围。

复现：`python3 /path/to/loom/research/opensandbox/run_experiment.py <新的批次名>`。脚本只接受新 evidence 目录；先编译真实依赖，再执行研究程序，并以另一个 OS 进程查询原执行身份。日志在 [experiment-001](evidence/experiment-001/run.json)，提取自原始 stdout 的可读观测在 [observations.json](evidence/experiment-001/observations.json)，完整构建输出及 `go version -m` 均保留。

| 实际操作 | 对象/进程侧观察 | 可支持的判断 |
| --- | --- | --- |
| 请求当前 uid/gid，执行 `id -u` 并写文件 | 实际 uid=1000，文件为 IDENTITY，执行 ID 查询 finished/exit0 | 支持普通 command 使用实际 OS 身份；不证明两域授权路由。 |
| 请求 uid0，写 elevated | OS 拒绝切换、错误 hook 报 EPERM，文件没有产生；`Execute` 的 Go error 仍为空 | 必须消费命令状态/错误事件，函数 nil 返回不能充当执行成功。 |
| 后台执行并按候选生成 ID 查询 | 实际文件 REAL-RESULT，tail 为 RAW-RESULT，状态 finished | 同活 Controller 可查询关联结果。 |
| 退出旧程序，新 OS 进程构造 Controller 后查询原 ID | `command not found`；旧输出文件仍在 fixture TMPDIR | 单靠此命令后端不能满足进程死亡后的结果身份恢复；需要受理/结果关联的持久设施。 |
| 普通子进程预开 FD 后 Interrupt | 返回 nil 后触发写，原文件保持 ORIGINAL | 此有限普通进程组对照被终止。 |
| 子进程 setsid 并孤儿化、预开 FD 后 Interrupt | 返回 nil、主 command running=false，子写者仍写入 LATE-FD | 仅以普通 command Interrupt/主进程状态作 H05 完成门禁会错误交接。 |

子进程 ready 记录包含实际 PID/PPID/PGID/SID，停止后的内容由研究驱动在对象端读取，不由候选日志自述填充。

## 可复用边界、适配与不采纳

- 保留：普通 command 的真实 uid/gid、后台同步登记、输出游标接口可做独立执行适配候选；其调用与反馈必须封装完整，持久关联不能依赖内存 map。
- 保留为待独立实测：IsolatedRunner 的 ready gate、workload 身份和 teardown 排空责任。G3 若拟采用，应先把 native gate、namespace pins、继承 FD、子进程与 cgroup 的失败路径作为独立组件验证；本批没有验证这些能力。
- 不采纳：把普通 command 后端当双 Shell 隔离器；把 Interrupt nil、主进程 finished 或文件仍在等同于整个执行树撤权/结果可恢复；把此版本 Phase2 的 commit/persist 接口作为已有版本恢复能力。
- 与 SRT 同属 Linux namespace/进程生命周期机制族，不能把不同包装计为两种独立内核隔离证明。生命周期控制与持久任务责任仍是两个不同待验证边界。

## 许可证与依赖

被测模块 Apache-2.0，完整 LICENSE 在固定仓库；本项目适配、分发须保留上游版权/NOTICE/许可证义务。直接依赖和 replace 见 identity 的 go.mod/go.sum 摘要，实际链接模块见 `evidence/experiment-001/build-module-versions.txt`。没有执行容器平台、eBPF 或 Jupyter。更强后端的原生 helper、内核能力和第三方组件另核；本实验不构成生产权限/资源限制或持久性验收。
