# macOS 宿主基座（Linux VM appliance）调研记录

**整理日期：2026-09-15**
**状态：正式调研（2026-09-15 同日完成在线核对与钉定，见 §7）；判据 V1–V4 未执行，源码审查与运行实验后置，V1–V4 通过前不进入安装器装配流程（用户 2026-09-15 指令）。**
**决策背景：** 用户 2026-09-15 确认原则——不重复造 sandbox/VM 底座轮子，macOS 宿主基座复用成熟 VM appliance；自研 VZ 应用仅作为后期演进项记录，不作为当前路线。

## 1. 问题定义

产品部署要求 macOS 宿主提供与 Linux 宿主同构的运行时物理事实：

- F 组件的 `renameat2 RENAME_EXCHANGE` 发布边界（`lore_files/install.py`，含同文件系统检查）与宿主侧文件监视（`lore_files/window.py`，当前仅 Linux inotify 实现）；
- X profile 钉死的 Docker Engine 28.0.1、镜像 digest 与 seccomp 摘要（`lore_execution/profile.json`）；
- 固定 volume 路径（`/var/lib/docker/volumes/...`，`scripts/lore_batch.sh` 依赖）与 `/proc`/cgroup 物理判据。

现状（Docker Desktop）中后三项为耦合副作用：Engine 版本随 Desktop 浮动、volume 在 VM 内不可钉、物理判据不可复现（X001/X031/X033 先例，validation-status 已记录）。业界在 macOS 上运行 Linux 运行时的成熟形态均为**自带 Linux VM appliance**，非本项目发明。

## 2. 候选身份登记（版本待钉定）

> 2026-09-15 在线核对后钉定结果见 §7；下表"钉定版本"列保留原文（待钉定）作为历史记录。

| 候选 | 仓库/来源 | 定位 | 与本项目的关系 |
| --- | --- | --- | --- |
| Lima | [lima-vm/lima](https://github.com/lima-vm/lima) | **主候选**。Finch 与 Rancher Desktop 的共同底座，开源 | 基座复用对象：钉死内核与 appliance 版本、VM 内 dockerd、docker.sock 挂载、共享目录语义 |
| AWS Finch | [runfinch/finch](https://github.com/runfinch/finch) | Lima 的生产化封装（Amazon 官方） | 证明"复用 Lima + 自有安装/钉定层"是可生产化路线；研究其安装器与镜像钉定组织 |
| Podman machine / podman-machine-os | [containers/podman](https://github.com/containers/podman) | Red Hat 的 appliance 化容器运行时 | appliance **版本化与升级模型**先例（升级=重新验证的既有组织方式）；Apple VZ/libkrun 后端选型参考 |
| Docker Desktop | 官方文档（商业闭源） | 形态参照（非代码候选）；当前开发模式的事实底座 | 其版本浮动与物理判据不可复现，是"继续依赖"不成立的直接依据 |
| Apple Containerization framework | [apple/container](https://github.com/apple/container)、[Virtualization.framework 文档](https://developer.apple.com/documentation/virtualization) | 系统级新变量 | "每容器一个轻量 VM"模型**不提供 Docker Engine**，与 X profile 钉死 Engine 28.0.1 冲突；登记为未来 X 后端可评估项，采纳即"换 Engine"，须按修订记录流程重新验证 |

## 3. 声称级观察（全部待核实，不作为结论）

以下为调研计划输入，均来自维护方公开材料的一般认知，未经本轮在线核对与源码审查：

- Lima 支持 QEMU 与 Apple Virtualization（VZ）两种后端，VZ 路线支持 arm64 原生加速与 Rosetta x86 转译【声称级】；
- Lima 通过 YAML 模板定义 VM，可固定镜像与版本，但默认配置随版本浮动，钉定需显式锁定模板与镜像 digest【声称级】；
- virtiofs/FUSE 挂载历史上对 `renameat2` flags（RENAME_EXCHANGE）与 inotify 支持不完整或随内核版本变化【声称级，核心风险】；
- podman-machine-os 独立发版，appliance 升级与宿主 CLI 版本解耦【声称级】。

## 4. 待验证判据草案（substrate 协议预登记输入）

三项物理事实决定 macOS 基座能否承载完整 Runtime，须在钉定版本的 VM 套件内按预登记协议实测（沿用 X001/X031 的 oracle 与判据边界惯例）：

| # | 判据 | 方法要点 | 失败时的后果与备选 |
| --- | --- | --- | --- |
| V1 | `RENAME_EXCHANGE` 在共享挂载上可用且原子 | 在 Surface/Workspace 共享目录执行 F 发布路径，核对 `install.py` 检查链与 errno 记录 | 若不可用：发布边界改为 VM 内暂存区 + 单次 rename 原子换入（须修订 F 契约并重验证），或评估容器卷驱动替代 |
| V2 | inotify 事件在共享挂载上完整送达 | window.py 观察者在 VM 内监视共享目录，宿主侧写入固定事件序列 | 若不可用：监视根移入 VM 内（输入经同步边界进入），或登记 F 的 Darwin/共享挂载限制并缩小声明范围 |
| V3 | 共享目录 `dev/ino` 跨 VM 重启稳定 | 固定文件集在 VM 生命周期前后比对 manifest 物理身份 | 若不稳定：依赖树与状态目录全部移入 VM 磁盘内（仅 Surface 交付物经同步边界输出），manifest 绑定 VM 内路径 |
| V4 | Engine 28.0.1 与镜像 digest 在 VM 内可钉定 | 按 `lore_execution/profile.json` 预检 Engine 版本与镜像身份 | 随套件钉定，预期通过；失败即回到候选选型 |

**arm64 前置修订（不属 V 批次，须先走修订记录）：** 现有钉死镜像 digest 为 amd64 形状；Apple Silicon 宿主需 per-arch digest 表或 Rosetta 方案，二者都改变 X profile 钉定内容，按修订记录处理并重跑相关批次。Rosetta 模拟改变物理判据形状，倾向 per-arch digest 表。

## 5. 自研与复用边界（用户原则的落位）

- **复用（不造轮子）**：VM 套件与生命周期（Lima 或等价）、Linux 内核、Docker Engine、NATS、Git、文件同步/共享层。
- **必须自建（市面无对应物，属项目核心价值）**：deps 树 manifest 物理身份在目标基座上的再生成、宿主预检与装配验证 probe、基座钉定配置（kernel/Engine/digest 与 V1–V4 判据的绑定）。
- **明确不采纳（当前）**：自研 VZ appliance 应用（工程量大且无证据支撑必要性）；Apple Containerization 作为 X 后端（换 Engine 须重验证，仅登记）；Rosetta x86 模拟承载验证批次（物理判据变形）。

## 6. 交付口径与后续步骤

按 §9 交付口径，本方向完成后须留下：候选钉定版本与许可核查、V1–V4 可复现实验及结论、可复用模块与接口位置（Lima 模板驱动、appliance 构建链）、不采纳理由存档。

1. 联网核实候选身份与当前版本，补钉定 commit（本记录升级为正式调研）——**已完成（2026-09-15，§7）**；
2. 起草 substrate 验证协议（V1–V4 + arm64 修订），按项目惯例预登记批次与停止条件——**已起草**：[substrate-verification-protocol-2026-09-15.md](substrate-verification-protocol-2026-09-15.md)（叙述）与 [validation/substrate/protocol-substrate-001.json](../../validation/substrate/protocol-substrate-001.json)（预登记批次），V1–V4 均未执行；
3. 产出最小 Lima 套件草案（钉定模板）——**已起草（DRAFT/UNVERIFIED）**：[scripts/substrate/lima/](../../scripts/substrate/lima/README.md)，仅在 V1–V4 通过后进入安装器装配流程。

## 7. 2026-09-15 在线核对与钉定（本轮正式调研增补）

**核对方式与边界：** GitHub REST API 限流（HTTP 403，与 2026-09-15 执行平台调研同因）；版本钉定改用 `git ls-remote` 直连观测 refs（含 annotated tag 的 peeled `^{}` commit，强于 releases/latest HTML 页）+ `releases/latest` 重定向页交叉确认"最新发布"语义；Lima v2.2.0 另做 `--depth 1 --branch v2.2.0` 浅克隆并 `rev-parse HEAD` 与 peeled commit 一致（de0816ea…）。文档级声称取自 lima-vm.io 官方文档与 GitHub issue 原件。全部为**观测日 2026-09-15 的钉定值**，不外推为"长期最新"。以下为钉定结果，替代 §3 的待核实状态；§3 原文保留作历史声称记录。

### 7.1 候选身份钉定

| 候选 | 最新发布（releases/latest 重定向，2026-09-15 观测） | commit（git ls-remote 观测） | 备注 |
| --- | --- | --- | --- |
| **Lima** | v2.2.0（另有预发布 v2.3.0-beta.0，不钉定） | tag object `867a7134…`，peeled commit `de0816ea4bdc5267b428ab21025889b8dd785526`（浅克隆 rev-parse 一致） | 主候选钉定对象 |
| **AWS Finch** | v1.17.2 | `c0f8e88c60793fa0a92030136c2281bdbf06683c` | 其 go.mod（tag v1.17.2）钉 `lima-vm/lima v1.2.3` + `lima-vm/lima/v2 v2.1.3`——**不跟随 Lima latest**，是"appliance/封装层与 Lima 版本解耦"的直接先例 |
| **podman-machine-os** | v6.1.2 | tag object `633c9a52…`，peeled commit `0a7a56040f65c42d666fd13df2e9afbb6bfce0c0` | **组织迁移观测**：`containers/podman-machine-os` 重定向至 `podman-container-tools/podman-machine-os`（引用其 release 时以迁移后 org 为准） |
| **apple/container** | 1.4.1 | `9a8917ca2da5cd6ba059b9ba5ca5a74892e9bb7d`（轻量 tag） | 登记项，未采纳（§5） |
| Docker Desktop | 形态参照，非代码候选，不钉定 | — | 其 release 节奏即"版本浮动"问题本身（profile.json platform_revision 已记录） |

### 7.2 Lima 官方文档核实（lima-vm.io，2026-09-15 观测）

| §3 原声称 | 核实结果 | 来源 |
| --- | --- | --- |
| QEMU 与 VZ 双后端；VZ 支持 arm64 原生加速与 Rosetta x86 转译 | **文档确认**：vz 自 Lima v1.0 起为 macOS 默认后端，要求 macOS ≥ 13；Virtualization.framework **不支持跨架构**（intel-on-arm / arm-on-intel 均不可）；Rosetta 为 vz on ARM 的"fast mode 2"（`rosetta.enabled/binfmt`；AOT 缓存需 Lima ≥ 2.0 + macOS ≥ 14）；跨架构全系统 VM 仅 QEMU"慢模式" | vmtype/vz、multi-arch 文档 |
| YAML 模板可固定镜像与版本；钉定需显式锁定 | **文档确认 + 模板实测**（v2.2.0 浅克隆直接读取）：`templates/_images/*.yaml` 对 per-arch 镜像 URL 附 digest；但 `templates/docker.yaml` 的 Engine 安装用 `get.docker.com`（**Engine 版本浮动**）——复用该模板必须替换为钉定 apt 包安装 | mount 文档、仓库模板 |
| virtiofs/FUSE 对 `renameat2` flags 与 inotify 支持不完整（核心风险） | **获得两条直接相关的声称级证据**：(1) Lima 官方：`mountInotify` 为**实验性**（≥ 0.21），机制是 hostagent 收集宿主 inotify 转发进 guest，已知缺口——9p 下监听目录的嵌套文件不触发、**宿主删除文件不触发事件**；(2) [docker/for-mac#7687](https://github.com/docker/for-mac/issues/7687)：**AVF + VirtioFS + bind mount 上 `renameat2(RENAME_EXCHANGE)` 造成数据丢失**（named volume 正常），state=OPEN（created 2025-05-28，观测时未解决）——比"报错"更凶险的静默损坏形状，V1 判据必须含交换后内容等值校验（`install.py` 的 walk 比对链已覆盖此形状，探针必须同样包含） | mount 文档、issue 原件 |
| podman-machine-os 独立发版 | **确认**（§7.1，v6.1.2，独立仓库/tag 线） | releases/latest |

**新增模板/池事实（套件钉定输入，2026-09-15 观测）：**

- Lima v2.2.0 `templates/_images/ubuntu-24.04.yaml` 钉定 noble `release-20260705` server 镜像 per-arch digest：amd64 `sha256:ffe6203da54deeb6db5d2a98a83f9ec8e55f149d3f7ba622e1abe5fa966ee3d6`、arm64 `sha256:7df0201546f75b8bcc1044594c806c35749421ad3c9bc1be2a3ab806cfae39cc`（另有 minimal 变体与 fallback 无 digest 条目——**套件模板只允许带 digest 条目**）；`ubuntu-lts` 现指 26.04 resolute。
- Docker apt 池：`docker-ce_29.1.3-1~ubuntu.24.04~noble_{arm64,amd64}.deb` 在 noble pool **两种架构均在**；resolute (26.04) pool **无** 29.1.3 → 套件 guest 选 **Ubuntu 24.04（noble）**，Engine 钉 `docker-ce=29.1.3`（与 `lore_execution/profile.json` 当前 `engine_version: 29.1.3` 一致；28.0.1 为该文件 `previous` 保留的修订前值）。
- profile.json 已于 2026-09-14 平台重定位为 arm64（Docker Desktop 29.1.3）且 python digest 引用 `sha256:78387bc3…` 未变——这是"该 digest 在 arm64 可用"的间接证据；**manifest list 形状（含 arm64 条目）留给 V4 批次实测确认**，不在文档级断言。

### 7.3 核对来源（2026-09-15 观测）

[34] [Lima releases/latest → v2.2.0](https://github.com/lima-vm/lima/releases/tag/v2.2.0)；[35] [Lima Filesystem mounts 文档](https://lima-vm.io/docs/config/mount/)（mount 类型/默认值/mountInotify 实验性与缺口）；[36] [Lima VZ 文档](https://lima-vm.io/docs/config/vmtype/vz/)；[37] [Lima multi-arch 文档](https://lima-vm.io/docs/config/multi-arch/)（Rosetta fast mode 2；QEMU 慢模式）；[38] [Lima v2.2.0 仓库浅克隆](https://github.com/lima-vm/lima/tree/v2.2.0)（`templates/docker.yaml`、`templates/_images/ubuntu-24.04.yaml`、`templates/_default/mounts.yaml`，HEAD=de0816ea…）；[39] [Finch releases/latest → v1.17.2](https://github.com/runfinch/finch/releases/tag/v1.17.2) 与其 [go.mod@v1.17.2](https://github.com/runfinch/finch/blob/v1.17.2/go.mod)；[40] [podman-machine-os releases/latest → v6.1.2](https://github.com/podman-container-tools/podman-machine-os/releases/tag/v6.1.2)（containers/ → podman-container-tools/ 迁移重定向）；[41] [apple/container releases/latest → 1.4.1](https://github.com/apple/container/releases/tag/1.4.1)；[42] [docker/for-mac issue #7687](https://github.com/docker/for-mac/issues/7687)（AVF+VirtioFS `RENAME_EXCHANGE` 数据丢失，OPEN，created 2025-05-28）；[43] [download.docker.com linux/ubuntu dists](https://download.docker.com/linux/ubuntu/dists/)（noble/resolute stable pool 文件列表，docker-ce_29.1.3 noble arm64+amd64 在池、resolute 不在）。

**版本钉定方法备注：** 以上 commit SHA 来自 `git ls-remote` 直连观测（annotated tag 记 tag object 与 peeled commit 两者）；HTML/API 页未取得 SHA 不影响钉定。克隆执行前须以 `git rev-parse` 复核 `de0816ea…`，不一致即停止（协议批次前置身份门禁）。
