# 修订记录：工具执行默认由"30s 硬杀"改为"check 先行"（2026-09-17）

状态：**已实施，独立复跑未做**（2026-09-17 当日实施；离线判据与既有套件已通过，见文末）。
不是验收结论；独立复跑前不得计入"check 先行"的通过。
依据：用户 2026-09-17 裁决"默认应是**提醒 check 事件**，runtime 负责避免死掉，但不是超时工具就不执行"；
设计见 [voice-assistant/execution-timeouts.md](voice-assistant/execution-timeouts.md)。
契约归属：本修订落在 **task runtime（`lore_task/`）**，不属语音专属。

## 1. 修订内容

| | 现状（2026-09-17 工作副本） | 目标 |
|---|---|---|
| 默认行为 | 工具调用到 `tool_timeout`（默认 **30 s**）**直接终止** | 到默认间隔**发 `sys.tool.check`**（存活提醒），**不自动终止**；怎么办由 harness 决定 |
| 终止时机 | 无条件（固定超时） | 仅当 harness 判定 `timeout`，或触发 runtime 资源安全网 |
| 终止范围 | `subprocess.run(timeout=)` 杀**直接子进程** | 终止时 SIGTERM→宽限→SIGKILL **整进程组** |
| 结果语义 | 落 `sys.tool.result{exit: 124}`（超时被塌缩成一个退出码） | 四分类 `ok / failed / timeout / unknown`，附 `side_effects`；`sys.tool.abandoned` 表示资源回收导致的**未知** |
| 存活观测 | 无 | `sys.tool.started` / `sys.tool.check` / `sys.tool.finished` / `sys.tool.abandoned` |

## 2. 现状事实（可复核）

源码位置（工作副本；`lore_task/` 当前**未入 git**，哈希为工作副本内容）：

| 文件 | 行 | 内容 | sha256（2026-09-17） |
|---|---|---|---|
| `lore_task/round.py` | 53–55 | `_run_shell` 用 `subprocess.run(["/bin/sh","-c",script], …, timeout=timeout)` | `e6649d5d2e923278d4b0d0282b65cf665d7c63326892d27e291d640d5cb45789` |
| `lore_task/round.py` | 371 | `def run_round(base, provider, *, max_steps=8, tool_timeout: float = 30.0)` | 同上 |
| `lore_task/round.py` | 488–490 | `except subprocess.TimeoutExpired: out = {"exit":124,"stdout":"","stderr":"timeout"}` | 同上 |
| `lore_task/round.py` | 491 | 落事实 `sys.tool.result`（含 `exit`） | 同上 |
| `lore_task/cli.py` | 58–59 | `--timeout 180.0`、`--tool-timeout 30.0` | `f47d6090e55fee72f3cb2bd7985c5c80bbe0340e10a58984c3066611d9eca13d` |
| `lore_task/cli.py` | 173 | `run_round(..., tool_timeout=args.tool_timeout)` | 同上 |

代码仓库 HEAD：`cfe7ce9eaca4101430bd67e2288694e8cb2705c8`（`lore_task/` 为未跟踪工作副本，故哈希只绑定当次工作副本）。

## 3. 为什么改（反例先行）

1. **误杀合法长任务**：安装/构建/大文件处理动辄几分钟，30 s 无条件终止是错的默认。
2. **塌缩语义**：`exit 124` 把一个"我们不知道结果"的状态写成了看起来像"失败/结束"的退出码；
   对可能有副作用的调用，这直接违反"不确定不重跑"（v5:332/336、X 合同）。
3. **终止不彻底**：`subprocess.run(timeout=)` 不保证**整进程组**终止；孙进程可能继续占资源。
4. **无存活观测**：卡住时系统没有任何"还在跑"的事实，等待方无从判断，只能等一个固定秒数被砍。

## 4. 影响面

- **产品代码**：`lore_task/round.py`、`lore_task/cli.py`（`tool_timeout` 参数语义要重新定义：从"硬截止"变为"软预算/check 间隔"或另立参数）。
- **事实契约**：新增 `sys.tool.*` 观测；`sys.tool.result` 的字段扩展（`outcome`、`side_effects`）。
- **既有校验器**：`validation/task_runtime/*` 经查**没有断言 `exit == 124`**（只断言 `exit 126` 未授权与 `exit 0`）→ 影响小；
  但**必须保留 `exit 126`（未授权目标）与 `exit 0`（成功）语义不变**。
- **文档**：[task-runtime-contract.md](task-runtime-contract.md) 的"M1 已知缺口"需标本条；
  [voice-assistant/execution-timeouts.md](voice-assistant/execution-timeouts.md) 是设计出处。
- **历史证据**：既有 task_runtime 证据绑定旧行为，**不迁移**为"check 先行"的通过。

## 5. 旧值保留

- 现状行为、源码位置与哈希记录于本文件，**不覆盖**；
- `exit 124` 作为"超时"的旧语义在兼容期可继续出现，但新实现应同时给出 `outcome`；
  两者并存不是双权威，`outcome` 为准、`exit` 为兼容镜像。

## 6. 实施顺序与门槛（不得跳步）

1. **先预登记用例**：VO37–VO42（[voice-assistant/validation-plan.md](voice-assistant/validation-plan.md) E4）落为可执行判据；
2. **再实现**：check 事件 + 结果四分类 + 进程组终止 + 资源安全网；
3. **独立复跑**：既有 `validation/task_runtime/` 套件 + 新用例，判据不放宽；
4. 未通过前，本修订状态保持"待实施"，且**不得**以"设计已定"声称行为已改。

## 7. 未决

- **D1** `tool_timeout` 参数的迁移：改名（`--tool-budget`）还是保名改语义（易误读）。
- **D2** `check` 落面事实还是观测域（频率待测）。
- **D3** 硬上限/并发上限的配置来源（X budget maxima vs `task.json.policy`）。
- **D4** 资源安全网与既有租约（M03/M04 的 ~30 s 租约）如何对齐，避免两套计时。

## 8. 实施记录（2026-09-17 当日补记；上方第 1–6 节原文保留）

- §6 顺序已执行：先落预登记可执行判据 `validation/task_runtime/offline_tool_liveness.py`
  （VO37–VO42 + exit 126/0 保持性），再改实现，再复跑。
- 实现：`lore_task/round.py`（托管执行 `_run_shell_managed`：select 增量读、check 退避、
  进程组 SIGTERM→宽限→SIGKILL、硬上限回收即 `abandoned/unknown`）、`lore_task/cli.py`
  （`--tool-timeout` 移除，新增 `--tool-check-interval/--tool-budget/--tool-hard-cap`，取舍见
  [task-runtime-contract.md](task-runtime-contract.md) 修订记录第 3 条）。
- 契约：`sys.tool.result` 增加 `outcome/side_effects/duration_ms/call_id`（U28 取合并），
  十个 harness 的契约副本收敛为规范一份。
- 结果：`offline_tool_liveness.py` 全部 PASS；既有 `validation/task_runtime/offline_*.py` 全部通过，
  判据未放宽（唯一断言文本更新：invariants 的拒绝消息动词随 deliver→relay 更名，判据本身不变）。
- **未做**：独立验收者复跑（AGENTS.md 门槛）；因此本修订在独立复跑前保持"已实施未独立复跑"状态。
