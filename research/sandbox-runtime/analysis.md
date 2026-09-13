# Anthropic Sandbox Runtime：路径强制有效，FD 与旧代撤权需额外边界

状态：G2 限定机制实测完成；不裁定 Runtime 性质通过。克隆源码固定 `c392e6cf9f8df957c66d9ab1461e2cfa99b1ab5d`（0.0.76 release merge）。[identity.json](identity.json) 固定官方身份、源码、依赖与证据。TS 从克隆源码编译；其 git 不含预编译 seccomp helper，实验使用官方 npm 0.0.76 的 x64 helper，单独记录 tarball 与 binary SHA，不声称可重复构建证明。

## 职责、控制与状态

H04/H05：把普通命令包入真实限制环境，不能依赖命令守约；可写对象已有 FD 和存活旧 wrapper 必须另行验证。候选主要承担“生成/配置 OS 运行边界”，没有提供本系统稳定受理、结果持久索引或写者 ownership ledger。

- [Linux wrap 参数与快速路径](https://github.com/anthropics/sandbox-runtime/blob/c392e6cf9f8df957c66d9ab1461e2cfa99b1ab5d/src/sandbox/linux-sandbox-utils.ts#L1773)：没有任何 restriction 时直接返回原 command（L1819）；调用者必须明确所需限制且检查依赖，不能将任意返回字符串视为已隔离。
- [文件系统构造](https://github.com/anthropics/sandbox-runtime/blob/c392e6cf9f8df957c66d9ab1461e2cfa99b1ab5d/src/sandbox/linux-sandbox-utils.ts#L946)：只读 root，再对 allowOnly 路径建立 RW bind；对路径规范化、符号链接、deny/missing path 做处理。状态是生成的 mount 边界，不是每次 write 再查策略记录。
- [PID/user namespace 与 cap 清空](https://github.com/anthropics/sandbox-runtime/blob/c392e6cf9f8df957c66d9ab1461e2cfa99b1ab5d/src/sandbox/linux-sandbox-utils.ts#L2025)：unshare PID/user、fresh proc、cap-drop，正常路径再调用 native apply-seccomp。`enableWeakerNestedSandbox` 是显式降低 proc 边界的选项，本实验没有启用。
- [native helper 生命周期](https://github.com/anthropics/sandbox-runtime/blob/c392e6cf9f8df957c66d9ab1461e2cfa99b1ab5d/vendor/seccomp-src/apply-seccomp.c#L634)：内部 init 处理主 worker 退出；PID namespace 销毁可以终止残留子进程。源码是解释依据；运行的 release helper 二进制另有摘要。
- `sandbox-manager.ts:1956` 的配置更新影响后续包装以及相应服务配置；不应推断文件系统已有 mount/FD 被重新授权。本批直接比较旧/新 wrapper，不把它说成测试了所有 updateConfig 的网络热更新路径。

## 先行协议、输入与实测

[protocol.json](protocol.json) 先登记判据，setup_note 在运行前说明 helper 来源；[experiment.mjs](experiment.mjs) 调用真实 `wrapCommandWithSandboxLinux`，再实际执行它生成的 shell。所有 worker 代码只操作自建三域 fixture 和 /proc 自身状态，环境白名单不包含用户凭据。网络 namespace 无代理，即完全禁网配置；没有流量/代理规则实测，不据此声称完整网络验证。

复现：`python3 /path/to/loom/research/sandbox-runtime/run_experiment.py <新的批次名>`。原始 wrapper、stdout/stderr、退出码与每阶段对象内容在 [stdout.jsonl](evidence/experiment-001/stdout.jsonl)；版本/摘要在 [run.json](evidence/experiment-001/run.json)。Ubuntu 官方 bwrap0.6.1、socat、ripgrep、libwrap 仅解包至项目局部路径，未修改宿主配置。

| 轨迹 | 独立目标侧结果 | 判断 |
| --- | --- | --- |
| Surface allowWrite，尝试写 Surface/Workspace/control/alias | Surface 成功；其余 pathname 写 EROFS。Workspace 配置对称成立 | 两份真实路径强制边界有区分能力，符号链接指向 control 的 pathname 写未绕过。 |
| 同时向启动链显式继承自建 control 文件 fd3 | 两域均可 `os.write(3)`，control 实际出现 FD3；相同控制文件的 pathname 写仍 EROFS | wrapper 不能替启动调用者关闭所有不该继承的可写 FD。需专门的句柄收口契约；不能用 pathname 负例代替句柄负例。 |
| 相同 worker 不经过候选 wrapper | 三域与 alias 都能写 | 确认文件可写、越权负例不是 fixture 本身拒绝一切。 |
| 旧 wrapper 预开 Surface FD；生成不允许该对象的新 wrapper | 新 wrapper 所有 pathname 写被拒；随后旧进程仍经原 FD 写 OLD-FD | 新配置/新 wrapper 不撤销现存旧写者。接管须真实停止/撤权验证，不能仅换配置记录。 |
| 主 worker 退出，后台子进程延迟写 | 受保护进程未写；无保护对照写 ORPHAN-FD | 此 Linux PID namespace 条件下，主退出能清理此有限子进程场景；不推广到允许的域外服务/远程写渠道。 |

实际 worker 为 UID/GID1000，内部 PID2、CapEff=0；每次 mount/user/PID/net namespace ID 及无保护对照均原始记录。UID 相同不意味 namespace 无效，也不意味可以承担两域授权身份的全部职责。实验没有对继承 FD 的漏洞在输出端补值或隐藏失败。

## 组件选择与不采纳

- 可复用候选：Linux command wrapper 的 bind/deny 编排、namespace+seccomp 启动、依赖检查。对应独立组件为“已解析且已授权的执行描述→真实受限命令”，不是全 Runtime。
- 必需适配：启动前 FD/环境/Unix 端点白名单；只允许明确的报告/输出通道；失效身份和未就绪隔离须拒绝；固定执行身份与状态持久查询另由对应组件承担。
- 写者交接组件必须在旧执行者已停止或已失去对当前权威对象写能力后授予新写者；本实测否决“重生成 wrapper / 更新配置即撤权”。
- 不采纳：零 restriction 快速路径作为受限执行的默认成功；将 read-only bind 视为对已打开 FD 的撤销；将共享 Node manager 的声明视为实际权限证明。
- 尚未验证：真实控制端点/网络代理绕行、动态路径替换竞态、恶意跨进程 FD 传递、磁盘/CPU/内存配额、生产目标内核。G3 应在独立夹具中补齐，不删去系统性质以迁就本候选。

## 许可证/依赖

TS 与 native helper 源码为 Apache-2.0。官方 npm tarball 版本0.0.76、完整 npm lock、release helper SHA、Ubuntu 包 SHA/依赖记录在 setup-001。npm ci 关闭 install scripts 后显式 tsc；依赖未获取用户环境。Ubuntu bwrap/ripgrep 等有各自许可证，不将主项目 Apache 声明传播给依赖。选为生产组件时仍需对实际随包分发的依赖/原生 helper 做完整许可与构建来源确认。

## 补充：P05 读取边界（read-002）

先保存 [protocol-read-002.json](protocol-read-002.json)，再运行真实同版本 wrapper，使用两个完全自建 canary，未读取真实凭据。原始证据为 [read-002/stdout.jsonl](evidence/read-002/stdout.jsonl)。writeConfig 为空允许集时，默认 denyOnly=[] 仍能读 PRIVATE-CANARY 与 PUBLIC-CANARY；明确 denyOnly 该目录后两者均不可见（ENOENT）；再 allowWithinDeny 公共子目录后，PUBLIC-CANARY 恢复可读而私密 sibling 仍不可见。三次 worker 正常退出，host 原文件内容未变。

因此可采用范围必须包含显式 read deny/allow 契约：默认 write confinement 不提供 P05 凭据读取隔离。此证据支持静态 canary 目录的选择性遮蔽，不证明所有真实密钥位置、FD、代理端点和路径替换均被覆盖。复现：`python3 research/sandbox-runtime/run_read_experiment.py <新的批次名>`。
