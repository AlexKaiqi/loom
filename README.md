# Loom

Loom 是一个持久、可恢复的 Harness Runtime。Go 控制端托管 Work、事实、授权与外部效果；独立 Node worker 复用 Pi 的 provider 适配和模型—工具循环；外部 Harness 定义投影与推进策略；任务命令由远程 OpenSandbox 执行。

产品目标、开发原则和不变量只有一份：[SPEC.md](SPEC.md)。当前组件和数据流见[实现架构](docs/architecture.md)，后续重构采用[目标架构](docs/architecture-target.md)，当前精确行为见[契约](docs/contracts)，构建与验证见[开发说明](docs/development.md)。

当前代码尚未实现共享 Work 执行环境、长期 Surface 模板、由模型控制的事实可见性、持久跨 Work 订阅及任意已记录点恢复。下面的安装和功能说明描述现有实现，不代表这些目标已经完成。

## 安装与使用

当前从源码安装，需要 macOS/Linux、Go 1.24+、Node.js 24、npm、Python 3.10+ 和 Git。安装器自动构建 Runtime、安装模型组件和独立 Harness Python 环境，无需手动填写组件路径或激活 venv。

```sh
./install.sh
export PATH="$HOME/.local/bin:$PATH"
loom setup
```

`setup` 引导选择 Pi 自带目录中的模型、填写独立部署的 OpenSandbox 地址，并隐藏输入密钥。配置与私有密钥保存在 `~/.config/loom/`，不会放进 Work。需要已有模型服务凭据和可访问的 [OpenSandbox 服务](deploy/opensandbox/README.md)；安装器不部署远程执行服务。复杂认证和自定义模型见[开发说明](docs/development.md)。

准备一个已有的任务文件目录，然后：

```sh
loom new ~/works/demo --userspace ~/projects/demo
cd ~/works/demo
loom ask "阅读项目，制定计划并完成第一步，把结果写进报告"
loom ask "根据报告继续下一步"
loom status
```

`ask` 接收自然语言并展示模型答复；文件结果在 `surface/` 和授权的任务目录。失败时保留输入并显示请求 ID；重试同一条消息使用原 `--request-id`，已处理的请求不会再次调用模型或工具。已有运行中或暂停的 Round 时，新消息入队；已确认暂停点用 `loom resume`，随后用 `loom run` 处理待办。未知效果不自动重放。

重新执行 `./install.sh` 即可安装新版本，配置和既有 Work 不变；失败不替换原安装。可以用 `--prefix /path/to/installation` 自定义安装目录。

## 最小 Harness

以下是当前 `kernel` 的行为。目标设计将 Plan 作为可选扩展，将 Archive 改为模型经普通文件操作控制事实可见性；当前自动门槛归档不能作为该目标的验收证据。

默认 `kernel` 已包含“目标 → 模型 → 远程 Shell → 文件反馈 → 报告”的闭环，以及两项辅助策略：

- **Plan**：普通 `surface/plan.md` 清单，投影当前与下一步，要求完成项引用证据。它帮助模型组织工作，不是独立验收器，也没有自动阶段门控。
- **Archive**：上下文达到 Harness 配置的大小门槛后，将原生对话原文保存到 `surface/archive/`，后续请求保留引用与最近完整工具对话。它是可回读的无损归档，不是自动摘要；超大且不可分割的输入明确拒绝。

`surface/report.md` 保存结果，`surface/notes.md` 保存笔记。归档和计划都由外部 Harness 实现，Runtime 不内置这些策略。完整边界见 [Kernel 契约](docs/contracts/kernel-harness.md)。

## 目录

```text
runtime/             Go 控制端、SQLite 状态、宿主授权、Work 与 Sandbox 客户端
services/model/      独立 Node/Pi 模型组件
harnesses/kernel/    外部 Harness、策略配置与初始 Surface 文件
deploy/              主机配置样例与 OpenSandbox 部署资产
tests/               组件、协议与黑箱验收入口
docs/                当前架构、契约和开发说明
```

每个 Work 的完整持久状态集中在自己的目录：

```text
work/
  work.toml
  harness/
  surface/
    plan.md
    report.md
    notes.md
    archive/         # 按需生成
  .loom/
    identity.json
    state.sqlite
    versions.git/
    artifacts/
    dependencies/
```

当前 `kernel` 提供 `surface/` 的初始文件，系统状态集中在 `.loom/`；目标设计把初始 Surface 的组装交给 Work 模板和普通文件操作。当前 Work 包含外部 Userspace 的可验证快照，可在另一宿主恢复。Userspace 仍是单独授权的执行目录；复制 Work 不复制授权或凭据。当前规则见 [Work 契约](docs/contracts/work.md)，跨宿主导出、导入和恢复步骤见[开发说明](docs/development.md)。
