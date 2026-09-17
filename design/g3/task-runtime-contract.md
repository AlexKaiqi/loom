# 任务目录 runtime ↔ harness 接口（M1 实现契约）

状态：**实现中的接口记录**，不是验收结论。对应实现 `lore_task/`（runtime）与 `lore_harness/goal/`（第一个 harness）。设计依据：[task-directory-landing.md](task-directory-landing.md) §4.4–4.7。

## Runtime 负责（机制）

- 基础树：`task.json`、`harness/manifest.json`、`surface/{content,head,facts.jsonl}`、`ledger/`；按需 `session/`、`derived/`。
- 事实流单写者：只有 runtime 追加 `surface/facts.jsonl`（append + fsync）；每条含 `seq/id/kind/source/payload/digest`。
- 触发器水位：`ledger/rounds.jsonl` 的 `trigger_seq` 决定"哪些事实已求值过"，与提交水位 `head.facts_end` 分开——已声明的事件仍能被下一次求值看到。
- Round 执行：求值触发 → 投影 → 模型 → 工具 → 落事实 → 提交；提交顺序见 landing §6。
- `head` 是唯一提交点（原子替换），每次提交含 `revision`（content 树 digest）+ `facts_end` + `round_id` + `ledger_seq`。
- 受理门：`ingest()` 对外来事实做幂等去重与冲突拒绝；未声明的 kind 直接拒绝。
- **harness 只读**：加载 harness 模块时禁用字节码写入；每轮开始/结束重算 harness digest，变化即响亮失败。
- 模型调用：`provider.complete(messages)`；凭据只在进程内，不写任务目录。
- 模型交互写 `session/rounds/<round_id>.jsonl`（观测区），**不是事实**；`reasoning_content` 与 `usage` 记在这里。

## Harness 负责（策略）

`harness/manifest.json` 声明与 `roles/` 下的普通代码模块。角色钩子：

| 角色 | 钩子 | 语义 |
|---|---|---|
| `rounds` | `should_start(*, task, facts, new, head, now) -> bool` | 触发求值；`new` = 水位之后未求值的事实；`now` = 当前 epoch（时间驱动判断归 harness） |
| `rounds` | `should_continue(*, state) -> bool` | **轮的结束条件**；每次动作后调用，False 即停步循环 |
| `projection` | `build(*, task, facts, new, head, content_dir, step, max_steps, rejected_final, workspaces, revision) -> {system, messages}` | 有界投影；步预算、已提交 revision、授权 Workspace 由 runtime 提供，怎么用归 harness |
| `logic` | `parse(text) -> action` | 解释模型输出（交互格式是 harness 选择） |
| `logic` | `guard(*, state, action) -> str \| None` | **动作执行前的拒绝权**：返回理由即拒绝该动作（落 `sys.action.rejected`，无副作用），用于挡住"原地打转" |
| `logic` | `settle(state) -> [{kind, payload}]` | 步循环结束后的收尾声明（派生事实在此计算） |
| `admission` | `accept(*, kind, payload) -> bool` | 外来事实准入规则 |

动作类型（runtime 执行、harness 解释）：`shell`、`emit`、`final`（**提案**结束本轮）。

- `shell`：`{type:"shell", script, target?}`；`target` = `content`（默认）｜`workspace`｜`workspace:<id>`。runtime 按 `task.json.workspaces` 解析 cwd；未登记/未知目标 → `exit 126` 拒绝且不回退宿主（v5:190）。**这是路由与记账，不是隔离**：真正的沙箱是 X 的职责，尚未接入。
- `emit`：`{type:"emit", kind, payload, base_rev?}`。**`base_rev` = 条件声明**：提供时必须等于轮开始时记录的已提交 revision，否则落 `sys.declaration.rejected` 并拒绝该声明（要求 manifest 声明该 kind）。
- `final`：**只是提案**（2026-09-16 反例修订）。runtime 调用 `rounds.should_continue(state)` 决定是否真的结束；被驳回的最后一句话经 `rejected_final` 回传下一次投影。

**规范观测（P7 最小实现）**：manifest 声明即启用——`sys.context.usage`（每次模型调用前落 `{step, projection_bytes, facts, content_files}`）；`sys.clock`/定时器尚未实现，时间目前经 `should_start(now=)` 提供。

**崩溃与恢复（2026-09-16）**：`ledger/rounds.jsonl` 用 `phase: start|commit|abort` 行标记轮；入口若见 `start` 无 commit 即返回 `recovery_needed`，不续跑；`lore_task recover` 把未提交尾部原字节存入 `session/crashed/`、截断 facts 到该轮 `trigger_seq`、写 `ledger/repairs.jsonl`。真实中断已用该路径恢复（见 FINDINGS）。

## manifest（M1 实际字段）

```json
{"schema":"lore-harness/v1","entry":{"ref":"logic/main.py"},
 "facts":{"kinds":[{"kind":"...","producer":"runtime|harness|external","contract":{"ref":"contracts/x.json"}}],
          "triggers":[{"id":"...","on":["<declared kind>"]}]},
 "roles":{"projection":[{"id":"...","ref":"projection/main.py"}], "...":[]},
 "views":[], "extensions":[]}
```

解析规则：声明优先、默认路径兜底、缺席=关闭；`sys.*` 只能由 runtime 声明；ref 必须存在（M1 校验存在性，digest 只记不算）。

## M1 已知缺口（未验证或未实现）

- **digest 校验只到存在性**：`roles.*.digest` 未与内容比对；manifest 自身 digest 记在 `task.json.harness.digest`。
- **工具域只有 content/**：Workspace 域、双 Shell、沙箱（X）未接。
- **工具协议是 harness 自定的单 JSON 动作**：不是 function calling；未做探测与修订。
- **尚无**：信息项 views/presentation（声明已保留）、多实例角色、`derived/` 重建、崩溃注入、幂等重放、并发/单写者租约、条件受理（base_rev）、Workspace 域。
- **已最小实现**：`sys.context.usage` 规范观测（P7）；跨轮触发（trigger_seq 水位）；`final` 提案 + harness 决定轮结束；archive 无损折叠（archive harness）。
- **与设计的已知差异（待实施修订）**：工具执行目前是**固定 `tool_timeout`（默认 30 s）硬杀**，
  超时塌缩为 `sys.tool.result{exit:124}`，无存活观测、不保证整进程组终止。
  设计目标为**默认到点发 `sys.tool.check`（不自动杀）** + 结果四分类 `ok/failed/timeout/unknown`
  + 资源安全网 `sys.tool.abandoned`。**实现未改**，差异与影响见
  [amendment-task-tool-liveness-2026-09-17.md](amendment-task-tool-liveness-2026-09-17.md)；
  设计出处 [voice-assistant/execution-timeouts.md](voice-assistant/execution-timeouts.md)。
- **证据范围**：单机、单实现者；见 [validation/task_runtime/FINDINGS-2026-09-16.md](../../validation/task_runtime/FINDINGS-2026-09-16.md)。
