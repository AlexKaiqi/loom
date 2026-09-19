# Loom

面向 Unix（macOS/Linux）的可持久接续 Agent Runtime。Runtime 负责登记、受理、开轮与恢复；Harness 决定模型看见什么、何时结束一轮。

**开发中的源码快照，尚未完成系统验收。** 可安装的是 Work 目录 Runtime（命令 `loom`），不包含旧的 NATS/Docker/Pi 装配。完整状态见 [验证状态](docs/validation-status.md)。

## 初次使用

需要 Python 3.10+。尚未发布到 PyPI，从本仓库安装：

```sh
git clone https://github.com/AlexKaiqi/loom.git
cd loom
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

### 1. 初始化 Host

```sh
loom init ~/loom-works
```

首次 `init` 会写入默认 works 根（`$XDG_CONFIG_HOME/loom/config.json`）。权威文件是 `~/loom-works/.loom-authority.json`，不是业务成功记录。

### 2. 先离线走通（不需要模型）

```sh
loom create demo --harness kernel
loom admit demo --kind work.objective.set \
  --payload '{"objective":"write hello.md with one line hello"}'
loom run demo --provider faux --faux-response \
  '{"action":{"type":"shell","script":"printf hello > hello.md"}}' --faux-response \
  '{"action":{"type":"emit","kind":"work.completed","payload":{"evidence_refs":["hello.md"]}}}'
loom status demo
loom facts demo
```

`~/loom-works/demo/surface/content/` 是这个 Work 的认知面。`loom run` 一次只开一轮；返回 `no_trigger` 表示没有新的已受理事实可开轮，不是安装失败。返回 `recovery_needed` 时先 `loom recover demo`。

### 3. 配置真实模型后再跑

Provider 必须是 OpenAI 兼容的 `/chat/completions`。`base_url` 写到 `/v1` 这一层，不要带 `/chat/completions`。密钥只放环境变量或 `~/.env`，不要写入 `loom config`。

```sh
cp .env.example ~/.env    # 编辑 LOOM_API_KEY=
loom config provider.base_url https://api.openai.com/v1
loom config provider.model gpt-4o
export LOOM_API_KEY=...   # 若不用 ~/.env
loom run demo
```

若接口回显的模型名与配置不一致，再设 `loom config provider.model_alias <回显名>`。

### 4. 同时跑另一种组合

其它策略是 git 分支上的同一棵 `lore_harness/` 树，用 worktree 挂出来。`--harness` 可以是路径或 `loom harnesses` 列出的分支名。说明见 [Harness 变体](docs/harness-variants.md)。

日常命令：`loom status`、`loom facts <id>`、`loom recover <id>`。跨 Work 才需要 `relate` / `relay`。

## 从哪里看

- [规范](spec/)：系统契约（L0 身份、L1 架构）。`design/` 与现行代码都不是规范。
- [系统设计 v5](harness-runtime-revised-v5.md)：历史来源，不能覆盖 spec。
- [GOAL.md](GOAL.md)：完整开发与独立验收目标；发布源码不是完成目标。
- [设计导航](docs/design.md)：性质、论证、组件契约和实现的对应关系。
- [开发说明](docs/development.md)：Linux 依赖、装配入口和目前的复现缺口。
- [依赖与来源](docs/dependencies.md)、[第三方声明](THIRD_PARTY.md)。

## 源码结构

| 目录 | 职责 |
| --- | --- |
| `lore_work/` | Work 目录 Runtime 与 `loom` CLI |
| `lore_harness/` | 当前 checkout 的 Harness 树（kernel；其它组合见 [变体](docs/harness-variants.md)） |
| `lore_runtime/` | 装配、共享 Runtime、推进与组件适配（旧组合线，不是 `loom` 包） |
| `lore_control/` | R：受理责任、持久状态、权限与租约；使用 Python SQLite |
| `lore_events/` | E：NATS JetStream 事件流、读取位置与通知 |
| `lore_files/` | F：Git 文件版本、捕获、发布与恢复边界 |
| `lore_execution/` | X：Docker 执行、挂载、资源及结果归档 |
| `lore_session/` | S：Pi 会话、Node 边界、原始结果与接续引用 |
| `lore_provider/` | 模型 HTTP 转发、凭据隔离与预算准入 |
| `harnesses/` | 外部定义的最简 Harness 和 Runtime Harness |
| `design/`、`governance/` | 设计、契约、用例、执行原则与验收规范 |
| `validation/`、`simulations/` | 组件和组合验证程序、顶层模拟 |
| `research/` | 固定版本的开源调研与机制实验源码 |

仓库名为 Loom；Python 实现包暂保留 `lore_*`。可安装入口是 `loom-runtime`（命令 `loom`）。

## 源码检查（旧组合线）

完整 `lore_runtime` 装配仍依赖 Node/Pi/NATS/Docker，见 [开发说明](docs/development.md)。下面两项不调用模型或 Docker，不能代替运行时验收：

```sh
python -m pip install -r requirements.txt
python scripts/check_source.py
python -m unittest simulations.test_observer
```

## 开发约束

先定义目标与性质，再确定抽象、契约和可拒绝错误的用例；组件独立验证后才能组合。保留失败与未运行状态，不通过删用例、放宽预算或改预期制造成功。入口为 [AGENTS.md](AGENTS.md)、[执行指南](governance/execution-guide.md)、[证据指南](governance/evidence-guide.md)和[检查表](governance/checklists.md)。

本次公开包含源码、设计和验证程序。模型请求与响应、凭据、运行快照、数据库、原始大证据包、研究仓库副本和依赖二进制保留在原开发环境，没有进入公开仓库。历史研究和审查中的通过结论有其原版本与范围；公开摘要不替代原始证据。

项目自身暂未指定开源许可证；第三方文件按其已有许可与声明保留。
