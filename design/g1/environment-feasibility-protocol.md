# G1 Linux 执行可行性观察（先行协议）

问题：当前WSL Linux是否有可直接用于G2独立实验的用户命名空间、cgroup可见性及既有容器服务？不选择生产隔离产品，不修改系统配置，不安装依赖。

观测：记录 uname、Python、uid/gid，查询 user namespace 配置、cgroup文件，定位 unshare/nsenter/bwrap/prlimit/timeout/docker；执行一次 unshare --user --map-root-user 下的 id，比较宿主uid及子命名空间uid；只读查询已有 docker daemon 的版本与安全/cgroup信息。命令逐个最多10秒，失败原样保留，不反复重试。

预期不是全部成功：某能力成功仅支持该具体实验入口存在；拒绝或不可用进入G2环境准备问题，不能绕过隔离在高权限宿主运行任务。整个观察不证明权限、进程/网络/资源、旧FD撤权或生产部署安全；真实隔离承诺仍需后续反例与环境外观测。
