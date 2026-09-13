# Linux 开发与运行边界

当前公开仓库提供产品源码、设计依据和验证代码。安装 Python 依赖后可以直接做源码语法与导入检查；真实 Runtime 装配仍需要重建宿主配置和固定依赖，尚不是 `clone` 后直接运行 M01 的发行包。

## 现在可以运行的检查

在仓库根目录使用 Linux Python（开发环境为 Python 3.10）：

需要 Python 3.10+ 及可用的 `venv`/pip；Debian 或 Ubuntu 通常需先安装系统包 `python3-venv`。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/check_source.py
```

Python 产品代码的外部包依赖是固定的 `nats-py==2.15.0`，不需要其可选 extras。以上检查不构造 `ExecutionStore`、不启动 NATS/容器、不调用模型，也不验证 TypeScript 执行、隔离或恢复能力。源码检查通过只说明这一层检查通过。

## 真实装配需要哪些输入

入口是 [`assemble(config, *, credential_provider=None, checkpoint=None)`](../lore_runtime/bootstrap.py)。`config` 必须恰好含以下五个顶层字段：

| 字段 | 实际接口要求 |
| --- | --- |
| `runtime` | `control_db`、`files_dir`、`execution_dir`、`session_dir` 为真实、无路径别名的绝对路径；另含 `engine_endpoint`、`nats_url`、`authority`、`worker_id`、`event_profile`。 |
| `startup_root` | 宿主控制目录，与 Surface、Workspace 分离。已有完整状态时，`assemble` 调用 `StartupAssets.open_existing` 核对原配置，不重新捕获旧输入来掩盖状态变化。 |
| `startup` | `principal`、`namespace`、`sources`、`code_sources`、`profile_ref`、`request_template_ref`、`deps_mount`、`model`、`capability_limits`；`original_refs` 可选。精确检查见 [`StartupAssets`](../lore_runtime/startup_assets.py)。 |
| `provider` | `root`、`endpoint={scheme,host,port}`、`principal`，可选固定 `budget`、`timeout`；现实现使用固定模型协议，不能仅换一个字符串就声称支持其他模型。见 [`ProviderOwner`](../lore_runtime/provider_owner.py)。 |
| `initial_session_ref` | 初始值为 `owner="S"`、`namespace`、`surface_id`、`session_id`、`session_generation=1`、`confirmation_request_id=None`。后续必须使用真实原 Session 引用。 |

`startup.sources` 必须恰好有 `surface`、`workspace`，每项为 `{path, resource_id}`，指向彼此不嵌套的普通目录。`code_sources` 的键集合由源码 `CODE_FILES` 固定：六个 Node 适配文件和三个外部 Harness 文件；每项绑定实际 `{path, sha256, bytes}`。`profile_ref`、`request_template_ref` 同样绑定真实文件字节。`model` 不得包含密钥或任意宿主连接配置。

目录关系也受校验：`runtime.execution_dir` 对应 `startup_root/X-state`，`event_profile.input_root` 对应 `startup_root/E-inputs`；R、E、Session 与 provider 的 principal/namespace/authority 必须一致。事件 profile 还明确存储、保留和大小限制，不能只给一个 NATS URL 代替。具体字段可对照 [`EventService`](../lore_events/service.py) 与 [`Runtime`](../lore_runtime/runtime.py)。

凭据只经 `credential_provider` 这个可信宿主回调提供；不要写入配置 JSON、Node 环境、镜像或证据。没有回调可用于固定 localhost HTTP 验证，但这不构成真实模型验证。

## 固定依赖和物理 manifest

实际运行依赖 Linux 文件租约、inotify、目录交换、`/usr/bin/git`、`/usr/bin/docker` 和 Unix Docker Engine。当前 [`X profile`](../lore_execution/profile.json) 固定 Engine 28.0.1、镜像 digest/ID 与 seccomp 摘要；构造 X 就会读取 Engine 版本和镜像身份。换 Engine、镜像或内核不能沿用旧环境通过结论。

Node 运行使用 Node 24.21.0，以及 Pi commit `71dca871bc80b6bc97be37f0ca3189399d651fff` 的已记录单行派生补丁、tsx/esbuild 和所需源码。它通过 [`loadPi`](../lore_session/node/session.mts) 加载 Pi 的真实 TypeScript 模块，不依赖一个已经发布并完整构建的本项目 npm 包。容器内 `/opt/node`、`/opt/lore/research/repos/pi`、`/harness`、`/input` 是当前协议布局，不能用宿主用户名路径替换。

要在新宿主生成可用配置，需要完成这些具体步骤：

1. 按固定版本和摘要准备 Node/Pi/tsx 依赖以及第三方许可证，保留上游与派生补丁的区别。
2. 创建独立只读依赖目录，逐文件核对 bytes/SHA、模式和符号链接，写入固定 `tsconfig.json`。当前所选依赖约 141 MB，未随源码附带历史运行副本。
3. 在新位置重新生成 `deps_mount`：`role="dependencies"`、`target="/opt"`、`read_only=true`，以及真实 `source={path,dev,ino}`、`manifest_ref`、`content_ref`。`content_ref` 需绑定原依赖选择 manifest 与生成配置；校验由 [`NodeProfile`](../lore_execution/node_profile.py) 和 [`ordinary_sources`](../lore_execution/ordinary_sources.py) 完成。
4. 根据新文件重新绑定 profile、request template 与代码引用，再生成上述装配配置。旧 manifest 中的绝对路径、inode、生成原件引用不是可移植模板；不能只做路径字符串替换后保留旧 SHA。
5. 提供符合 E profile 的真实 NATS JetStream 服务、固定 X 环境及两个普通资源目录，再运行装配验证。

开发机的 M01 入口还读取未发布的 `validation/session-plan-evidence/context-independent-001/workspace/original-host`，其中三份文件是 `profile.json`、`request-template.json`、`dependencies-manifest.json`。依赖 manifest 又引用旧 XN 验证目录中的物理依赖树。测试 NATS 启动器依赖本地固定二进制；M01 产物检查另有固定 Markdown 解析器来源。公开源码不包含这些大证据目录，因此当前不能直接复用开发机命令。这里列出的是重建所需边界，不声称已经提供了自动安装器。

## 装配后的调用顺序与验证范围

[`Runtime`](../lore_runtime/runtime.py) 现有方法为 `register`、`start`、`open`、`drive_until`、`query`、`close`：

- `assemble` 返回 `registrations_spec` 和 `initial_refs`，但不自动登记或启动 invocation。登记时使用原 spec 和稳定请求 ID；同资源改一个请求 ID 再登记会冲突。
- `start(principal, request)` 的请求含 `id/namespace/kind/payload`。invocation payload 绑定 `resource_id/resource_revision`、Harness/能力/Session/原结果引用，以及 `input_binding` 中的事件起点、Surface 版本、前序 Session 和两个执行目标。不能用自由文本 prompt 替代这些关联。
- `await open()` 后才能 `await drive_until(principal, request_id, deadline_monotonic=...)`。`query` 读取原责任，不重新执行模型或工具。`await close()` 关闭共享句柄；它本身不是任务容器已释放的证明。

验证证据区分源码检查、单组件、组件接线、完整系统用例和真实模型样本。固定 localhost 回复证明传输与装配机制，不能替代模型完成任务；`MISSING`、`UNVERIFIED`、只准备 fixture 和未运行项均不算通过。M01 必须同时核实际产物、R/F/X/S 原件、事件和资源；M02/M03 等权限与故障轨迹另有独立判据。复制旧报告或新环境语法检查通过，都不能赋予新环境相同的物理验证结论。
