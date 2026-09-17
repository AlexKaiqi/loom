# X 执行环境 profile 引用修订（2026-09-15）

状态：CONTRACT_REVISION_2026-09-15，经用户授权的 M06 前置工作（"M06 实现前的 profile 引用契约修订"）。依据：`design/g3/system/m06-browser-environment.md` §1 契约修订说明、`design/g3/x/backend-seam.md` D-X-ENV-001（T0 profile 资产化）、`design/g3/x/contract.md`。

## 修订内容

1. **请求绑定**：generic schema-1 请求新增必填字段 `profile_sha256`（FIELDS 增补）；`environment` 的语义从"单一常量字符串"改为"X 环境注册表中的登记 profile 引用"。模式来源是 schema-2 会话路径的既有机制（`node_profile.py` 受信 profile 注册表 + 请求 `profile_sha256` 对照），本次推广到 generic 路径。
2. **新产品文件** `lore_execution/environment_profiles.json`：schema 1，`profiles` 列表；每条目字段集固定为 `{id, profile_sha256, image, image_id, seccomp_sha256, engine_version, network, endpoints, interpreter_argv}`；`profile_sha256` = sha256(canonical(条目去掉 `profile_sha256` 字段))，与 journal 摘要同构（`lore_execution.journal.canonical/digest`）。
3. **首条目 `fixed-python-linux-v1` 复现现行身份与语义**：image/image_id/seccomp_sha256/engine_version 与 `lore_execution/profile.json` 逐字一致；network `none`、endpoints `[]`、interpreter 允许表 `[["python","-c"],["python3","-c"],["/bin/sh","-c"]]` 与原钉定块等价——**对既有流零行为变化**。
4. **`requests.validate()` 变更**：`environment` 必须命中注册表条目、`profile_sha256` 必须逐字匹配条目、`network`/`endpoints` 必须等于条目声明（取代原硬编码 `network=="none"`/`endpoints==[]`）、`interpreter_argv` 必须属于条目允许表（取代原硬编码三元组）。错误码保持 `INVALID_REQUEST`/`unapproved execution profile`。
5. **Engine 预检扩展**（`PROFILE_CHANGED` 守卫延伸）：注册表每个条目的 image/image_id/seccomp_sha256/engine_version 必须与 `profile.json` 一致——在容器创建路径按 profile 取镜像（M06 实现工作项）之前，注册表只可能包含与现行冻结身份一致的条目，防止"校验接受但创建仍用旧镜像"的伪登记。
6. **构造点同步**：生产构造点 `lore_runtime/tool_plans.py` 与 X 套件构造点 `validation/components/x/fixtures.py` 增填 `profile_sha256`（取自注册表导出常量，不手抄摘要）。

## 判据与用例

- 新增 X029（未登记 environment 拒收）、X030（`profile_sha256` 不匹配拒收），`status: UNVERIFIED`，依赖 `real_docker`/`X_test_adapter`；用例 schema 与 X008 的拒收断言形状（`api.error.code`）同构，其适配器形状符合性同样待套件实际运行核验。
- **行为保持锚**：既有 28 例全部经 `fixed-python-linux-v1` 路径执行；套件整批通过即证明本修订零行为变化，强于另设回归例。
- 本地离线核验（无 Docker）：`validation/components/x/environment_profile_check.py`——注册表 schema 完整性、摘要重算、v1 条目与 profile.json 互检、构造点导出值一致性、FIELDS 增补与接缝归属声明同步。

## 影响与旧值保留

- 产品文件：`lore_execution/requests.py`、`lore_execution/engine.py`、`lore_runtime/tool_plans.py`、`lore_execution/backend.py`（归属声明）、`lore_execution/environment_profiles.json`（新）；X 套件 `fixtures.py`。发布清单同步登记。
- 旧值：`requests.py` 原 environment 钉定块与 interpreter 三元组由本修订取代，原文保留于 Git 历史；无 `profile_sha256` 的旧请求绑定证据批次绑定旧哈希，仍只证明其原范围，不迁移为新契约通过。
- **非目标**：不开放 network 非 `none` 模式（browser profile 的 egress 策略是后续独立修订）；不实现按 profile 取镜像的创建路径；不在本修订内登记 `linux-browser` profile（须与镜像构建、R 登记、创建路径泛化同批按 §5 流程走）；不改 endpoints 语义。

## 验证环境

本机 Docker 29.1.3（与 profile.json engine_version 一致）、钉定镜像 `python@sha256:78387bc3…` 本地存在（2026-09-14 平台重定位宿主）。X 套件按例运行（`run.py --batch <id> [--case <id>]`）。

## 验证结果（2026-09-15 实际执行）

1. **离线**：`environment_profile_check.py`（evidence/environment-profile-offline-001）PASS——注册表 schema/摘要重算/v1↔profile.json 互检/FIELDS 增补/接缝归属声明。
2. **组件（真 Docker + 真 JSONL 适配器）**：X029 **PASS**（environment-profile-014）、X030 **PASS**（environment-profile-015）——未登记 id 与摘要不匹配均按预登记判据拒收（INVALID_REQUEST），新规则端到端生效。
3. **行为保持的经验证据与边界**：X001 冒烟（environment-profile-012/013）显示 execute 主路径在新校验下端到端跑通（容器创建/运行、exec 运行、输入归档生成），但预登记 oracle 的 Linux 形状物理观测（`--pid host` 的 /proc/cgroup/ns、task_uid/cap_eff）在 Docker Desktop macOS VM 抽象下不可复现——**整批 30 例的正式组件验收仍属 Linux 宿主验证环境**（governance/linux-environment.md），不因本机部分通过而宣称。
4. **平台分支修复（本机首测发现，均按 AGENTS.md 平台纪律落位）**：docker CLI 路径 `DOCKER_CLI`（LORE_DOCKER_CLI 覆盖 > darwin /usr/local/bin/docker > Linux /usr/bin/docker；engine×4 + store×1 + collector×10 统一）；host xattr API 缺失守卫（archives/ordinary_sources `HOST_LISTXATTR`，容器内 unsupported_metadata 仍为绑定观测）；输入归档改确定性 Python tarfile 打包（pax、numeric 1000:1000、无 atime/ctime、无 xattr——与原 GNU 选项语义等价且消除 host tar 差异）；collector 平台事实源切至产品 profile.json（environment.json 保留为历史 G3 记录）；run.py 错误记录补 filename 诊断。发布清单同步（101 产品文件）。



## 修复记录（2026-09-15，接续 Agent）

原落盘的 DOCKER_CLI 分支在 else 侧自引用（赋值右侧引用该名），Linux 平台
导入即 NameError，任何 X 执行无法启动。按本文件注释声明之意图修复为
"/usr/bin/docker"（历史路径）。语义与注释一致，无行为扩展。
