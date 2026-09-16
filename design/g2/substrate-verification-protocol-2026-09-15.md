# macOS 宿主基座（substrate）验证协议：V1–V4 预登记批次

**起草日期：2026-09-15**
**状态：预登记草案（batches NOT EXECUTED）。本文件与机器可读预登记 [validation/substrate/protocol-substrate-001.json](../../validation/substrate/protocol-substrate-001.json) 共同构成批次判据；判据先于批次执行，执行中不得修改。**
**来源：** [macos-host-substrate-survey-2026-09-15.md](macos-host-substrate-survey-2026-09-15.md) §4（判据草案）与 §7（在线核对与钉定）；F 契约 `lore_files/`（`install.py` renameat2 RENAME_EXCHANGE 检查链、`window_linux.py` lease+inotify 观察窗、`util.identity()` dev/ino）；X 契约 `lore_execution/profile.json`（engine_version、镜像 digest、seccomp 摘要、volume 路径）与 `lore_execution/engine.py` 预检。判据来源是 POSIX 系统调用语义、F/X 契约文本与上游官方文档，不调用被测套件生成预期。
**用户指令（门禁）：** V1–V4 全部 PASS 之前**不进入安装器装配流程**——避免在未验证的共享目录语义上堆上层工作。

## 1. 被验问题与证据层级

在 macOS 宿主 + 钉定 Linux VM appliance 上，三项物理事实与一项钉定能力决定该基座能否承载完整 Runtime：

1. F 发布边界依赖的 `renameat2 RENAME_EXCHANGE` 在共享挂载上可用、原子且内容无损（[docker/for-mac#7687](https://github.com/docker/for-mac/issues/7687) 已给出同族实现"静默数据丢失"的反例形状）；
2. F 稳定观察窗依赖的 inotify 事件能从宿主侧写入完整送达 VM 内观察者（Lima `mountInotify` 为实验性且有文档记录的缺口：宿主删除不触发、9p 嵌套文件不触发）；
3. 共享目录的 `dev/ino` 物理身份跨 VM 生命周期稳定（deps 树 manifest 身份再生成策略的前提）;
4. X profile 钉定物（Engine 版本、镜像 digest、seccomp 摘要、固定 volume 路径）在 VM 内可复现钉定。

**证据层级：** 本协议属 G2 定向调研实验（候选机制验证，按 [evidence-guide](../../governance/evidence-guide.md) §3 允许预登记为正式批次）。通过结论的范围是"钉定基座上这些物理事实成立"，**不等于** R/E/F/X 组件在基座上的组合验收，更不等于系统验收；组件进入基座后的重验批次另行预登记。批内观测在 VM 内真实 Linux 内核上进行（/proc、cgroup、inotify、renameat2 均为本机观测，无 Docker Desktop VM 形状的 oracle 缺口——这正是基座改造的目的，但不因此放宽判据）。

## 2. 钉定批次身份（执行前置身份门禁）

批次只允许在下列钉定身份上执行；任何一项与预登记不符即停止推进（停止条件 S0）：

| 项 | 钉定值 | 观测来源 |
| --- | --- | --- |
| Lima | v2.2.0，peeled commit `de0816ea4bdc5267b428ab21025889b8dd785526` | git ls-remote + 浅克隆 rev-parse 一致（2026-09-15，survey §7.1） |
| guest 镜像 | Ubuntu 24.04 noble `release-20260705` server，按宿主架构取 per-arch digest：amd64 `sha256:ffe6203d…`，arm64 `sha256:7df02015…` | Lima v2.2.0 `templates/_images/ubuntu-24.04.yaml`（survey §7.2）；模板只允许保留带 digest 条目，fallback 无 digest 条目必须删除 |
| Docker Engine | `docker-ce=29.1.3-1~ubuntu.24.04~noble`（apt 池钉定安装，禁用 `get.docker.com`） | download.docker.com noble stable pool arm64+amd64 均在（survey §7.2）；与 profile.json `engine_version: 29.1.3` 一致 |
| X profile | `lore_execution/profile.json` 当前值：python 镜像 `sha256:78387bc3…`、seccomp `sha256:9c1025c8…`；28.0.1 为其 `previous` 修订前值 | 仓库文件（批次执行时逐字节读取并记录） |
| 挂载 | 主批 `vmType: vz` + `mountType: virtiofs`（macOS ≥ 13）；对照批 `vmType: qemu` + `mountType: 9p`（同架构 hvf 加速） | Lima mount 文档；对照批为 V1/V2 的备选路线证据 |
| 模板 | `scripts/substrate/lima/lore-substrate-virtiofs.yaml`、`lore-substrate-9p.yaml` 及探针脚本，以执行时计算的 sha256 记录入批次证据；与预登记 JSON 中 `template_sha256` 不一致即 S0 停止 | 套件草案（DRAFT/UNVERIFIED） |

执行机要求：Apple Silicon macOS ≥ 13（vz 原生）；Intel 宿主不在本协议范围（vz 不可用，且跨架构属 arm64 修订议题，见 §5）。执行机身份（机型、macOS 版本、limactl 版本）逐批次记录。

## 3. 批次与判据（预登记）

重复数与用例固定如下；预期全部先于执行钉定。每批次证据写入 `validation/substrate/evidence/<batch-id>/`（原始输出不入 Git），逐项预期→实际→裁定，失败原状保留，不重跑、不修补（沿用 m06 P7 惯例）。

### V1 共享挂载上的 RENAME_EXCHANGE（×3）

- **方法：** 在共享挂载（Surface/Workspace 形状的目录）内构造 base/staged 两棵固定文件树；探针复用产品原语（`lore_files.install` 的 `_renameat2` 绑定、`lore_files.util.identity`、`lore_files.metadata.walk`）执行与 `install.py` 相同的检查链：交换前 walk 等值校验 → `renameat2(…, RENAME_EXCHANGE=2)` → 目录 fsync → 交换后 walk 与内容 sha256 等值校验 → dev/ino 身份互换核对 → errno 逐例记录。
- **判据：** 3/3 交换成功（返回 0）；交换后两棵树内容与身份判定与预注册等值关系逐字节一致；无静默数据丢失形状（对照 #7687）。任一例返回非 0 或内容不符即批次 FAIL。
- **负对照（探针必须能拒绝的错误）：** (a) 在 VM 本地盘（ext4）执行同探针预期成功——证明探针实现本身可通过；(b) 跨文件系统交换预期 `EXDEV`——证明 errno 路径被真实执行；(c) 预置篡改树（交换后内容不符）预期被 walk 校验拒绝——证明等值校验有拒绝能力。三项对照任一不符合预期，批次无效（验证器错误，非被测物错误），修复探针后换批次号重登记，不覆盖旧记录。
- **对照批（备选路线，同判据独立登记）：** qemu+9p 上执行同 V1；其结果只作为 V1 失败时修订路线（单次 rename 换入或容器卷驱动）的输入，不改变主批裁定。

### V2 共享挂载上的 inotify 送达（×3）

- **方法：** VM 内以真实 `lore_files.window_linux.StableWindow`（递归 inotify、租约、丢事件掩码检测）监视共享目录；宿主侧固定写入器按预注册序列执行：创建文件 → 写入并 close → 同目录 rename → 删除文件 → 嵌套子目录内创建。两端记录时间戳与事件集。
- **判据：** 3/3 批次中，create/close_write/move/delete 四类事件与嵌套递归送达均被观察者完整收到，且 `StableWindow` 无丢事件掩码（Q_OVERFLOW 等）报告。**任何一类缺失即 FAIL**——特别注意：上游文档已声称"宿主删除不触发"（mountInotify 机制缺口），本批就是要在钉定基座上实测该声称；delete 缺失直接否定 F 的 BASE_CHANGED 并发检测语义，属核心失败，按 §5 修订路线处理，不得以"实验性功能"为由降低判据。
- **负对照：** 无宿主写入的静默窗预期零事件（拒绝恒真观察者）；宿主写入但观察窗未开启的影子记录预期为空（拒绝同源采集）。`mountInotify` shim（若启用）作为独立对照运行记录，其已知缺口（宿主删除、9p 嵌套）作为边界发现记录，不参与判据。

### V3 共享目录 dev/ino 跨 VM 生命周期稳定（重启 ×2 + 重建 1 次观测）

- **方法：** 固定文件集（两目录 × 三文件）在共享挂载与 VM 本地盘各建一份，记录 `identity()` manifest（含 dev/ino 与 sha256）；`limactl stop` → `limactl start` 后复测比对，×2 次；随后 `limactl delete` + 重新实例化后第三次观测（该次为**观测项**，其结果只决定 manifest 再生成策略，不参与判据）。
- **判据：** 2/2 重启后共享挂载文件集的 dev/ino 与 sha256 逐项一致（本地盘集合同步核对，作为对照）。任何 dev 或 ino 漂移即 FAIL。
- **负对照：** 预置"重启后人为替换文件"的反例运行一次，预期 manifest 比对报告不符——证明比对器有拒绝能力；该反例不与正式样本混算。

### V4 Engine 与镜像身份在 VM 内可钉定（×2，独立实例各 1）

- **方法：** 全新实例内：`docker version` Server 段逐字段等值于 profile.json `engine_version`（与 `lore_execution/engine.py` 预检同一比较语义）；`docker pull python@sha256:78387bc3…` 后 `RepoDigests` 含该 digest；`docker manifest inspect` 记录该 digest 的 manifest 形状（是否 manifest list、含哪些 arch——**观测项**，为 arm64 修订提供实测输入）；seccomp 文件 sha256 等值于 profile.json；`docker volume create lore-runtime-deps` 后 `_data` 路径存在且位于 `/var/lib/docker/volumes/`（固定 volume 路径可复现——Docker Desktop 时代不可钉的耦合副作用，在基座上应为可复现事实）。
- **判据：** 2/2 实例五项等值判定全部成立（manifest 形状为记录项）。任一不符即 FAIL：Engine/digest 不符 → 修订路线回到候选选型或按修订记录改 profile 钉定；volume 路径不符 → deps 布局修订。
- **负对照：** 预置 engine_version 为错误值（如 `28.0.1`）的预检运行预期被拒绝——证明等值比较拒绝错误而非恒真。

## 4. 停止条件

- **S0 身份门禁：** 模板/探针 sha256、Lima commit、镜像 digest、apt 包版本任一与 §2 钉定不符 → 不启动 VM，停止并记录。
- **S1 同因连续失败：** 同一判据同因连续失败 2 例（V1/V2）或 1 例且原因可复现（V3/V4）→ 停止推进转诊断；失败原状保留。
- **S2 环境阻塞：** 执行机不满足 macOS ≥ 13 / Apple Silicon / Virtualization.framework 可用，或 pinned 镜像与 apt 池不可达 → 记 BLOCKED（不是 FAIL），附缺失条件。
- **S3 批次 FAIL 的全局效力：** 任一批 FAIL 即本协议范围整体 FAIL；失败后果按 §5 修订路线处理；修订后须以**新批次号**重新预登记并全量重跑受影响批，不覆盖旧记录。
- **S4 未运行项：** 因停止条件未运行的批记 UNVERIFIED；探索性对照批（9p 对照、mountInotify shim 对照、delete 重建观测）未运行不影响主批裁定，但其结论同样不得计作 PASS。

## 5. 失败后果与修订路线（继承 survey §4，含 arm64 修订）

| 失败 | 修订路线 | 约束 |
| --- | --- | --- |
| V1：EXCHANGE 不可用或数据丢失 | 发布边界改为 VM 内暂存区 + 单次 rename 原子换入（修订 F 契约并重验证），或评估容器卷驱动替代 | 修订走修订记录；9p 对照批结果作为路线选择输入 |
| V2：inotify 缺失类事件 | 监视根移入 VM 内（输入经同步边界进入），或登记 F 的共享挂载限制并缩小声明范围 | 缩小范围须保留原判据记录与影响分析 |
| V3：dev/ino 不稳定 | deps 树与状态目录全部移入 VM 磁盘内（仅 Surface 交付物经同步边界输出），manifest 绑定 VM 内路径 | 与 dependencies-manifest 再生成策略同步修订 |
| V4：Engine/digest/volume 钉定失败 | 回到候选选型；或按修订记录改 profile 钉定并重跑受影响 X 批次 | profile 修订必须走 amendment，不得批内就地改 |
| **arm64 前置修订（不属 V 批次）** | Apple Silicon 宿主 + 镜像钉定的 per-arch digest 表 vs Rosetta 方案，二者都改变 X profile 钉定内容，按修订记录处理并重跑相关批次 | 本协议已按"倾向 per-arch digest 表"钉定（noble per-arch digest + QEMU/Rosetta 不承载判据）；Rosetta/binfmt 路线改变物理判据形状（用户态转译），**不得承载任何判据运行**，仅可作为后续性能观察项 |

## 6. 适用范围与非目标

- **范围：** 单台 Apple Silicon macOS 宿主、§2 钉定 appliance、`~` 下仓库工作副本经共享挂载进入 VM 的形状。结论不外推到其他 Lima 版本、其他 guest 镜像、其他挂载类型或其他宿主。
- **非目标：** 不做安装器装配（V1–V4 全 PASS 前为门禁阻塞项）；不做 R/E/F/X 组件或整系统在基座上的重验（后续独立预登记）；不做性能基准宣称；不修改 `lore_execution/profile.json` 或 F/X 契约文本；不采信本批任何结果豁免既有 UNVERIFIED 项（XN01–XN12、X031/X033 物理判据等的终验归属不变——基座若通过，恰好为它们提供 Linux 宿主验证环境，但须按各原协议重跑）。
