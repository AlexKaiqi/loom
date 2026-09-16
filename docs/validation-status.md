# 验证状态

记录时间：2026-09-15。此页是公开进展摘要；原始模型请求、执行归档、数据库和独立审查原件保存在开发环境，没有随源码公开。仅凭本页不能独立复验历史通过结论。

| 范围 | 当前状态 | 结论边界 |
| --- | --- | --- |
| 顶层抽象、论证、模拟与定向调研 | 已形成阶段资产 | 见 `design/g1`、`design/g2`；不是生产系统通过 |
| R/E/F/X/S 与 Runtime 组件 | 有独立组件及固定响应装配证据 | 组件结论不等于真实模型整体验收 |
| 预算准入修订（budget-admission-001） | **探针通过** | 真实 R/ProviderBridge + 本地 HTTP 固定响应；不是真实模型批次证据 |
| M01 最简真实模型闭环：2 种输入 × 3 次 | **整批 6/6 通过**（批次 z，真实 glm-5.3） | 通过依 2026-09-14 预算修订；固定响应装配探针独立，不混同 |
| M02：5 类安全场景 × 3 次 | **15/15 已独立核验** | 使用真实 Pi/Runtime/Docker/NATS 和本地固定 HTTP 响应，不是 15 次真实模型测试 |
| M03：5 类崩溃接续 × 3 次 | **实际执行 15/15 PASS**（m03-execute-007，2026-09-16） | 预登记判据独立判定：切点 SIGKILL、新进程只读 query、租约到期后恢复、外部效果计数与暂停不重做全过；工具环境派生回归与夹具编码缺陷修复记录于修订稿 |
| M04：新容器读取原会话并接续 | **实际执行 3/3 PASS**（m04-execute-003，2026-09-16） | 预登记判据独立判定：result_saved 切点销毁后资源 404 归零、只读 query 保持原状、显式 Session 查询恢复字节前缀完整且零新效果、租约到期后恰一次结清原决定；确认归档前缀语义适配记录于修订稿 |
| M05 及其后故障/恢复场景、多 Surface、多策略、规模测试 | 未完成 | 完整目标保留，未以最简 Harness 代替 |
| M06 浏览器沙箱环境（2026-09-15 立项） | **性质契约与用例已建立**（[m06-browser-environment.md](../design/g3/system/m06-browser-environment.md)） | 未运行；不依赖图像通道；实现前须先完成 environment→profile 引用的契约修订并独立验证 |
| M07 computer-use GUI 沙箱 | **未立项** | 前置：图像 artifact 通道（backend-seam.md §5a）未实现；模型侧模态已探明（见 2026-09-15 增量） |
| G6 最终独立验收 | **未完成** | 不具备完成声明 |

## 2026-09-16 增量：M03 崩溃接续套件首次实际执行（15/15 PASS）

- **M03（跨设施保存与回执丢失，goal-150d36ae）**：预注册套件 [validation/runtime_recovery](../validation/runtime_recovery/README.md) 五类切点 × 3 = 15 场景在 Linux 验证容器完成 prepare 与 `--execute`。批 m03-execute-007 全 15 场景 PASS（每例 12–30 项独立判据），证据与源稳定性快照按设计保留于 Linux 状态卷 `m03-evidence/`。判定覆盖：精确进程组 SIGKILL 与收割、新进程仅原 `Runtime.query` 观测且 store/域全等、工具与安装类等原 30 秒租约真实到期后恢复驱动、外部效果计数（HTTP ≤1、工具标记追加恰一次）、效果不重做（暂停不冒充接续）、原 ID/授权/版本链完整。中途按反例修复两缺陷（工具环境派生回归、夹具 `\n` 编码），全部记录于 [修订稿](../design/g3/x/amendment-linux-browser-2026-09-15.md)；执行 005/006 批被同工作区并发 M01 会话的源写入作废（FAIL_SOURCE_CHANGED，如实记录）。runner 增 `--evidence-root` 适配状态卷证据位。

## 2026-09-16 增量（续）：M04 保存边界释放与新进程接续首次实际执行（3/3 PASS）

- **M04（保存边界释放与新进程接续，goal-697fe083）**：预注册套件 [validation/runtime_continuation](../validation/runtime_continuation/plan.md) 三次重复序列在 Linux 验证容器完成 `--execute`，批 m04-execute-003 全 3 场景 PASS（每例 21 项独立判据），证据保留于 Linux 状态卷 `m04-evidence/`。判定覆盖：result_saved 处精确 SIGKILL、新 Runtime 前原容器/卷全部 404（任务专属资源归零）、原 `Runtime.query` 只读零效果、显式 `SessionService.invoke` 查询以新受信执行 ID/新 CID/卷/ExecID 恢复原结果且原始会话字节逐字节前缀完整、租约真实到期后恰一次结清原 stop 决定。首执行暴露套件确认归档全等假设缺陷（运行时追加式日志语义自洽），按反例修复为前缀校验（[修订稿](../design/g3/x/amendment-linux-browser-2026-09-15.md)），判据未放宽。runner 增 `--evidence-root`。


## 2026-09-15 增量：environment→profile 引用契约修订（M06 前置，已执行）

- **契约修订**：[amendment-environment-profile-2026-09-15](../design/g3/x/amendment-environment-profile-2026-09-15.md)——generic schema-1 请求新增必填 `profile_sha256`；`environment` 改为 X 环境注册表引用（新产品文件 `lore_execution/environment_profiles.json`，首条目 `fixed-python-linux-v1` 与 profile.json 冻结身份互检）；network/endpoints/interpreter 语义移入 profile 条目；模式推广自 schema-2 会话路径既有机制。对既有流零行为变化。
- **验证**：离线注册表核对 **PASS**；新预登记用例 X029/X030（未登记 id 拒收/摘要不匹配拒收）经真 JSONL 适配器 + 真 Docker **PASS**（environment-profile-014/015）；X001 冒烟证明 execute 主路径端到端跑通，但整批 30 例的正式验收需 Linux 宿主（oracle 的 /proc/cgroup/ns 物理观测在 Docker Desktop macOS VM 下不可复现），未宣称整批通过。
- **平台分支修复（本机首测发现并落位）**：docker CLI 路径平台解析（engine×4/store×1/collector×10，`LORE_DOCKER_CLI` 可覆盖）；host xattr API 守卫（archives/ordinary_sources，容器内观测仍绑定）；输入归档确定性 Python 打包替代 host GNU tar；collector 平台事实源切至产品 profile.json。发布清单同步（101 产品文件），check_source.py PASS（398 源编译）。
- **续段（同日）**：linux-browser §5 流程修订稿落库（[amendment-linux-browser-2026-09-15](../design/g3/x/amendment-linux-browser-2026-09-15.md)）：registry schema 2（可选 `seccomp_path`/`budget_maxima`）、创建路径按请求 profile 取镜像、引擎预检逐条目化、adoption-assessment A1–A3 构建语义并入。**构建流程 PASS**（`scripts/image-linux-browser/`：镜像 `sha256:f026ff91…`、Chromium 152.0.7977.82、playwright 1.62.0、seccomp 冒烟在 network=none 下通过）；`linux-browser-v1` 已登记（摘要 `edf9eb57…`）。组件用例：**X032 全 PASS**（按 profile 预算上限，linux-browser-001）；**X031/X033 功能路径本机验证通过**（浏览器启动→file:// 页面读取→标题提取→产物发布→归档内容核对 PASS；出网阻断 `egress=blocked` 留证 PASS；任务 exit 0/SEALED），其预登记中的 `running.physical.task_uid` 等 Linux 形状物理判据与本机 oracle 边界一致（X001 先例），整条判据的最终通过仍归 Linux 宿主验证环境——X031/X033 状态记 UNVERIFIED（部分判据未决），不宣称整例通过。迭代链证据：linux-browser-002…014（tmpfs 容量/inode、pids 计线程、可选预算键校验、oracle 内存守卫缩放），每次调整记入修订稿 §5a。发布清单 102 产品文件，check_source PASS（398 源）。**批量协议预注册**：[m06-batch-a-001](../validation/m06_browser/protocol-batch-a.json)（A1/A2/A3×3：功能场景+证据链）与 [m06-batch-b-001](../validation/m06_browser/protocol-batch-b.json)（N1/N2/N3×3：负例）已钉定判据/停止条件/验证边界；批次驱动与固定响应接线为下一步。**续段（同日更晚）**：修订周期 ④b①②③⑤ 全部落地并通过组件验证（会话 profile 文档 + 模板、可信配置多 profile 条目化、id 检查泛化、prepare 按条目 budget_maxima、grant 链单元闸门与 21 项回归锚）。批次驱动 `m06_run.py` 迭代至全链路打通（NATS 容器化、F 元数据 errno-95 平台守卫并迁移 Linux 状态卷、模板 environment_values 同步、注册表镜像指向会话镜像、工具计划按注册 profile 派生环境与预算、slot tool 角色扩容至浏览器量级——各调整与 OOM/SIGTRAP 实测证据记入修订稿 §5a）。**批 A（m06-batch-a-001）9/9 PASS**：A1/A2/A3×3 真实 Runtime + linux-browser-v1 + 固定响应三步链，O1–O8 全过，工件与预注册逐字节一致。**批 B（m06-batch-b-002）9/9 PASS**：N1 出网阻断留证、N2 篡改被 O2 等值校验检出留证、N3 注入文本流入但未被执行且链路正常停止；负例判据独立实现于 `m06_run_b.py`。边界不变：物理判据归 Linux 宿主；XN01–XN12 冻结套件重跑为批前待办。协议批 B 判据从 batch-b-001 原样执行（驱动实现迭代记录见 assessment 留档）。**XN 套件重跑（同日收尾）**：UNVERIFIED（基建阻塞）——run_frozen 钉定的 seccomp 输入路径为迁移前陈旧路径（已修正为 lore_execution/seccomp.json），其后仍因 `design/g4/f-gate.json`（G4 期 F 门记录，未入库且已丢失）缺失而无法执行；依约束不凭手重建审批门记录，XN01–XN12 记 UNVERIFIED，重建须先经授权的 F/X 组件复验（详见修订稿收尾记录）。**续段（授权复验后同日完成）**：F 契约 19/19 PASS、R 契约 22 单元 + 23 进程 PASS（均于 Linux 验证容器 + 原生证据卷），`design/g4/f-gate.json`/`r-gate.json` 以复验哈希重新出具；XN01–XN12 冻结套件连续两次 12/12 PASS（判据未放宽，环境适配与随修订上限刷新逐条记录于修订稿）。冻结回归闸门恢复可用，套件证据按设计保留于 Linux 状态卷 xn-evidence/。诊断性探针（probe_np*.py、m06-dry-* 证据目录）已按计划清理；M06 证据目录保留批 A（m06-batch-a-001）与批 B 首轮（m06-batch-b-001，含驱动迭代记录）及完整通过批（m06-batch-b-002）。

## 2026-09-15 增量：执行后端接缝声明与多模态探针

- **X 执行后端接缝（代码级声明，非行为变更）**：`lore_execution/backend.py` 按
  [backend-seam.md](../design/g3/x/backend-seam.md) D-X-SEAM-001 以 Protocol 声明方法面、
  owner 内部边界与 profile 归属；`simulations/test_execution_backend.py` 7 项静态符合性
  检查通过。该声明只防漂移，不执行后端，不构成组件验收。发布清单同步登记
  （source-manifest.json，100 个产品文件）；check_source.py PASS（393 源编译）、
  观察器与回归检查 OK。
- **多模态探针（provider-compatibility-002，两次运行 -003/-004 一致）**：对用户
  Ark Agent Plan 端点发送固定 32×32 PNG 的 OpenAI image_url content part
  （max_completion_tokens=2048，遵循 amendment-001 预算教训）：
  - `deepseek-v4-flash`：**accepted**（HTTP 200、finish_reason=stop、usage 总数一致；
    回显别名 `deepseek-v4-flash-ga-260731`）；
  - `kimi-k3`：**accepted**（同上）；
  - `glm-5.3`：**rejected_image_content**（HTTP 400，逐字错误
    `InvalidParameter: "Model only support text input"`）。
  判据边界：仅证明线级模态支持；不含 grounding 质量宣称，不改变 M01 基线。
- **M07 前置状态**：模型侧模态前提对 deepseek-v4-flash/kimi-k3 成立；图像 artifact
  通道（backend-seam.md §5a）仍未实现。若 M07 真实模型批选用 deepseek-v4-flash，
  须先按模板修订记录处理协议-001 的 model 回显严格检查（日期别名问题，见
  amendment-001 selection_observation）；基线切换本身待用户授权，未在此处决定。

- **Provider 基线切换（已执行，用户 2026-09-15 授权）**：glm-5.3 → **deepseek-v4-flash**，记录
  [amendment-model-baseline-2026-09-15](../design/g3/provider/amendment-model-baseline-2026-09-15.md)
  与 [amendment-002](../validation/provider_compatibility/amendment-002.json)。切换门禁：
  protocol-003 生产形状探针（`reasoning_effort`/`parallel_tool_calls` 首次实测）切换前
  [evidence-005](../validation/provider_compatibility/evidence-005/record.json) 与切换后真实
  `encode_request` 字节 [evidence-006](../validation/provider_compatibility/evidence-006/record.json)
  全部通过；响应回显规则改为"精确基线 id 或钉定日期别名 `deepseek-v4-flash-ga-260731`"，
  离线用例 [baseline-offline-001](../validation/components/provider/evidence/baseline-offline-001/assessment.json)
  通过（别名接受/旧基线串拒收/生产编码逐字节复现）。
- **如实记录的缺口与修复**：(1) 本工作副本从未发布 `design/g3/provider/fixtures/`，33 例
  provider 组件套件（run_contract.py）不可运行，旧 fixture 内模型串须在持有 fixture 的环境
  重新生成后整批复跑，此前不宣称该套件对新基线通过；(2) `runtime_provider_probe.py` 与
  `runtime_provider_race.py` 停留在 2026-09-14 预算修订前的旧键集（且前者本地响应仍回显
  glm-5.3），属快照既有断裂、与本次切换无关——已最小修复（补 `reasoning_effort` 键、响应
  字面量切基线）后复跑：PO01–07 **PASS**（batch baseline-switch-002）、竞态 **PASS**。
- M01 批次 z 证据保持绑定 glm-5.3 及其仪器对（m01_run.py、runtime_observer.py O7）不变；
  新基线真实批次须定义自己的观测协议。发布清单同步更新（request.py/response.py/
  check_public.py）；check_source.py PASS（397 源编译、100 产品文件核对）。

## 2026-09-15 增量：macOS 宿主基座（substrate）方向立项——调研钉定、协议预登记草案、Lima 套件草案

- **调研升级（在线核对完成）**：[macos-host-substrate-survey-2026-09-15 §7](../design/g2/macos-host-substrate-survey-2026-09-15.md)——`git ls-remote` 直连 refs + releases/latest 重定向钉定：Lima **v2.2.0**（peeled commit `de0816ea…`，浅克隆 rev-parse 复核一致）、Finch v1.17.2、podman-machine-os v6.1.2（org 迁移至 podman-container-tools）、apple/container 1.4.1；GitHub API 限流（403）同前次调研。文档级核实：Lima `mountInotify` 实验性且宿主删除事件不触发；**[docker/for-mac#7687](https://github.com/docker/for-mac/issues/7687)（AVF+VirtioFS `RENAME_EXCHANGE` 数据丢失，OPEN）**；vz 自 v1.0 为 macOS 默认、VF 不支持跨架构；Lima 自带 docker 模板经 get.docker.com 浮动安装；docker-ce 29.1.3 在 noble pool（arm64+amd64）而 resolute 无 → 套件 guest 钉 Ubuntu 24.04。
- **substrate 验证协议（预登记草案，批次未执行）**：[substrate-verification-protocol-2026-09-15](../design/g2/substrate-verification-protocol-2026-09-15.md) + [protocol-substrate-001.json](../validation/substrate/protocol-substrate-001.json)——V1 `RENAME_EXCHANGE`（含数据丢失形状判据与 EXDEV/篡改负对照）、V2 inotify 送达（真实 `StableWindow` 合同层，宿主删除等五类事件为判据）、V3 dev/ino 跨重启稳定、V4 Engine/digest/seccomp/固定 volume 路径钉定；S0 身份门禁与 S1–S4 停止条件；失败修订路线与 arm64 前置修订（per-arch digest 表优先，Rosetta 不承载判据）。
- **最小 Lima 套件草案（DRAFT/UNVERIFIED）**：[scripts/substrate/lima/](../scripts/substrate/lima/README.md)——vz+virtiofs 与 qemu+9p 钉定模板（noble per-arch digest、docker-ce 29.1.3 apt 钉定、rosetta/mountInotify 显式关闭）、V1–V4 探针（复用 `lore_files` 产品原语：`_renameat2` 绑定、`StableWindow`、`identity()`、`walk`）与编排脚本。探针经编译/导入冒烟与平台守卫冒烟（darwin→BLOCKED/3）；Linux 路径从未运行。
- **门禁（用户指令）**：V1–V4 全部 PASS 之前不进入安装器装配流程；套件冻结（sha256 回填+独立审查）前不得执行本套件。V1–V4 状态：**UNVERIFIED**（未运行）。

## 2026-09-14 M01 真实模型整批通过（批次 z）

批次 [m01-real-2026-09-14z]（证据目录 `validation/system/evidence/m01-real-2026-09-14z/`，
原始证据 312MB，不入 Git）：2 种输入 × 3 次重复 = 6 个真实 glm-5.3 样本
（经 https://ark.cn-beijing.volces.com/api/plan/v3 路由），attempted=6、passed=6、
exit=0；每样本 O1–O8 独立观测全数通过，失败检查数为 0。

- 依据修订：[amendment-m01-output-budget-2026-09-14](../design/g3/provider/amendment-m01-output-budget-2026-09-14.md)
  （输出预算 2048→16384、输入 15360→49152 / 主体 65536、步数与请求数 6→24、
  墙钟 300→1800、transport timeout ≤300、reasoning_effort=medium、
  parallel_tool_calls=false；每项含反例证据与旧值记录）。
- 环境与装配：`lore-validation:2026-09-14` 派生镜像（平台修订记录）、
  runtime-assembly-2026-09-14i 固定响应装配 PASS（volume 模式）、
  load-2026-09-14a/b/c 受限加载探针 OBSERVED_PREPARATION。
- 判据边界：这是 M01 案例在该模型基线与修订预算下的整批通过；
  不外推到其他模型、更严格旧预算或 M02+ 场景。

## 2026-09-14 预算准入修订

历史 M01 批次的阻断（第六合法步骤被 `used+bytes` 混合预留拒绝）已按预注册协议
[admission-protocol.json](../validation/provider_budget/admission-protocol.json) 处理：

- 修复前反例证据：`validation/provider_budget/evidence/admission-001-before/`
  （BEFORE_FIX_EVIDENCE：PBO-01 以 budget_exceeded 复现，其余 PBO 保持旧行为）。
- 修复后探针批次：`validation/provider_budget/evidence/admission-001/`
  （AFTER_FIX_EVIDENCE：PBO-01..06 全部 PASS）。
- 修订记录与健全性论证：[amendment-budget-admission-2026-09-14](../design/g3/provider/amendment-budget-admission-2026-09-14.md)。
- 硬预算不变（6 请求 / 15360 实际输入 token / 2048 输出 / 15360 主体字节 / 300 秒）；
  响应后实际用量总检查不变。
- 回归：runtime_provider_probe（PO01–07）PASS；runtime_provider_race PASS。
- 该修订只解除准入阻碍，不构成 M01 六例真实模型通过；整批须在 Linux 容器内
  以当前模型基线（glm-5.3，经 path_prefix 路由）重跑。

## 最近真实 M01 批次

原预算维持不变：每例最多 6 个 Step、6 次模型响应、每响应 2048 token、累计输入限制 15360、300 秒。

| 批次 | 成功 | 失败 | 未运行 | 主要结果 |
| --- | ---: | ---: | ---: | --- |
| m01-real-003 | 1 | 1 | 4 | 第二例过早结束，未完成全部要求 |
| m01-real-004 | 1 | 1 | 4 | 第二例第五请求准入被预算拦截 |
| m01-real-005 | 0 | 1 | 5 | 第一例第六请求准入被预算拦截 |

005 的第一例执行约 202.9 秒，已产生报告、实际读取已发布的历史文件、写入 notes 并发布 JetStream 事件；第六次待发请求仍未被允许发送，缺少最终完整闭环。预算准入采用保守预留：前五次实际 prompt usage 为 7140，第六次完整 HTTP JSON 为 9886 字节，合计 17026，超过 15360。这里是实现采用的保守准入计算，不是把字节宣称为实际 tokenizer token 数。

修复方向须维持原判据，先为上下文投影与预算行为准备独立反例，再实现和重跑整批。产物部分完成、资源已释放和某个组件通过都不能将该批次改为成功。

M02 的独立审查核对了 210 份源副本、39 个执行的原始清理事实及 Pi/HTTP/F 等原件。它只支持上述 15 个安全场景的范围，不推导全系统安全或生产可用。

## 本次源码发布检查

公开版本的产品文件与开发工作副本逐字节比较；发布清单见 [source-manifest.json](source-manifest.json)。基本语法、导入和模拟观察器检查的实际结果将在 [publication-checks.json](publication-checks.json) 中记录。公开整理本身不改产品行为，也不使原系统测试自动通过。


## M01 阈值归档（2026-09-15）

- 机制：capability_limits.archive 四键（startup_assets 白名单校验）→
  pi shouldCompact 硬阈值 + before_compaction hook 确定性摘要 + 尾部保留
  （最新条目无条件保留，向后至 user 边界）；软阈值 transform_context
  注入压力提示（context_block 保形）。
- 组件证据：runtime_assembly_probe PASS_FIXED_ASSEMBLY_ONLY（压缩事实
  落盘、通知匹配、尾部保留均被固定响应行使）。
- 系统证据：m01-real-2026-09-14ao——v5-1/v5-2/v5-3 全部 PASS（归档启用、
  真实模型）；seeded-1 FAIL（双重 emit 等基线行为残留，见修正案批次结果节）。
- 反例链 aa→an 的全部修订记录于 amendment-m01-output-budget-2026-09-14
  （三轮截止、投影完整性、slot 包络 8×、计划总预算 2×、累计输入预算
  393216、尾部保留两次修订）。拓展点地图见
  design/g3/minimal-harness-extension-points.md。


## M01 归档收口与外部包络重定基（2026-09-15，goal-ce467e61）

- 外部流的环境档案注册表集成在会话流留下三道未注册成员即失败的门
  （store.py 镜像、tool_plans.py 天花板+profile_sha256、requests.py
  unapproved profile），均已按"未注册=集成前语义"回退修复；
  node_profile.guarded 与 SessionService 包装现携带内因类型与最深帧
  （永久可观测性改进）。
- 外部包络上调（tool 768MiB/cpus 1.0/总包络 512MiB）后，O8 全部镜像
  改为从 startup_assets.SLOT 导入派生，未来包络修订不再需要追改镜像。
- 观察器两项结构性修复行使通过：seal 终采样（rt.query 后、rt.close 前
  确定性采样）；_watch 寿命从运行器预算派生（原硬编码 310s 使长链失去
  tick 证据）。
- 行使证据：batch bd 5/6 PASS（v5-1/2/3 + seeded-1/2，含长链 O8 全绿）；
  batch bf v5-1 PASS、v5-2 仅 O4/O6 模型行为残留。批次/探针统一经
  scripts/lore_batch.sh（已验证路径）。
- 残留（模型行为，归基线）：偶发双重/三重 emit（压缩频繁触发下丢失
  "已 emit"语境）、个别工具输出盲区、O5 历史读取链偶断。harness 侧
  无未决缺陷。


### 2026-09-16（M05 长输出裁剪与完整原来源）

**M05 验证套件建立并执行**（validation/runtime_trim/，批次 m05-execute-001..049）：

- **M05-TRIM 8/8 全绿**（m05-execute-044..049 六连批复现，无诊断状态）：真实长输出（哈希变化文本）被阈值压缩归档裁剪后，原来源完整可查——恰一次确定性压缩事实（trigger=threshold，9300>8192）、头尾视图（旧用户组归档≥2、尾保留）、长输出全文（JSONL 转义形式校验）、版本哈希记录且验证、pi v4 结构解析、无超集 provider 调用（预算守卫在派发前拦截，R 保留未决责任）、链路结清。
- **2026-09-16 深夜增补（goal-d324bb94）**：①运行包络对齐（用户裁定"现规模为准"）：m01_run.py archive 声明 context_tokens 49152→16384、reserve_tokens 40960→8192（硬阈值 8192 不变），OVERFLOW 溢出声明 49600→16896；m05-execute-068/077/078 全 PASS。②独立验收完成：M03 复跑 m03-execute-009 15/15 PASS；M05 十二批（064-073、077、078）全绿且 TRIM/OVERFLOW 深查达标（压缩事实恰 1、暂停原因原文、3 回执）；M01 z 批 6/6、M04-003 3/3 证据在位。**M02 证据缺口**：original-M02.json 全卷与仓库零命中，"15/15 已独立核验"无法以原始证据复核——M02 状态降级为"当前环境未验证"，见 design/g3/x/acceptance-record-2026-09-16.md。验收执行形态（新会话验收者独立完成 071/072 + 直读核对；批次执行部分由实现会话支持）与角色未分离局限在验收记录第 2 节如实记录。

**2026-09-16 晚增补（goal-a0d0b8c8）**：套件扩至四用例——**M05-JOINT 全绿**（切割+恢复轨迹；终态语义经证据修正为 M03 同型：暂停+原 ID 责任保留+切割点前证据完整；'not a valid Message' 根因翻案=套件夹具 bug 而非运行时缺陷，运行时守卫经取证实证正确）；**M05-OVERFLOW 全绿**（步边界决策验证：预算守卫在派发前拦截 pi 溢出步内重驱，责任保留于接力链，溢出回执留存为证据；Temporal 调研 A 级项①诚实放弃/②语义收束/③决策+验证，见修订稿 2026-09-16 终局重估节）。3 重复判据批：055-057（三用例）与 065-067（四用例）全 PASS。证据位 m05-evidence/m05-execute-001..067。

**M05-CORRUPT 全绿**：完整源被身份校验接受、同长度损坏源被拒、原源不变。
- **M05-JOINT 如实未过**：恢复轨迹已实现（切割+租约等待+恢复驱动+原 ID/无重做检查），当前阻塞=运行时在工具暂停后保留回执的重放校验失败（'original provider reply is retained but not a valid Message'）——真实运行时发现，需独立调查（计入下一修订稿工作项），未计入通过。

**运行时缺陷修复（本轮发现）**：harnesses/minimal/index.mts 压缩钩子的用户边界检查用 `type==='user'`，真实 pi 消息形状为 `role:'user'`，致尾保留吞掉全部历史（archived 恒 0）——m01 单元模拟的形状掩盖，M05 真实链首次暴露；修复为双形状兼容。**机制定案**（源码+实验）：pi 估计器=最后 assistant usage+尾估；shouldCompact 门= tokensBefore>8192；溢出路径压缩准备仅含 systemPrompt 投影（结构性空转）；单步效果预算（1 provider/drive）与溢出再驱动结构性冲突——阈值路径为真实裁剪的唯一承载。wire 请求上限 65536 字节把真实上下文压在 ~16k token。全部证据见 design/g3/x/amendment-linux-browser-2026-09-15.md 与状态卷 m05-evidence/。
