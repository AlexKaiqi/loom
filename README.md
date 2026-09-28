# Loom

Loom 把长期工作上下文、完整事实和推进策略保存在 Work 中。Go Runtime 托管输入与执行责任；Harness 决定投影、上下文选择、工具和继续策略；模型组件复用 Pi；任务环境通过独立 Provider 的远程协议访问。

[HTML 设计书](docs/loom-design-book.html) 的各分篇共同构成产品规格、架构、协议、技术基线和验收的**唯一真相源**。总入口提供阅读顺序；正文在 `docs/design-book/` 按契约与接入职责维护，共用样式和交互脚本。本页及各 README 只说明操作，不另立规范。实现仍在按设计书重构；组件测试通过不等于全部验收完成。

## 安装

Linux 默认直接安装到 `/opt/loom`，使用管理员预先准备的 NsJail、cgroup v2 执行绑定及 Go、Node、Python 等工具；无需 Docker。安装会锁定独立版本的 Runtime、Pi 和 Python 依赖，并真实检查受限进程后激活。准备方法见[开发操作说明](docs/development.md)。

```sh
# 在准备好的 Linux 设施中，以管理员身份执行
./install.sh --execution-config /etc/loom/execution.toml
loom setup --sandbox-provider ssh-process/v1 \
  --sandbox-endpoint ssh://linux-facility.example:22 \
  --sandbox-options /private/loom-process-options.json \
  --sandbox-key-file /private/loom-process.key
```

macOS 或希望使用容器承载 Work 设施时，显式选择 Docker（需要 Python 3.11+ 和运行中的 Linux Docker 引擎）：

```sh
./install.sh --deployment docker
export PATH="$HOME/.local/bin:$PATH"
loom setup --sandbox-provider ssh-process/v1 \
  --sandbox-endpoint ssh://linux-facility.example:22 \
  --sandbox-options /private/loom-process-options.json \
  --sandbox-key-file /private/loom-process.key
```

所有 Work 共用一套 Linux 设施，各自按 Unix 身份和受限文件视图执行。默认工作根为 `~/Loom`；`--workspace-root DIRECTORY` 可重复指定。Docker 部署将这些根挂载给控制端，模型的 Work Bash 仍只看到获准的文件。

Work 设施与任务 Provider 独立配置。普通代码默认选 [SSH Process](deploy/ssh-process/README.md)：设施预置一次，每次只启动 systemd/NsJail 受限进程，通过 SSH/SFTP 远程访问，不创建任务容器。先按该操作页准备设施并生成上述 options 文件。需要容器部署时仍可显式选择 [OpenSandbox](deploy/opensandbox/README.md) 和 `--sandbox-provider opensandbox/v1`。Provider 参数属于宿主 `[profiles.code.options]`，Runtime 核心不解释。

`setup` 隐藏输入密钥，宿主配置保存在安装前缀的 `host-state/`，不进入镜像或 Work。已有未决效果保持原 Provider 和参数；不支持旧绑定的版本不会猜测或重放。更换部署使用独立安装前缀，保留原版本核对旧责任。

## 使用

```sh
mkdir -p ~/Loom/project
loom new ~/Loom/demo --userspace ~/Loom/project
cd ~/Loom/demo
loom ask "阅读项目，完成修改并说明验证结果"
loom status
```

`ask` 保存输入后推进。已有未交接 Round 时，新输入排队。`loom resume` 接续已确认的继续点；`loom recover` 先撤销旧执行权限并确认进程组停止，再判断能否继续。结果未知的外部操作不会自动重放。

使用默认配置创建 Work 时，同一项目复用已登记的资源身份，不同项目自动使用不同的逻辑名称。`--definition` 提供的资源声明保持原样。

任务修改保存为每个 Target 的独立资源副本，共享项目不会自动被覆盖。查看保存的结果：

```sh
loom restore-resource . app ~/Loom/demo-result --target default
```

模型通过普通 Bash 维护 `surface/main.md`：引用文件、保留当前理解、调整可见事实。默认不会自动摘要或按年龄归档。Plan 是可选的普通文件/策略扩展。

```text
work/
  work.toml           # 逻辑资源、模型与 Harness 声明
  harness/            # 可编辑的候选策略；运行使用确定快照
  surface/main.md     # 长期维护的上下文模板与可见性选择
  .loom/
    identity.json
    state.sqlite      # 完整事实、责任与检查点
    versions.git/     # 文件原始字节的历史版本
    records/          # 不可变输入、结果、投影与必要内容
    views/            # 可重建的只读视图
```

`loom select-harness .` 选择候选版本用于后续 Round；当前 Round 和恢复继续使用原策略。

```sh
loom history .
loom inspect . CHECKPOINT_ID ~/Loom/history-view
loom fork . CHECKPOINT_ID ~/Loom/exploration
```

查看历史不执行代码。Fork 使用新 Work 身份、独立副本，不继承宿主权限、活跃输入或旧效果的重放权。原历史与未决责任继续保留。

## 能力与源码入口

| 能力 | 唯一实现归属 | Loom 使用的公开交接 |
| --- | --- | --- |
| 持久工作 | 本仓库 `runtime/` | 输入、授权、事实、检查点、文件保管与恢复 |
| 模型访问 | [Model Resource Hub](components/model-resource-hub/model-invocation/pi/README.md) | 一次原生模型请求／结果；无 Agent 循环 |
| 隔离执行 | [OnDemand Sandbox](components/sandbox/execution/README.md) | 执行／查询／取消／释放、原生身份与测得的工作目录 |
| 参考工作策略 | [Worksurface](components/worksurface/README.md) | 投影、继续判断、Surface 修复、Pi 循环；通过宿主调用模型和工具 |

专用代码、规则、依赖和测试随能力维护。`components/` 是固定提交的 Git submodule；`deploy/work` 只组装 Loom 的发布环境。共享 FD 3 绑定由 [Worker RPC SDK](runtime/worker-rpc/README.md) 提供。控制器只导入沙箱公开 Go 模块，供应商实现仅在 CLI 组合入口注册。

首次获取或切换组合版本后执行 `git submodule update --init --recursive`。子仓库包含私有仓库，需要对应 Git 读取权限；构建 Go 模块时设置 `GOPRIVATE=github.com/AlexKaiqi/ondemand-sandbox`。Docker 安装现在要求宿主 Go 1.25+，先生成锁定依赖快照再送入构建，凭据不进入镜像。

原 `agent.run` 配置需拆成模型 worker 和 `[drivers]` 两个入口，固定 Harness manifest 需声明 `driver = worksurface/v1`；见[配置示例](deploy/config.example.toml)。没有已批准 driver 时拒绝推进，不回退旧模型循环。已有 Work 的活动 Round 继续保留原身份和责任，升级前应完成或显式处理未决 Round，再选择新 Harness。

本次保留 schema-2 Work；设计书中的 schema-3／Temporal 目标仍须独立迁移，见[迁移范围](docs/capability-migration.md)。构建与验证入口见[开发说明](docs/development.md)。
