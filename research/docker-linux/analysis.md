# Linux容器：作为普通进程取消与SRT wrapper的机制对照

此专题来自G1 H04/H05及独立复跑发现的旧FD/资源边界缺口，属于原调研清单保留的OCI/Linux既有设施依据，不增加一个Agent框架。protocol.json先保存五项待检验问题、有限负载与停止条件，再实现并运行实验驱动。固定Linux Engine28.0.1、containerd1.7.25、runc1.2.4；当前daemon由Docker Desktop提供Linux engine，未来产品只依赖Linux Engine API，不使用Windows路径/PowerShell/NTFS。此环境事实不等于独立生产主机已验证。

## 运行与对象证据

evidence/run-001的11项机制检查全部满足，7个唯一ID的实验容器均已清理；该批并非完整符合原停止条件，见下述DOCKER-R01。固定python3.12-slim digest见protocol/image-inspect。每容器uid/gid1000，rootfs只读、capabilities全部丢弃、no-new-privileges、network none、128MiB memory=swap、pids32、CPU0.5、tmpfs16MiB；这些数字只为限制探索实验的破坏范围，不是系统SLA。实际cgroup文件、进程状态、Docker inspect与stdout均保存。

WSL原生ext4文件直接bind到/work后，标记原文一致、授权写在主机同一对象上出现；未把docker cp冒充直接文件接口。未挂载控制目录和Docker socket，符号链接到主机canary不能读/写；原canary不变。域外路径、只读rootfs写失败；FD3/4/5均EBADF，TEST-NET地址连接ENETUNREACH，CapEff为0。此网络测试只是关闭网络配置，不宣称已实现任意网络白名单。

真实子进程setsid再孤儿化，预先打开/work/object FD，以原子rename发布完整ready。负对照触发后出现LATE-FD。正例对完整container ID发kill并wait，然后才触发，文件保持ORIGINAL。另起可信只读host-PID观察器，扫描仅匹配该旧PID namespace的/proc条目：kill前实际3个进程，kill后0个。观察器不进入生产模型环境、不读取任何宿主命令行、environ或秘密；它独立于被验worker，实际进程消失和对象不再写共同支持有限终止结论。

资源限制不仅来自配置：实际fork尝试在48次界限前收到EAGAIN；192MiB有界分配在128MiB限制下OOMKilled、exit137，before-allocation日志保留，未输出分配成功。CPU quota/period实际比值0.5。未测磁盘quota/IO饥饿或并发吞吐，不能将这些检查当完整破坏半径或规模验收。

当前daemon默认seccomp unconfined；实验没有继承此默认。明确加载官方moby v28.0.1 profile，容器/proc状态显示Seccomp2/NoNewPrivs1。配置JSON与根Apache2许可证来自固定版本官方仓库，下载地址/摘要见source-provenance.json，LICENSE.moby随副本保存。Docker/containerd/runc/基础镜像是外部运行依赖，各自第三方许可不能以单一Apache声明覆盖；G3发行清单须分别列出。

## 比较与下一层边界

OpenSandbox普通Controller、Daytona SessionService的取消针对进程树/组，本轮逃逸子进程仍持FD；没有由此否定它们未运行的隔离/容器后端。SRT真wrapper可实施双域路径/命名空间，但显式继承FD、旧wrapper和默认宿主读范围仍需外层处理，资源限制另需设施。Docker进程namespace和cgroup生命周期提供一种现成可组合机制，复杂平台API/编排不必全部引入。

拟作为G3双域执行器的首选候选，而非已通过的组件：还需稳定执行身份/内容绑定、启动与返回丢失后的原ID查询、保留输出到引用、cancel请求与actual stop分开、共享域写锁、创建前路径/挂载对象竞态、环境版本重建、期限和资源预算、socket范围授权、OOM/超时/子进程故障及日志存储上限的独立验收。单个容器成功不能替代这些交接。

威胁范围是受约束但可能错误/越权的普通任务代码；Linux内核、容器运行时和Runtime管理员在信任边界内。未证明内核漏洞、恶意管理员或Docker daemon攻破隔离。正式系统必须检测所需Linux内核/资源能力并在缺失时拒绝启动，不回落到宿主Shell。

复跑：python3 research/docker-linux/experiment.py NEW_BATCH。官方机制依据：[run](https://docs.docker.com/engine/containers/run/)、[resources](https://docs.docker.com/engine/containers/resource_constraints/)、[kill](https://docs.docker.com/reference/cli/docker/container/kill/)、[seccomp](https://docs.docker.com/engine/security/seccomp/)。声明、实际观测与拟采用推断已分别标注。

## 独立审查发现DOCKER-R01

原protocol停止条件误写最多1个并发容器，但K3可信观察器需与活writer共存，实际最多2个、每个128MiB。独立审查明确指出这是原数值边界违约，不能以机制断言通过掩盖。保留protocol和run-001原样，protocol-amendment-002给出独立于运行成败的观察需求依据，面向后续运行明确2个/合计256MiB界限，其余边界不改；修订不追溯让旧批合规。
