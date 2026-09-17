# 任务目录 runtime ↔ harness 接口（M1 实现契约）

状态：**实现中的接口记录**，不是验收结论。对应实现 `lore_task/`（runtime）与 `lore_harness/goal/`（第一个 harness）。设计依据：[task-directory-landing.md](task-directory-landing.md) §4.4–4.7。

## Runtime 负责（机制）

- 基础树：`task.json`、`harness/manifest.json`、`surface/{content,head,facts.jsonl}`、`ledger/`；按需 `session/`、`derived/`。
- 事实流单写者：只有 runtime 追加 `surface/facts.jsonl`（append + fsync）；每条含 `seq/id/kind/source/payload/digest`。
- 触发器水位：`ledger/rounds.jsonl` 的 `trigger_seq` 决定"哪些事实已求值过"，与提交水位 `head.facts_end` 分开——已声明的事件仍能被下一次求值看到。
- Round 执行：求值触发 → 投影 → 模型 → 工具 → 落事实 → 提交；提交顺序见 landing §6。
- `head` 是唯一提交点（原子替换），每次提交含 `revision`（content 树 digest）+ `facts_end` + `round_id` + `ledger_seq`。
- 受理门：`admit()`（Fact Admission，2026-09-17 由 `ingest` 更名）对外来事实做幂等去重与冲突拒绝；未声明的 kind 直接拒绝；`requires_relation` 的 kind 无 sender 直接进入也拒绝。
- **跨任务中继**：`relay()`（2026-09-17 由 `deliver` 更名，墓碑 delivery）把一个任务的事实经**接收方的**受理门送入另一任务；需双方在 host 权威文件登记且路径一致、接收方 wants + 发送方 grants 双向匹配；拒绝记在接收方受理账；副本不继承授权（I8）。
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

动作类型（runtime 执行、harness 解释）：`shell`、`emit`、`final`（**提案**结束本轮）、`recall`（确定性检索，落 `sys.recall.result` 观测；第四类动作，2026-09-17 补记）。

- `shell`：`{type:"shell", script, target?, budget_ms?}`；`target` = `content`（默认）｜`workspace`｜`workspace:<id>`。runtime 按 `task.json.workspaces` 解析 cwd；未登记/未知目标 → `exit 126` 拒绝且不回退宿主（v5:190，语义保持不变）。`budget_ms`（可选，模型动作内声明）是 harness/模型的**策略预算**：到点**整进程组**终止（SIGTERM→宽限→SIGKILL），结果 `outcome:"timeout"`（调用已执行，副作用可能发生）；超过 runtime 上限的声明在执行前被拒并落 `sys.action.rejected`（需声明该 kind）。**这是路由与记账，不是隔离**：真正的沙箱是 X 的职责，尚未接入。
- `emit`：`{type:"emit", kind, payload, base_rev?}`。**`base_rev` = 条件声明**：提供时必须等于轮开始时记录的已提交 revision，否则落 `sys.declaration.rejected` 并拒绝该声明（要求 manifest 声明该 kind）。
- `final`：**只是提案**（2026-09-16 反例修订）。runtime 调用 `rounds.should_continue(state)` 决定是否真的结束；被驳回的最后一句话经 `rejected_final` 回传下一次投影。

**规范观测（P7 最小实现）**：manifest 声明即启用——`sys.context.usage`（每次模型调用前落 `{step, projection_bytes, facts, content_files}`）；工具存活观测（2026-09-17 实施，均按声明启用）：`sys.tool.started`、`sys.tool.check`（默认间隔 10 s、退避 ×2 封顶 60 s，**只观测不杀**）、`sys.tool.abandoned`（资源安全网：结果未知，恢复须先查询不盲重跑）。其余 runtime 产生的观测：`sys.action.rejected`（guard/预算越界拒绝）、`sys.declaration.rejected`（base_rev 冲突）、`sys.recall.result`。`sys.clock`/定时器尚未实现，时间目前经 `should_start(now=)` 提供。

**崩溃与恢复（2026-09-16）**：`ledger/rounds.jsonl` 用 `phase: start|commit|abort` 行标记轮；入口若见 `start` 无 commit 即返回 `recovery_needed`，不续跑；`lore_task recover` 把未提交尾部原字节存入 `session/crashed/`、截断 facts 到该轮 `trigger_seq`、写 `ledger/repairs.jsonl`。真实中断已用该路径恢复（见 FINDINGS）。

## manifest（M1 实际字段）

```json
{"schema":"lore-harness/v1","entry":{"ref":"logic/main.py"},
 "facts":{"kinds":[{"kind":"...","producer":"runtime|harness|external","requires_relation":false,
                    "contract":{"ref":"contracts/x.json","digest":"sha256:..."}}],
          "triggers":[{"id":"...","on":["<declared kind>"]}]},
 "roles":{"projection":[{"id":"...","ref":"projection/main.py","digest":"sha256:..."}], "...":[]},
 "views":[], "extensions":[]}
```

解析规则：声明优先、默认路径兜底（兜底条目不盖章，由 `task.json.harness.digest` 整树覆盖）、缺席=关闭；`sys.*` 只能由 runtime 声明。**digest 严格校验（2026-09-17，落地 R2）**：登记时 `create_task` 对每个声明 ref（角色条目、kind 契约、trigger `when`、view resolver）计算并写入 digest（盖章幂等）；加载时缺失或不匹配即响亮拒绝。

## M1 已知缺口（未验证或未实现）

- **工具域只有 content/**：Workspace 域、双 Shell、沙箱（X）未接。
- **工具协议是 harness 自定的单 JSON 动作**：不是 function calling；未做探测与修订。
- **尚无**：信息项 views/presentation（声明已保留）、`derived/` 重建、崩溃注入、幂等重放、并发/单写者租约、Workspace 域。多实例角色：manifest 校验支持，runtime 尚不按实例选择。
- **已最小实现**：`sys.context.usage` 规范观测（P7）；跨轮触发（trigger_seq 水位）；`final` 提案 + harness 决定轮结束；archive 无损折叠（archive harness）。
- **工具执行已按修订实施（2026-09-17）**：默认是**到点发 `sys.tool.check`（只观测，不杀）**；
  `budget_ms` 是策略判定（到点整进程组 SIGTERM→宽限→SIGKILL，结果 `timeout`）；
  runtime 硬上限是资源安全网（结果 `unknown` + `sys.tool.abandoned`）；
  `sys.tool.result` 增加 `outcome`（权威）与 `side_effects`，`exit` 为兼容镜像。
  离线判据 VO37–VO42（`validation/task_runtime/offline_tool_liveness.py`）与既有套件全部通过；
  **独立复跑未做**，修订状态仍以 amendment 为准。
  记录：[amendment-task-tool-liveness-2026-09-17.md](amendment-task-tool-liveness-2026-09-17.md)；
  设计出处 [voice-assistant/execution-timeouts.md](voice-assistant/execution-timeouts.md)。
- **证据范围**：单机、单实现者；见 [validation/task_runtime/FINDINGS-2026-09-16.md](../../validation/task_runtime/FINDINGS-2026-09-16.md)。

## 修订记录（2026-09-17 重构）

1. **术语对齐（glossary v3.2）**：`ingest` → `admit`（Fact Admission）；`deliver` → `relay`
   （墓碑 delivery→Event+Fact Admission）；CLI 子命令 `admit`/`relay` 同步更名，
   `validation/task_runtime` 调用点同步。历史命令名出现在 2026-09-16 及更早的验收记录中，按原样保留。
2. **R2 digest 严格化**：登记时盖章（`stamp_manifest_digests`），加载时缺失/不匹配即拒。
   此前的"只记不算"缺口关闭；旧行为记录于上方历史版本（git 历史 66 行版）。
3. **工具存活**：`tool_timeout`（30 s 硬杀）移除。修订 D1–D4 的 M1 取舍：
   D1 参数改为 `--tool-check-interval`（默认 10 s）/`--tool-budget`（默认无，ms）/`--tool-hard-cap`
   （默认 600 s，runtime 保留，动作声明越界被拒并留痕）；
   D2 check 落**面事实**（`sys.tool.check`，声明启用；退避 ×2 封顶 60 s，数值待测 U26）；
   D3 硬上限目前是 runtime 级每调用上限（配置来源 X budget maxima vs `task.json.policy` 仍待裁决 U27）；
   D4 与租约的对齐未处理（M1 无租约机制）。
4. **U28（`sys.tool.finished` 是否与 result 合并）**：M1 取合并——`sys.tool.result` 增加
   `outcome/side_effects/duration_ms/call_id`，不另立 finished 事实；契约十份收敛为规范一份
   （此前 4 变体漂移，4 份缺 runtime 实际会写的 `target/cwd`）。
5. **U30（check 落库粒度）**：暂落面事实；频率影响待测量后复议。
6. `task.json.landing{boundary,last_round}` 死字段移除（创建后从未更新）；
   `provider.py` 文档中的 "ARC plan" 更正为 "Volcengine Ark plan"（env 变量名 `ARC_PLAN_API_KEY` 不变）。
