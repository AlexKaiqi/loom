# Loom

面向 Unix 系统（macOS/Linux）的可持久接续 Agent Runtime。Runtime 管理状态、事件和隔离执行；Harness 独立定义模型可见上下文与推进策略。

**当前是开发中的源码快照，尚未完成系统验收。** M01 最简真实模型闭环已按 2026-09-14 修订预算在 Linux 容器内取得整批 6/6 真实模型通过（批次 m01-real-2026-09-14z，glm-5.3）；修订记录与反例证据见 [验证状态](docs/validation-status.md)。M02 的 15 个固定响应安全场景已通过独立证据审查。完整状态和限制见 [验证状态](docs/validation-status.md)。

## 从哪里看

- [系统设计 v5](harness-runtime-revised-v5.md)：系统目标、边界、抽象和核心判断。
- [GOAL.md](GOAL.md)：完整开发与独立验收目标；发布源码不是完成目标。
- [设计导航](docs/design.md)：性质、论证、组件契约和实现的对应关系。
- [开发说明](docs/development.md)：Linux 依赖、装配入口和目前的复现缺口。
- [依赖与来源](docs/dependencies.md)、[第三方声明](THIRD_PARTY.md)。

## 源码结构

| 目录 | 职责 |
| --- | --- |
| `lore_runtime/` | 装配、共享 Runtime、推进与组件适配 |
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

仓库名为 Loom；现有 Python 包保留 `lore_*`，以便对应已验证的代码版本。

## 可直接运行的源码检查

在 Unix（macOS/Linux）系统中执行：

需要 Python 3.10+ 及可用的 `venv`/pip；Debian 或 Ubuntu 通常需先安装系统包 `python3-venv`。

```sh
git clone https://github.com/AlexKaiqi/loom.git
cd loom
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/check_source.py
python -m unittest simulations.test_observer
```

这两项检查不调用模型或 Docker，不能代替运行时验收。完整 Runtime 装配仍依赖需要在新宿主重新生成的 Node/Pi 依赖树与物理身份 manifest；现有 M01 入口也引用了未随源码发布的本地准备产物，详见[开发说明](docs/development.md)。目前没有可直接照抄的生产部署命令。

## 开发约束

先定义目标与性质，再确定抽象、契约和可拒绝错误的用例；组件独立验证后才能组合。保留失败与未运行状态，不通过删用例、放宽预算或改预期制造成功。入口为 [AGENTS.md](AGENTS.md)、[执行指南](governance/execution-guide.md)、[证据指南](governance/evidence-guide.md)和[检查表](governance/checklists.md)。

本次公开包含源码、设计和验证程序。模型请求与响应、凭据、运行快照、数据库、原始大证据包、研究仓库副本和依赖二进制保留在原开发环境，没有进入公开仓库。历史研究和审查中的通过结论有其原版本与范围；公开摘要不替代原始证据。

项目自身暂未指定开源许可证；第三方文件按其已有许可与声明保留。
