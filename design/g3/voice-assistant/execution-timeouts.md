# 执行超时与存活检查：默认是"到点发 check 事件"，不是"到点杀"

状态：UNVERIFIED 设计稿（第 2 稿，按用户 2026-09-17 修正）。
用户修正："可以是一个**提醒 check 的事件**发出来，默认有个时间；runtime 负责**避免死掉**的情况；
但不是超时工具就不执行之类的。"——即默认不是硬杀，而是**可观测 + 由 harness 决策**；
杀只是最后的资源安全网。
相关：[scheduling.md](scheduling.md)（业务时钟）、[events.md](events.md)、[architecture.md](architecture.md)。

## 1. 结论（修正上一稿）

1. **默认语义：到点发 `sys.tool.check` 事件**（runtime 观测，默认间隔 `check_interval`），
   让等待方知道"这个调用还在跑、多久没动静了"——**runtime 负责不让系统静默卡死**。
2. **怎么办归 harness**（策略）：继续等 / 追加预算 / 主动取消 / 降级 / 标记未知。
   **超时是 harness 的策略判定，不是一个自动的机制动作。**
3. **超时 ≠ 工具没执行，也 ≠ 失败**：调用**已经执行过**。结果只有四类：
   `ok` / `failed` / `timeout`（策略判定）/ `unknown`（无确认结果）。不得把"没结果"写成"没执行"。
4. **资源安全网仍然必须有**（runtime 职责）：硬上限 + 并发/资源上限；到限时
   **回收资源并落 `unknown`/`abandoned`**，明确"结果未知"，不冒充成功或失败。
5. **harness 声明默认与上限**：按工具类别给默认 `check_interval` 与预算，schema 可见、可调低、不得越上限。
6. **不做逐次"请设置超时"提醒**：默认即兜底；长/危险类可在**执行前**要求显式预算（guard），
   而不是在对话里唠叨。
7. **in-band `timeout` 是纵深防御**，不是权威（§7）。

## 2. 为什么默认不杀

- **合法长任务会被误杀**：安装、构建、大文件处理动辄几分钟；30 s 硬杀是错的默认。
- **"无响应"不等于"该放弃"**：连接卡住、远端慢，先要**看见**，再决定。
- **杀会把"未知"伪装成"结束"**：一旦杀掉，副作用可能已发生但结果未确认——
  这是 v5:332/336 与 X 合同明确禁止的（"不确定不重跑"）。
- 所以：**观测优先（check）→ 策略判定（harness）→ 资源安全网（runtime）**。

## 3. 事件

| 事件 | 产生者 | 关键 payload | 语义 |
|---|---|---|---|
| `sys.tool.started` | runtime | `call_id, tool, target, started_at, budget_ms?` | 调用开始（输入边界固定，对齐 v5:149） |
| `sys.tool.check` | runtime | `call_id, check_seq, elapsed_ms, silent_for_ms, last_output_at?, budget_left_ms?` | **存活检查提醒**：默认间隔发出；**不代表要杀** |
| `sys.tool.finished` | runtime | `call_id, outcome(ok\|failed\|timeout\|unknown), exit, side_effects(none\|possible\|unknown), duration_ms` | 调用收束；`timeout` 是**策略判定**的结果 |
| `sys.tool.abandoned` | runtime | `call_id, reason(resource_limit\|lease\|shutdown), last_known_state` | 资源安全网触发：**结果未知**，不是失败也不是没执行 |

- `check` 的**间隔退避**（如默认 10 s → 30 s → 60 s），避免长任务刷爆事实流；
  同一调用同一 `check_seq` 幂等。
- `timeout` 与 `unknown` 的区分很重要：前者是"我们决定不等了"，后者是"我们不知道结果"。
  有副作用的调用即使判定 `timeout`，也要带上 `side_effects: possible|unknown`，恢复时**先查询**。

## 4. 分工

| 谁 | 负责 |
|---|---|
| **runtime** | 执行；存活观测（`check`）；资源安全网（上限/回收 → `abandoned/unknown`）；**绝不**把"无结果"写成"失败/没执行" |
| **harness** | 默认 `check_interval` 与各类预算（写进 conventions/manifest、schema 可见）；收到 `check` 后的策略（继续/追问/取消/降级）；判定何时算 `timeout` |

**收到 `check` 的典型策略**（harness 逻辑，可配）：

- 正常：更新投影里的"进行中"状态，继续等；
- 超过软预算：给用户/上游一句进度（语音场景尤其自然："这个还在跑，稍等"）；
- 超过硬预算或长时间零输出：主动 `cancel`（这时才终止进程组），或降级到替代方案；
- 有副作用且无确认：标 `unknown`，把"先查询再决定"写进后续步骤。

## 5. 与"工具调前提醒设置超时"

- **默认兜底**：不给预算也有默认 `check_interval`，不会静默卡死；
- **schema 可见**：`budget_ms` 有默认值且出现在工具定义里，模型需要时能调；
- **长/危险类显式**：安装/出网/有副作用的工具，harness 的 `guard` **执行前要求**显式预算——
  这是可测的拒绝规则，不是聊天里的提醒。

反例：每次调用都提示"请设置超时"；或只在 prompt 里写"记得设超时"。

## 6. 资源安全网（runtime 职责，"避免死掉"）

"runtime 负责避免死掉"落成三条：

1. **硬上限**（每调用/每 Round/每任务）：超过即回收资源；
2. **并发与总量上限**：防止大量挂起调用耗尽资源；
3. **回收即未知**：回收一个没有确认结果的调用 → `sys.tool.abandoned{reason:resource_limit}` +
   `side_effects: possible|unknown`，恢复路径**先查询**，不重跑冒充接续（v5:332/336、X 合同）。

租约到期属于第 1 条的实现手段之一，但**租约到期不是 stopped proof**（X 合同明文），
必须转成 `abandoned/unknown` 而不是"失败"。

## 7. in-band `timeout` 的价值与局限（不变）

| 它能做什么 | 它不能做什么 |
|---|---|
| 让命令自己早退，给出干净退出码（124） | **忘写就没有**；默认值才可靠 |
| 缩短"到达策略判定"的窗口 | **连接层无响应**时根本没机会执行——只有 runtime 的 `check`/安全网能兜 |
| 对已知长命令做局部收紧 | 只杀**直接子进程**；需 `--kill-after` + 进程组 |
| 在脚本里表达意图 | 命令可 `trap` 信号 |

结论：可以做成 harness 生成脚本时的**默认包装**（可关），但**不是权威**。

## 8. 预登记用例（接 [validation-plan.md](validation-plan.md)）

| ID | 判据 | 相关反例 |
|---|---|---|
| VO37 | **默认可观测**：长调用按默认间隔发 `sys.tool.check`；两次 check 之间系统不静默卡死 | 无任何观测，永久挂起无迹 |
| VO38 | **到点不自动杀**：到达默认/软预算时**不杀**，harness 可选择继续；只有 harness 判定或资源上限才终止 | 30 s 无条件杀，误杀长任务 |
| VO39 | **结果四分类**：`ok/failed/timeout/unknown` 可区分；`timeout` 不写成"没执行"；有副作用带 `side_effects` | 把无结果记成失败或"未执行" |
| VO40 | **资源安全网**：超过硬上限/并发上限时回收资源并落 `abandoned/unknown`；恢复先查询不重跑 | 回收后当失败重试，产生第二次副作用 |
| VO41 | **默认与上限**：harness 默认按类别生效；显式值不得越 runtime 上限，越界被拒且留痕 | 模型设无限预算绕过 |
| VO42 | **in-band 是纵深**：命令级 `timeout` 存在时仍由 runtime 兜底；连接层无响应由 `check`/安全网处理 | 依赖脚本里的 `timeout` 作为唯一保障 |

## 9. 未决

- **U26** 默认 `check_interval` 与退避曲线的数值（先测量再定，v5:349）。
- **U27** 硬上限/并发上限的归属与配置位置（X budget maxima vs task.json policy）。
- **U28** `sys.tool.*` 的正式字段与是否与既有 `sys.tool.result` 合并（进组件合同定 schema）。
- **U29** 命令级 `timeout` 包装是否设为 harness 生成脚本的默认（可关）。
- **U30** `check` 落库粒度：面事实 vs 观测域（长任务少，倾向面事实；但需测量频率）。

## 10. 与现有实现的关系（差异在案）

**现状与本节设计冲突，已登记为待实施修订**：

- 现状：`lore_task/round.py` 的 `_run_shell` 用 `subprocess.run(..., timeout=tool_timeout)`，
  默认 **30 s 硬杀**，超时塌缩成 `sys.tool.result{exit:124}`；无存活观测、不保证整进程组终止。
- 目标：本节 §1–§6（check 先行、不自动杀、四分类结果、资源安全网）。
- 记录：[../amendment-task-tool-liveness-2026-09-17.md](../amendment-task-tool-liveness-2026-09-17.md)
  （含源码位置、工作副本哈希、影响面、实施顺序与门槛）；
  同时登记在 [../task-runtime-contract.md](../task-runtime-contract.md) 的"M1 已知缺口"。
- **未实施前不得声称行为已改**；改后须独立复跑既有 `validation/task_runtime/` 套件 + VO37–VO42。
