# Loom

Loom 把长期工作上下文、完整事实和推进策略保存在 Work 中。Go Runtime 托管输入与执行责任；Harness 决定投影、上下文选择、工具和继续策略；模型组件复用 Pi；任务环境通过 OpenSandbox 远程访问。

[HTML 设计书](docs/loom-design-book.html) 是产品规格、架构、协议、技术基线和验收的**唯一真相源**。本页及各 README 只说明操作，不另立规范。实现仍在按设计书重构；组件测试通过不等于全部验收完成。

## 安装

宿主需要 macOS/Linux、Python 3.11+ 和运行中的 Linux Docker 引擎。安装器构建一个共享 Linux 环境，里面提供 Go Runtime、Node/Pi、Python 和 NsJail；不同 Work 使用独立 Unix 身份与受限执行域。

```sh
./install.sh
export PATH="$HOME/.local/bin:$PATH"
loom setup
```

默认把 `~/Loom` 映射给控制端。也可在安装时指定 `--workspace-root /path/to/works-and-projects`，多个根可重复指定。模型的 Work Bash 只看到当前获准的文件视图。

`setup` 配置模型和独立的 [OpenSandbox 服务](deploy/opensandbox/README.md)，隐藏输入密钥。安装的宿主配置保存在 `~/.local/share/loom/host-state/`，不进入镜像或 Work。安装、升级及完整使用流程的验证入口在 `tests/install/` 和 `tests/onboarding/`。

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

## 源码入口

- `runtime/`：Go 控制端；执行设施、存储、授权和适配器有独立包边界。
- `services/model/`：独立 Node/Pi 模型组件，通过 FD 3 的 JSON-RPC 通信。
- `harnesses/kernel/`：参考 Python Harness；`templates/` 提供初始 Surface。
- `deploy/`：共享 Work 环境及独立 OpenSandbox 的部署构件。
- `tests/`：组件、协议、真实环境和组合检查。

构建、配置、迁移与验证入口见[开发操作说明](docs/development.md)。
