# BND 有限模型实现交叉审查

- 审查人：`/root/review_constraints`。我编写过 BND 预注册用例，未实现 BND；本报告审查实现是否兑现冻结契约，不独立批准用例完整性，不替代整体 G1 验收。
- 范围：BND 的 5 个最终模块、`freeze-002.json` 及其 6 个冻结输入、开发失败记录、正式 `g1-001` 的 BND 原始轨迹。
- 结论：在冻结的有限对象与可信 fixture 假设内，**未发现阻断实现验收的问题**。实际效果与控制层报告的关键区分成立，三处故障表示修订保留了真实错误转移。此结论不代表真实 Runtime 的 P02/P03/P04/P05/P08/P12 已通过。
- 方法：逐模块源代码审查，冻结输入和正式实现 SHA 核对，45 个 BND raw 文件逐项 SHA 核对，关键正例/反例的动作前后状态直接核对。没有在本次审查中重跑正式模型；运行结果属于 root 的独立入口。未修改实现、冻结输入、断言或门槛。

## 1. 版本与证据链

`freeze-002.json` 的源提交为 `c8fe8ebf8bcd811efe783a3d4e54ccff6f5674ea`。当前 6 个输入均匹配该冻结文件，BND 用例 SHA256 为 `c6a156b4b779a9c4e2c70c4ca94ca126d9909a4fbfa5cf787b6601257d91d441`，冻结文件自身 SHA256 为 `8ed693e7c0523305668a8295a7622cd586ed4542d61331e43b06e5c41c74430b`。

正式入口的 `simulations/evidence/g1-001/summary.json` SHA256 为 `46c13ed72b29f029364771f287f3b477e2b46750a6691cf1121caaa0c4bfb8ab`；时间为 `2026-09-12T17:54:02.493864+00:00`，命令为 `/path/to/loom/simulations/run_g1.py --suites strategy durability boundaries --batch g1-001`。BND 共 22 条正轨迹、23 条反轨迹，45 个 raw 文件的实际 SHA 均与 summary 的对应条目相同，状态均为 PASS。反轨迹 PASS 表示错误机制被其相关断言拒绝，并不表示错误机制符合契约。整体 53 正 / 54 反的统计不作为本报告跨范围审查结论。

最终源文件均与正式批次 `implementation_sha256` 一致：

| 文件 | SHA256 |
| --- | --- |
| `simulations/boundaries.py` | `f033ed7b2c7d97fcad0eafe549127eee45f938cf055f4cd76fb4374bdec6a247` |
| `simulations/boundary_execution.py` | `81ec20320b260acc4cf07ceb128a6d7072b50c2eb3599ca582fa8f66577b219b` |
| `simulations/boundary_writers.py` | `65fbdb0df62798f9508da179d673ced9869f546f9649d0b06322db8eb18a54f4` |
| `simulations/boundary_versions.py` | `e7a76461cf53af020015ec732945fd8da18e831fff33ed3aed5d4e404de88deb` |
| `simulations/boundary_records.py` | `a6d9479b6bd2a55ac917dc98c73ba41682fa909536b00654a62489c3699522d2` |

## 2. 转移与观察独立性

`boundaries.py:48–75` 只接收初态、机制 variant、`op + args`；操作名采用固定白名单并分发到共享转移。5 个模块没有文件读取、oracle 导入或以 case ID 分派行为；AST 中也没有 `G1-BND-`、`cases-boundaries` 或 `expected` 字面量。这个静态检查只是辅助证据，结论还依据逐模块阅读。

`snapshot()`（`boundaries.py:67–68`）直接深拷贝内部状态，没有按断言补路径、补值或在观察时修复记录。`external_change`（86–94）只能改变声明的外部 fixture 根，不能直接注入 `observations`、计数器或 `effective_writers`。观察标签只用于关联操作输出。对象写入会实际改变 `objects` 的内容和 revision；观察字段从该转移结果生成。

有限模型的事实仍处于同一 Python 进程和字典内：本报告确认逻辑区分，不将其解释为操作系统权限隔离。

## 3. 契约与原始轨迹核对

以下轨迹名均相对于 `simulations/evidence/g1-001/`；`aN` 是原始记录中的动作后状态。

| 契约与实现位置 | 直接证据与判断 |
| --- | --- |
| 双域目标、同位置歧义、身份授权、无 host fallback；`boundary_execution.py:6–29,36–97` | 目标解析依据注册、位置集合、principal grants 与实际 directory identity；正常执行的写集合来自所选 profile。错误 fallback 会实际使用 host profile 并增加 host 执行数；声明 profile 不在正常分支中提升权限。没有以命令文本或 cwd 自动授予另一身份。 |
| 路径别名、检查后重开；`boundary_execution.py:31–47,99–130` | `boundaries--G1-BND-005--correct.json` 最终 `objects.control.value=C0`，别名交换后拒绝，合法 W1 写入 `ok`。`--check_then_reopen_alias.json` 实际将 control 写为 `bad`；`--path_prefix_only.json` 实际改写 control 与 S2。错误不是只在 denied_writes 报告上翻转。 |
| 继承句柄；`boundary_execution.py:132–164` | BND007 正例实际 process handles 仅含 task output 或 runtime report；反例 `--inherit_parent_handles.json` 的父子进程实际获得 control/model-key，使用 control 后实际生成 `registry.task-parent`。管理能力另受 action grant 限制，不能仅从句柄名推导所有操作均许可。 |
| 同 Surface / 共享 Workspace 写者交接；`boundary_writers.py:5–50` | 正常门禁查看实际 `effective_writers`，不只查看 owner 或 Surface 局部 owner。BND008 `--owner_record_as_revocation.json` a2 同时存在 old/new 写者；a3 旧写者实际把 S1 写为 old-before；只有后续明确撤销事实才移除旧写能力。 |
| 取消与父进程退出；`boundary_writers.py:52–78` | 取消只记请求。BND010 `--parent_exit_as_tree_stop.json` a2 父进程 running=false，而 child.running=true 且仍在实际写者集合。a3 错误批准 new 后出现 old-child/new 重叠；a4 子进程真实写入 child-before。父退出推断仅进入 `control.assumed_stopped_processes`，没有伪造子进程死亡或抹除真实写能力。 |
| 人工编辑不能被忽略；`boundary_versions.py:9–27` | BND011 `--ignore_external_edit.json` a2 实际内容为 human/revision=1；a3 保存原有 stale proposal 后，错误提交仍实际写入 agent-from-R0/revision=2；a4 版本捕获也保存这个错误内容。proposal 的存在不掩盖覆盖失败，E01/E02 因真实结果不符而失败。 |
| 多文件输入协调与快照依赖；`boundary_versions.py:29–88` | BND012 正例 materialized 为 T0/B0、T1/B1；反例 r0 实际混合 T0/B1。BND013 正例快照与恢复内容含 tracked-template、untracked-block、artifact-v1；tracked-only 反例实际只保留 T0，missing 从缺失引用计算。当前路径变化不能替换已经保存的内容。 |
| 回退、历史与外部效果；`boundary_versions.py:90–112` | BND014 `--rollback_erases_history.json` a2 的实际 `records.history` 是 `[null, rollback-record]`，原确认内容已丢失；external_effects.op1 仍为 1，历史重播的执行增量为 0。正常转移追加回退记录；反例在原数组真实写 tombstone，snapshot 不补造观察路径。 |
| 事件声明与确认权威；`boundary_records.py:6–49` | BND015 正例 a1 应用 `surface.registered` 只进入 app 事件，registry/runtime 为空；显式有能力且目标合法的 register 后才建立实际 registry 与 runtime 记录。`--event_name_is_authority.json` a1 则已经错误生成实际 registry 与 runtime 记录。因此不是只检查返回的 registration_completed。 |
| 私有输入视图与源记录；`boundary_records.py:70–97` | BND016 正例被修改的视图重建后仍为 original，实际 events 原文未改；`--view_is_authority.json` 实际 events 被改成 forged-confirmation，重建后也读到污染来源。读视图本身不生成确认事实。 |
| Step 固定 Harness；`boundary_versions.py:114–137` | BND018 正例 step1 始终取 H0，step2 使用 H1。latest 反例即使 steps.step1.harness 仍为 H0，实际 phase 值已取 H1/M1/T1/P1；绑定报告与实际使用版本被分别观察。missing-pinned-harness 正例保持 H0 并 blocked，反例擅用可用 H1。 |
| 裁剪投影保留源记录与未决责任；`boundary_records.py:99–168` | BND019 `--trim_deletes_raw.json` a2 实际 raw 被截为 HEAD/TAIL，a3 丢弃 projection 后 a4 仍读到截断原文。BND020 `--trim_drops_unknown.json` a2 实际 saved/pending 被删；a3 retry 使真实 external_effects.op1 从 1 变成 2，随后查询确认这个实际次数。既没有以摘要是否含 unknown 代替责任状态，也没有以重试返回值代替外部效果次数。 |

## 4. 开发失败与故障表示修订

我直接读取了开发失败记录和最终源码，未将开发者 smoke 作为独立验收证据：

1. `boundaries-001-smoke.txt` 保留 BND010 的 `NEGATIVE_NOT_DETECTED`（22/23 负例被检出）。原 mutation 只遍历 parent 方向，未匹配 fixture 的 children 关系。最终源码识别双向有限关系，但对子进程“已停止”的错误推断只写控制层，不改变真实运行/写权限事实；正式 raw 中有旧子写入与新旧重叠的直接证据。
2. `boundaries-002-smoke.json`、`003` 保留 BND011 的 rejected_edits 路径缺失、BND014 清空 history 后必需槽位缺失等结果；缺路径按 INVALID 对待，不计为成功杀死 mutation。`boundaries-004-mutation-revision.md` 明确记录该约束。
3. 最终 BND011 在正常冲突检测点保存真实提议，然后由错误机制绕过提交拒绝；最终 BND014 真实抹去已有历史槽位的内容并留 tombstone。二者都在共享转移里改变事实，没有在 snapshot 中补槽或按 case ID 修补。BND019 则保留实际原始日志截断。修改没有改冻住的 oracle，错误机制本身仍然被真实失败结果反驳。
4. `boundaries-005-smoke.json` 是修订后的开发记录，正式 `g1-001` 的轨迹和最终源码 SHA 才是本次采用的运行证据。旧失败文件仍可追溯。

开发记录 SHA256：

| 文件（相对于 `simulations/development/`） | SHA256 |
| --- | --- |
| `boundaries-001-smoke.txt` | `da0e42d987fdc7add31c83751d52e592249117b1fdfa9a8e7f0596e9be6046b4` |
| `boundaries-002-smoke.json` | `3af9dee78255b38362d357119d61fce70a397e40c297332f3941d519f25e1c90` |
| `boundaries-003-smoke.json` | `d5f63b36b61027293ab25e4f6b2e80d3e2d535c9aa1bec064d116be3ecc561a1` |
| `boundaries-004-mutation-revision.md` | `3e9519288f0d77c367b321b69f693a8ab45b207de0cebc8c89ef6b5feb555645` |
| `boundaries-005-smoke.json` | `cb25eed2501dd5a707dac7df3787a6fb9cb09a880e47639947f05f59d030c475` |

## 5. 结论的适用边界

- `observe_revocation` 中非空 witness 是可信环境注入；模型验证的是“获得真实失权事实之前不交接”。它没有证明真实 OS 中 witness 的真实性、进程树完整性、FD 关闭、云端停止或资源再访问确实被禁止，这些仍需 G2/G3 对独立组件验证。
- `start_process`、`update_registration` 是声明范围内的可信管理/fixture 操作。不能把测试驱动可调用这些 op 的能力当作模型代码、普通调用者或生产 API 获得该能力。
- BND014 的 `domain_versions` 是有限版本选择，未模拟真实多文件回退的事务与落盘；BND013 的独立内容复制也不能证明真实文件系统快照原子性和持久性。BND012 仅保证已经协调的 input_set 内一致读取，不承诺无协调的人类多文件编辑自动构成原子事务。
- Harness 版本可用性、输入 locator/read_grants、原始记录的持久性都由有限 fixture 表示；BND018 的固定选择、BND019 的原文留存和 BND021 的输入字段完整性不能替代真实存储、权限、恢复与模型输入连通性验证。
- 本次没有判定 21 个主用例加扩展足以覆盖所有可能交错、真实路径别名和攻击方式，也没有将模型内通过推广为系统组合后的通过。后续若机制或抽象改变，仍须回溯冻结前提与用例，再按正式独立入口验证。
