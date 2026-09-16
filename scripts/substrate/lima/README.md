# 最小 Lima 套件草案（substrate 批次 V1–V4）

**状态：DRAFT / UNVERIFIED（2026-09-15 起草，从未执行）。**
**判据与身份：** [validation/substrate/protocol-substrate-001.json](../../../validation/substrate/protocol-substrate-001.json)（预登记批次+停止条件）与 [design/g2/substrate-verification-protocol-2026-09-15.md](../../../design/g2/substrate-verification-protocol-2026-09-15.md)（叙述）。身份调研依据：[macos-host-substrate-survey-2026-09-15.md §7](../../../design/g2/macos-host-substrate-survey-2026-09-15.md)。

## 门禁（用户 2026-09-15 指令，先于一切）

1. **V1–V4 全部 PASS 之前，不进入安装器装配流程**——不在未验证的共享目录语义上堆上层工作。
2. **套件冻结前不得执行本目录任何脚本。** 冻结程序：独立审查本目录与预登记 JSON 的一致性 → 将模板/探针实测 sha256 回填协议 JSON 的 `environment.template_sha256` → 此后 S0 身份门禁才可判 PASS。此前执行即违反预登记。
3. 本套件只验证共享目录语义与钉定能力；R/E/F/X 组件与整系统在基座上的重验另行预登记，不在本套件范围。

## 文件

| 文件 | 角色 |
| --- | --- |
| `lore-substrate-virtiofs.yaml` | 主批钉定模板：vz + virtiofs，noble release-20260705 per-arch digest，docker-ce 29.1.3 apt 钉定，`mountInotify: false`，`rosetta` 显式关闭 |
| `lore-substrate-9p.yaml` | 对照批模板（qemu + 9p，同架构 hvf）：仅作 V1/V2 失败时的修订路线输入，不改主批裁定 |
| `run-v1-v4.sh` | 批次编排草案：S0 身份门禁 → 决定性实例生成 → V1→V2→V4(样本1)→V3(重启×2+重建观测)→V4(样本2)；证据落 `validation/substrate/evidence/<instance>-<ts>/` |
| `probes/v1_rename_exchange.py` | V1：exchange（×3）+ exdev/corrupt 负对照；复用产品 `_renameat2` 绑定与 `walk` 等值语义 |
| `probes/v2_inotify.py` + `probes/v2_host_writer.sh` | V2：raw 层（产品掩码常量+动态递归）与产品 `StableWindow` 合同层双观测；silent/shadow 负对照 |
| `probes/v3_identity_stability.py` | V3：dev/ino+sha256 manifest record/compare；重启 ×2 判据、重建为观测项 |
| `probes/v4_engine_pin.py` | V4：Engine/digest/seccomp/固定 volume 路径四项等值 + 错误版本拒收负对照；manifest 形状为记录项（arm64 修订输入） |

## 判据映射（详见预登记 JSON）

- **V1 判据：** 交换返回 0 且交换后两侧状态逐字节互换（内容+元数据+hardlink 组，walk 字典等值）、目录 dev/ino 互换；任一不符 = FAIL（含 #7687 静默数据丢失形状）。负对照：本地 ext4 通过（探针可通过）、跨文件系统 EXDEV（errno 路径真实）、篡改树被拒（等值校验有拒绝能力）。
- **V2 判据：** 宿主写入序列的 create / close_write / move cookie 对 / delete / 嵌套创建五类全部送达 raw 层，且产品窗口 `assert_clean()` 必须 raise `CHANGE_OBSERVED`（静默 = 观察者失明 = FAIL）；无丢事件掩码。已知上游声称（宿主删除不触发）正是本批实测对象，不得降标。
- **V3 判据：** 重启 ×2 后共享挂载文件集 dev/ino+sha256 逐项一致；本地盘集合为对照。重建（delete/新建实例）为观测项，不参与判据。
- **V4 判据：** `docker version` Server 等值 profile.json `engine_version`（29.1.3）、按 digest 拉取后 RepoDigests 相符、seccomp sha256 相符、volume 固定路径 `/var/lib/docker/volumes/lore-runtime-deps/_data` 存在。manifest 形状（是否含 arm64）为记录项。错误 engine 版本必须被拒收。
- **退出码：** 0 = 判据满足/预期拒收成立；2 = 判据违反（原状留证，不重跑）；3 = 环境阻塞（BLOCKED，非 FAIL）。

## 停止条件（摘自预登记 JSON）

- **S0** 身份不符（limactl ≠ 2.2.0、模板/探针 sha256 与回填值不符、digest/apt 包不可达）→ 不启动 VM。
- **S1** 同判据同因连续失败 2 例（V1/V2）或 1 例可复现（V3/V4）→ 停止转诊断。
- **S2** 宿主不满足 Apple Silicon / macOS ≥ 13 / Virtualization.framework → BLOCKED。
- **S3** 任一批 FAIL = 本协议范围整体 FAIL；修订后以新批次号重新预登记并全量重跑受影响批；不覆盖旧记录。

## 使用（冻结后）

```bash
# 宿主（Apple Silicon, macOS >= 13）：安装钉定 limactl 2.2.0 后
LORE_ROOT=/abs/path/to/loom ./run-v1-v4.sh virtiofs   # 主批
LORE_ROOT=/abs/path/to/loom ./run-v1-v4.sh 9p         # 对照批（仅 V1/V2 失败后有解释力）
```

- 实例由模板经 `sed` 决定性生成（`{{.Param.LORE_ROOT}}` → 绝对路径），两份 sha256 均写入 `evidence/identity.txt`。
- 临时探针目录 `.substrate-tmp/` 在共享挂载上，属批次工作区：执行前考虑加入 `.gitignore`，证据目录按 [evidence-guide](../../../governance/evidence-guide.md) §4 保留原始输出（不入 Git）。

## 已声明的边界与已知形状

- **租约边界：** guest 侧 read lease 不覆盖宿主侧写入者（不同内核），宿主侧并发检测只可能依赖 inotify——这正是 V2 存在的原因；V2 探针已在 docstring 记录。
- **递归边界：** `window.py` 的递归 watch 建立于窗口进入时；窗口内新建目录在其递归范围之外。V2 raw 层用动态递归测量"共享挂载能送达什么"，产品窗口层只要求拒绝它能看到的变化。
- **xattr：** `lore_files/metadata.py` 已按 amendment-linux-browser（2026-09-15）对 errno 95 的挂载记录空 xattr 集；virtiofs 行为以批内实测为准。
- **Rosetta/binfmt：** 改变物理判据形状，模板显式关闭，不承载判据运行（协议 §5）。
- 任何探针结果都不构成组件或系统验收；独立验收者须从预登记 JSON 与原始证据直接复查（evidence-guide §6）。
