# 修订记录：Linux 容器验证环境重建（platform-revision-2026-09-14）

## 背景与授权

本仓库当前目标为 Unix 系统（macOS/Linux）；运行时验证在 Linux 容器内执行
（Docker Desktop 29.1.3，arm64）。原验证环境的物理身份（路径、inode、二进制
SHA、依赖清单）不可复制到新机器；按 AGENTS.md 与 docs/development.md 的边界，
在新环境重新生成全部路径与物理身份记录，旧值全部保留于本记录，不覆盖。

## 重建内容与证据

| 项 | 旧值（保留） | 新值 | 证据 |
| --- | --- | --- | --- |
| NATS 二进制钉扎（support.py） | darwin 构建 `c2ce368d…` | linux/arm64 构建（commit 3c80d8f8…，v2.15.0-dev）`38427c1a…` | research/.cache/nats-server/nats-server sha256；容器内启动由各探针核对 |
| F 观测窗口 | 单一 Linux 实现（window.py） | window.py 派发 + window_linux.py（Linux 语义不变）；非 Linux 导入安全、使用显式 UNSUPPORTED | scripts/check_source.py PASS；Linux 语义由既有 facilities 证据约束 |
| Provider boot 身份 | 仅 `/proc/sys/kernel/random/boot_id`（Linux） | Linux 不变；darwin 用 kern.uuid+kern.boottime 的 SHA-256 组合（同一启动内稳定、跨启动变化） | provider_owner.py `_boot_identity`；本地组件探针通过 |
| 依赖选择 manifest | 旧机器 `dependencies.json`（pin `75e72765…`） | 重建于 linux/arm64 容器：5828 文件 + 1 链接，pin `888ba3c5…` | design/g3/x-node-profile/dependencies.json（环境派生，gitignore）；original-host/dependencies-manifest.json（1.4MB，低于 2MB 产品上限） |
| Pi 派生补丁 | 已记录单行派生补丁 | 同一单行：packages/agent/src/harness/context.ts 的 `@earendil-works/chord/context` 导入改为 `../../../chord/src/context/index.ts`（registry chord 0.85.1 不带 dist；tsx 直接加载 workspace TS 源；type-only 导入无需改动） | dependencies.json inputs 记录；受补丁文件的 sha256 进入 manifest |
| X profile | Engine 28.0.1 / image_id `ec7d6c95…` | Engine 29.1.3 / image_id `78387bc3…`（digest 引用不变）；seccomp sha 不变 | lore_execution/profile.json platform_revision 字段 |
| markdown-001 解析器快照 | 旧机器快照 | 同版本重建：markdown-it-py 4.2.0 + mdurl 0.1.2，72 个 .py 源 + py.typed×2 + port.yaml + 3 份 MIT 许可 | validation/system/dependencies/markdown-001/manifest.json |
| Node/Pi/tsx 版本 | 24.21.0 / 71dca871… / tsx 4.22.1 / esbuild 0.28.2 | 不变；node tarball sha256 `6ad1325e…` 校验 | dependencies.json inputs |

## 受限容器负载探针（S-CONTAINER-PREP-001 同协议）

`scripts/runtime-env/container-load-probe.py`（证据 validation/components/s/evidence/
load-2026-09-14{,b,c}/）：pinned 镜像 + 只读根 + 无网络 + uid 1000 + 512MB/64 pids
限额下，未改动 worker probe-public.mts 执行 single（provider=1，effects=1）与
multi（provider=1，effects=0）两条轨迹，node v24.21.0，全部检查通过
（load-2026-09-14c 为最终树回归）。结论等级：OBSERVED_PREPARATION，仅为准备证据。

## 影响分析

- 组件代码语义未变（window 派发保留 Linux 行为；boot_id darwin 分支仅本地探针使用）。
- 依赖树为按需闭包（运行时 import 闭包 + pi-ai 惰性 SDK 剔除）；剔除原因与范围
  记录于 dependencies.json。若未来启用 pi-ai 内置 SDK provider，须恢复对应包并重新钉扎。
- 旧环境证据（facilities-001、node-independent-full-001 等）的结论保留于其原件，
  不因本修订自动延伸到新环境；新环境的装配与 M01 需按既有判据重新取证。
