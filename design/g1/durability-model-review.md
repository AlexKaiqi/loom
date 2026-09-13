# DUR 模型独立交叉审查

当前状态：DUR-R01（DR01）已完成独立修复复核并闭合，见文末。下文保留修复前发现、复现与原证据；裁定仅限冻结 G1 有限模型范围。

审查者：acceptance_evidence。审查对象为 DUR 实现与原始运行证据；本人编写过原 DUR 用例、没有实现 DUR 模型。因此本报告可独立检查实现是否符合原契约，但不把本人用例的覆盖完整性批准为无遗漏。

修复前发现 DUR-R01：完整决定关联元组的冲突检查遗漏源结果和 Harness 版本。当时它阻塞这一顶层契约的完整通过；须先独立冻结补充用例，再修复模型和重验。既有 g1-001 中 28 条 DUR 正向与 28 条负对照的已执行结论仍只对应旧冻结轨迹，不能覆盖新发现的两个输入。

## DUR-R01：同身份关联变化被静默当作原请求

- 原始依据：[顶层契约第 64、66 行](top-level-contracts.md)明确稳定决定身份与输入、策略版本、阶段关联，并拒绝同身份不同决定内容；原冻结用例的 action_semantics.accept_decision 明确接受决定内容、源结果、版本及执行身份。
- 直接源码：[durability_requests.py 第 92–102 行](../../simulations/durability_requests.py)对已有决定仅比较 payload 和 execution_id，随后直接 return；source_result 与 harness_version 没有参与冲突判断。
- 最小复现分别独立初始化：先接受 d1/continue:step2/op2/R1/h1v1，再完整重交一次，最后仅将 source_result 改成 R2 或仅将 harness_version 改成 h1v2。两次改变后的 conflict_reported 均为 false。原接受记录和责任仍在，所以这是静默忽略关联冲突，不是原记录已被覆盖。
- 旧 DUR-028 仅改变 payload 与 execution_id，能够检测恢复时错误分支和换身份，无法检测本缺口。不能以旧断言全部成立代替完整关联语义。
- 已预注册 [追加用例](cases-durability-supplement.json)：DUR-S001、DUR-S002 分离初始化，先验证完整元组重交合法，再单独改变关联字段；检查显式冲突、原完整元组、原责任的单次启动和旧效果保持。通用负对照 ignore_decision_association_conflict 忽略关联字段比较。补充未冻结时不授权修复，更不报告新范围通过。

## 原冻结轨迹的直接复核

读取了 5 个 DUR 模块、cases-durability.json 的所有动作/判据/观察规则、freeze-001、顶层契约，以及 g1-001 中全部 56 个 DUR 原始文件。没有把 summary 的 PASS 或实现者 smoke 当作唯一依据。本次对原始输出做独立解析，未重跑原正式批次；下面的最小复现是缺陷诊断，不是补充用例的正式验收。

对 268 个原始快照，从 _evidence 内的接收端记录、物理内容与定位/授权、责任记录、实际效果/调用/交付列表、资源实体重新核算 14 个观察字段，共 3752 次比较，没有发现不一致。包括确认/可解析集合、待处理与可恢复责任、各类计数、资源数量及父子进程生存值。该核算不把 recovery_status、execution_status、completion_claim 或 saved_result 的自述自动认作事实。

| 核查点 | 直接来源和实际观察 | 可支持的结论 |
| --- | --- | --- |
| 丢确认与重交 | DUR-003/a2、a4 的 receiver_requests 仍有 r1/A/accepted，caller_view 是 unknown；a5 接收端逻辑身份仍只有一个。requests.py:19–29、53–74 将接收端事实与客户端认知分开。 | 原受理事实不会被丢回执或重启删除；同身份同 payload 重交复用。 |
| 结果到继续交接 | DUR-007/a1 的 physical_records 有 R1，责任从 step1:resolve_result 先接到 step1:decide；a4 仍有 R1 和未结责任；a5 交给 step2:running，启动一次。execution.py:48–61 与 requests.py:83–90 先建立新依据再退休旧责任。 | 普通结果保存不会自动销账；该既定策略的恢复可继续。 |
| 原结果不可猜造 | DUR-006/invent_unsaved_result/a3 报 saved_result=R1，但 confirmations={}、physical_records=[]，E1 确实失败。DUR-009/sandbox_only_confirmed_content/a3 保留 6 项确认历史，却没有物理记录，可解析集合为空且恢复失败。 | 负对照可以暴露报告与实际内容不一致，确认历史不替代内容可取回。 |
| 未知效果 | DUR-010 查询事实按 op1 保存 found_completed/R1，恢复后物理保存 R1，效果仍 1 次；DUR-012/a2 保留 op1:resolve 并暂停，a3 由 old_inflight 的环境动作产生唯一效果。execution.py:80–114 不从非终局 not-found 推导安全重试。 | 本声明查询假设下，确认结果与未知暂停分开；未因查询缺项重做旧操作。 |
| 等待前/中/后事件 | DUR-013/014/015 分别登记前、扫描登记间隙、登记后保存事件；原始交付关系引用同一 e1、指定目标和 data1。events.py:56–93 用权威事件/起点匹配而非只读扫描或通知。 | 三种已冻结顺序在公平有限驱动下交付。 |
| 通知丢失与重启 | DUR-017/a4 保留 w1:wait；a5 建立 e1→s2:step1 和处理责任。notification_only_worklist 反例有权威 e1 和等待责任，却没有交付，相关 3 个判据失败。 | 可用独立负对照拒绝仅靠通知维持工作表。 |
| 等待资源与确认先后 | DUR-022/a2 的环境资源实体 agent/connection/sandbox 都为空而 shared_service 保留；DUR-023/a1 尚无保存确认时原任务资源仍在，a5 才释放。preserve_task_waiter 反例仍有 agent:0 与 connection:0，资源断言失败。 | 资源观察来自有限环境实体；不是 declare_waiting 的字符串。 |
| 取消与真实停止 | DUR-024/a1 取消请求已记，但 observed_child_alive=true、execution_status=running；a2 子进程仍可产生效果；执行器确认后才结束。cancel_request_means_stopped 反例报告 finished 时子进程仍活着。 | 取消请求与停止确认分开；不能抹去已经发生的效果。 |
| 非恒定决定 | DUR-028/a1 的 accepted_decisions 保存 A/op2/R1/h1v1；a3 候选已变 stop/op3；a5 实际 step_launches 仍为 op2，a6 拒绝不同 payload/op。错误重算反例原接受记录仍是 A，但实际没有启动 op2，反而保存 final:R1，E3/E4 失败。 | 旧轨迹确实拒绝把重新求值得到的 B 代替已接受 A；完整关联冲突仍受 DUR-R01 限制。 |

源代码检查发现五个模型模块仅导入 copy 和经审查的同族模块；没有 open/read/load、eval/exec、网络/子进程入口，也未发现按用例 ID 或 expected 分支。dispatch 接收 op 与 args，cut 只写入注释记录。固定 step2、w1 和策略标签是这个已声明有限域的表示，不是一般 Runtime 接口或任意输入保证。

## 真实能力与审查限制

1. _evidence 的分层是同一 Python 模型内部的事实/报告区分，不是独立 OS 权限域或真实目标系统。save_result、query_external、confirm_required_state_saved、executor_confirms_stop 及 executor_confirms=True 都是预声明 fixture 事实；本批不证明它们在实际存储、网络或执行器中真实成立。
2. 崩溃发生在已列的抽象动作边界；多条 Python 写操作内部没有进程级中断探索。交接代码顺序可以审查，但跨存储的写入、fsync、回复丢失与重启必须在 G3/G4 的真实依赖中验证。
3. 公平调度是固定的最多 8 次启用转移驱动，并按有限顺序处理接受决定、反馈、启动和等待。原始轨迹支持声明的事件顺序，不证明任意并发交错、任意多个任务或无限时长活性。
4. 内容以预置、不透明且独立确定的标签表示，读取授权以 fixture 位表示；模型的内容可取回不证明真实字节、版本真实性或生产读权限。
5. DUR-007/027 允许固定 fixture 策略；DUR-028 只验证已接受分支不能被变化候选覆盖。未接受回调的重求值合法性、任意普通代码副作用、序列化规范化以及关联元组的完整比较不能从旧轨迹推出。DUR-R01 需要在 G1 当前阶段修复，不能只转记后续债务。
6. 审查者与实现者共享可写工作区；文件哈希用于确定审查版本，不构成防篡改隔离。本人是原用例作者，覆盖无遗漏仍须由其他独立角色核查。

## 最小复现

工作目录：/path/to/loom。实际 Linux 进程为 python3 -B -c，脚本如下；没有修改模型或冻结文件。它基于原 observer_defaults 构造两个合法独立内容事实，检查当前未修复实现。退出码为 0 表示诊断脚本正常结束，实际观测的两个 conflict=false 才是缺陷证据。

```python
import copy,json
from pathlib import Path
from simulations.durability import DurabilityModel
defaults=json.loads(Path('design/g1/cases-durability.json').read_text())['observer_defaults']
observations=[]
for field,value in [('source_result','R2'),('harness_version','h1v2')]:
 initial=copy.deepcopy(defaults)
 initial.update(saved_result='R1',confirmed_refs=['R1','R2'],resolvable_refs=['R1','R2'],
                pending_responsibility=['step1:decide'])
 model=DurabilityModel(initial)
 accepted=dict(decision='d1',payload='continue:step2',execution_id='op2',
               source_result='R1',harness_version='h1v1')
 model.apply('accept_decision',accepted)
 model.apply('accept_decision',accepted)
 same=model.snapshot()
 changed={**accepted,field:value}
 model.apply('accept_decision',changed)
 after=model.snapshot()
 observations.append({
  'changed_field':field,'changed_value':value,
  'same_tuple_conflict_reported':same['conflict_reported'],
  'changed_tuple_conflict_reported':after['conflict_reported'],
  'accepted_decision_fact':after['_evidence']['accepted_decisions']['d1'],
  'receiver_decision_history':after['_evidence']['decision_history'],
  'pending_responsibility':after['pending_responsibility']})
print(json.dumps(observations,ensure_ascii=False,indent=2))
```

原始 stdout：

```json
[
  {
    "changed_field": "source_result",
    "changed_value": "R2",
    "same_tuple_conflict_reported": false,
    "changed_tuple_conflict_reported": false,
    "accepted_decision_fact": {
      "phase": "accepted",
      "payload": "continue:step2",
      "execution_id": "op2",
      "source_result": "R1",
      "harness_version": "h1v1"
    },
    "receiver_decision_history": [
      {
        "event": "accepted",
        "identity": "d1",
        "record": {
          "phase": "accepted",
          "payload": "continue:step2",
          "execution_id": "op2",
          "source_result": "R1",
          "harness_version": "h1v1"
        }
      }
    ],
    "pending_responsibility": [
      "decision:d1:apply"
    ]
  },
  {
    "changed_field": "harness_version",
    "changed_value": "h1v2",
    "same_tuple_conflict_reported": false,
    "changed_tuple_conflict_reported": false,
    "accepted_decision_fact": {
      "phase": "accepted",
      "payload": "continue:step2",
      "execution_id": "op2",
      "source_result": "R1",
      "harness_version": "h1v1"
    },
    "receiver_decision_history": [
      {
        "event": "accepted",
        "identity": "d1",
        "record": {
          "phase": "accepted",
          "payload": "continue:step2",
          "execution_id": "op2",
          "source_result": "R1",
          "harness_version": "h1v1"
        }
      }
    ],
    "pending_responsibility": [
      "decision:d1:apply"
    ]
  }
]
```

## 被审文件与原始证据版本

下列哈希在写报告时重新计算。五个模型文件与 g1-001/summary.json 中 implementation_sha256 完全一致；原冻结 DUR 文件与 freeze-001 中 fcd8f28d… 完全一致。补充文件单独列出，不混入旧批次。

| 文件 | SHA-256 |
| --- | --- |
| design/g1/cases-durability.json | fcd8f28d3e9eb245cef55f5716a404e458fff0d9ec3f5f7c75906e2490f3f861 |
| design/g1/cases-durability-supplement.json | b09e071a2adc9faeafc34deb94d7708f14ef582354cc7dc58eeda2f2c4b0f26a |
| design/g1/top-level-contracts.md | 5644cd02f5d6625690ba8ff9e90e7e4085606eba44eb532eb4c2de34314adeb4 |
| design/g1/freeze-001.json | cdaa1ce39f246aa750105af7dcaf3f853b82be73073493c4c4cc7acb06b30115 |
| simulations/evidence/g1-001/summary.json | 46c13ed72b29f029364771f287f3b477e2b46750a6691cf1121caaa0c4bfb8ab |
| simulations/durability.py | 8ae1511d606f88a0a171b59c365ce3d27bca963981ca854281f40a036488847e |
| simulations/durability_events.py | d7c73b14877fd22882df42e3cec2da31aa8906c0670826c93f0d343054c3915a |
| simulations/durability_execution.py | 170689a14798b7d96154daaf546f0e784a3a7bcd0f6b718e51b2d006edec4b3c |
| simulations/durability_facts.py | 090df189ea16cd23af50cbc5f140846487aa14f717ae8aef18986ad2f1afce17 |
| simulations/durability_requests.py | d622824c2bac3a7e91afc65c07b04ca31b79e8eaaca2d3d377acfcaf031884d7 |
| simulations/evidence/g1-001/durability--DUR-001--bytes_implies_completion.json | af09872cf40896cbc1fbfba04bc3e6e25389ad8218fa1fcca73499e1b8eaf807 |
| simulations/evidence/g1-001/durability--DUR-001--correct.json | 1e14fdbb5d5c25c66950341507b975eb39639a578370f812fd6320fee914ec9a |
| simulations/evidence/g1-001/durability--DUR-002--acceptance_starts_model.json | 842dc689e2b9abff6b41eb9503c6756bb2f76aaa43b3c90c0f17b879702c6e78 |
| simulations/evidence/g1-001/durability--DUR-002--correct.json | f9019ae9edad41235e5125d36a6c7da123ae22a5baa225e30d490ad36053d92e |
| simulations/evidence/g1-001/durability--DUR-003--correct.json | edd1c8790a8e9a47cbcfbf4fa917299ee187f141053b48e85a140ccdf51cb2d9 |
| simulations/evidence/g1-001/durability--DUR-003--lose_request_identity_on_restart.json | ffc54275c09457b95135a40cab964903363426a8fcd5faf075acf853c16ab10a |
| simulations/evidence/g1-001/durability--DUR-004--correct.json | 443dff95888f3a1341f8cce219d943d3c1d7c275bc3921dd48b1ca48a80a2f12 |
| simulations/evidence/g1-001/durability--DUR-004--overwrite_conflicting_request.json | 644e30f72408c9636d2519491dd6cce5afc0ef58e8ef68b42c562b6ec14926a6 |
| simulations/evidence/g1-001/durability--DUR-005--correct.json | 860fce65716e49b35cfad2682f562c3c8dbe6692664d831e078e01406d5280ee |
| simulations/evidence/g1-001/durability--DUR-005--query_causes_side_effects.json | d23a74b83bf84fd8b8d8c5f457263ea3b8270f75f09fed583359b37660767fda |
| simulations/evidence/g1-001/durability--DUR-006--correct.json | 96a30b31ffa920843d1032384fa2114909687b246b22882e5d779605e5537570 |
| simulations/evidence/g1-001/durability--DUR-006--invent_unsaved_result.json | 8017ca53af94954af19196970f2b5f0ecfeaa50b66fcced0c10561ed34247b65 |
| simulations/evidence/g1-001/durability--DUR-007--correct.json | bbcfe70db4a3aaa931ac411a44be65c62584a51ed09ad5773a7b2dea6fe2c8da |
| simulations/evidence/g1-001/durability--DUR-007--drop_responsibility_after_result.json | 0cd51172de27213f5aabb47d4cceed8f89cdadc457abf816a271e68be1c90b29 |
| simulations/evidence/g1-001/durability--DUR-008--correct.json | 366d5f25e5c54e7a44ae465d5e508a2f34a607c4b96976cba988d13a73cf4286 |
| simulations/evidence/g1-001/durability--DUR-008--volatile_next_step_acceptance.json | 9f9156dda169c3230ee8f55cd67392df884646a6a010912b6dcdbe6d7f05016a |
| simulations/evidence/g1-001/durability--DUR-009--correct.json | a6a7fc56cb6879e72135a06948b9403509e6d32b52f3421f74d04704fe4f9f95 |
| simulations/evidence/g1-001/durability--DUR-009--sandbox_only_confirmed_content.json | 688b6da3ec731efd56e14de3f3650d876a820404baad198df49c34ac540cecf8 |
| simulations/evidence/g1-001/durability--DUR-010--correct.json | a5758a19ca52cf17f8b66ee0d11031d7614f0d0229e1c01aa1fd830a8779f4e2 |
| simulations/evidence/g1-001/durability--DUR-010--retry_unknown_before_query.json | 57fc654eb0b9a16ca3177be00ea78803e22522a6f9e0370c38faae14c8269c25 |
| simulations/evidence/g1-001/durability--DUR-011--correct.json | 393958503eb0d08b7aee47590cbe70a735222dacb0b63adfa9f8acae912f2cac |
| simulations/evidence/g1-001/durability--DUR-011--discard_unknown_operation_on_query_failure.json | 760560d94c6c529e32d2194f880c549ba4c1866ef15c21890b00a64d4d60b7bd |
| simulations/evidence/g1-001/durability--DUR-012--correct.json | b6920e6ac5d641ecce30d5cb7b492e47428dfa48a732df341529c0517a5b7e31 |
| simulations/evidence/g1-001/durability--DUR-012--retry_on_nonfinal_not_found.json | 9b336cdb732113d02cf3ce39d6f49cbc3b6ede8ef18b7730a667a83f4d41bb4c |
| simulations/evidence/g1-001/durability--DUR-013--correct.json | 6811aa0d62230aff435fd14a2ed2dcbc86b467349fb4260b497654346c9fc222 |
| simulations/evidence/g1-001/durability--DUR-013--ignore_preexisting_events.json | ad213395cd43b8869cbf34afd4ace63ea16045a34996f062d23b1b70dd6bf21b |
| simulations/evidence/g1-001/durability--DUR-014--correct.json | 16e9c535a6b913afc2c27b6a05b94bdafc2fda63efe3b0b1f7a9d3ea9da7400e |
| simulations/evidence/g1-001/durability--DUR-014--scan_subscribe_gap.json | 26378ee91b056be3c126bb1180608419ecd8057a41b9d6d52e3c63529d6049af |
| simulations/evidence/g1-001/durability--DUR-015--correct.json | a0959a317da5cfcac3dd16d389af0449b9316107079df9cadc622493114ce02f |
| simulations/evidence/g1-001/durability--DUR-015--ignore_future_events.json | b11b5dfbf6b4aefd76dfe2d538c3ed44cf15e13e6d24e21fa129214a12d213fc |
| simulations/evidence/g1-001/durability--DUR-016--correct.json | e9e9c27955084f3a56b9348b8fdd85a9e8f65108d2fa50ec3e161628a467f8e2 |
| simulations/evidence/g1-001/durability--DUR-016--ignore_wait_origin.json | f3f786a3659412002b984712e19d6a94fb81b3ea421a06251bf5fb02dc3105dd |
| simulations/evidence/g1-001/durability--DUR-017--correct.json | 975e5165830274ce521a5a52bd13935b16ea124b04f78c9a87b1499f162a4405 |
| simulations/evidence/g1-001/durability--DUR-017--notification_only_worklist.json | 0a9c8b4d1b65c2b6c206a8e193523f9cd731fa167baa51e9063b71c4a605867f |
| simulations/evidence/g1-001/durability--DUR-018--correct.json | 433ce785b621b02f095df9af506b7a8b20453628184f3f36e9aae1548883392f |
| simulations/evidence/g1-001/durability--DUR-018--read_view_marks_processed.json | a478e453e2827342e2c38867eda9a30befb2f7d35882430986b6faadc4345d3a |
| simulations/evidence/g1-001/durability--DUR-019--correct.json | 59bc4961ca7c41177728f9f9d13501489ff2c16532a9184d220672352fbf39fb |
| simulations/evidence/g1-001/durability--DUR-019--notify_creates_new_business_step.json | 4f068a9755607c553cd29ac462e478d7eaae9e98710b07ae8d2e8fd34aa184fd |
| simulations/evidence/g1-001/durability--DUR-020--correct.json | f248fe8c8311561aa6388ad4da8219a7a2fe74c2fd61761fe5f8c4a63f535b68 |
| simulations/evidence/g1-001/durability--DUR-020--expire_promised_record.json | cd3a62efcf44ac6d41d03f26936c0cfb0933f161cb7efea877a275dd37880460 |
| simulations/evidence/g1-001/durability--DUR-021--archive_leaves_stale_reference.json | c15a3025739f5e32726a856baa9e87ef3d375f10b4ad6bdb5681f537adebd495 |
| simulations/evidence/g1-001/durability--DUR-021--correct.json | bb74242ecc9271ab913ac0bf329d2975d1eb7082312919648e9fb62daedfdd67 |
| simulations/evidence/g1-001/durability--DUR-022--correct.json | 330203230f08f92a5e3650eaed677790fcf2c14ab47fccb7d086a4f00a5afa21 |
| simulations/evidence/g1-001/durability--DUR-022--preserve_task_waiter.json | a9801067bf879fe8d0e631cd4c26bff4a971b3398dffad0087a706800cda31d9 |
| simulations/evidence/g1-001/durability--DUR-023--correct.json | 15ab3067279f69c5eaca7d466fffd1ac0cc39cde2ba5c4a0d49e9421dcd34e70 |
| simulations/evidence/g1-001/durability--DUR-023--release_before_durable_wait.json | 0cc7e152a01db5cc59bd76624a765c5357be1bdfb51dc7e05de7b532b3f1867c |
| simulations/evidence/g1-001/durability--DUR-024--cancel_request_means_stopped.json | 7d8c2090b24e371da89980c247f034a32fc88087abbef485e451599bbbececf2 |
| simulations/evidence/g1-001/durability--DUR-024--correct.json | 992100f906acdea9763cb0b3528da1e9e011ad38d1dfaaf394da94c3eca47646 |
| simulations/evidence/g1-001/durability--DUR-025--correct.json | 124f5adb65b6864c92e0a67d666c86cda4ca7e180d35300d4e8d392f21f53fea |
| simulations/evidence/g1-001/durability--DUR-025--replay_executes_event_payload.json | d8668f566f625a1851368ee60289288217a84cb0fbfab9b89183ca7f16236ae6 |
| simulations/evidence/g1-001/durability--DUR-026--correct.json | dcdfa447427723e11e0c9eaa42aa12b4219c20cfd5c61aa2b44493b1b54d53e5 |
| simulations/evidence/g1-001/durability--DUR-026--missing_history_means_success.json | 836fe2c9fb0fea0a1ba4f90ddb39dd3f7e9fae0fa30a6dccc6222fad3361bf24 |
| simulations/evidence/g1-001/durability--DUR-027--correct.json | 76464a3d5704c7ed9e66fc9df990b7cc9c69f7c05f10a521b4743a102e883e16 |
| simulations/evidence/g1-001/durability--DUR-027--result_implies_automatic_continue.json | a032261348983b6cfedf004b8f059f54e8cce5682e3d851b9d578d1260a8afcf |
| simulations/evidence/g1-001/durability--DUR-028--correct.json | 758cc2825e719e3d7748a3cffa08e1ed3640ef7401807dc8e6bf51c86dcbc084 |
| simulations/evidence/g1-001/durability--DUR-028--recompute_accepted_decision.json | 1cca673a1a2d0bbb5b9081c4a23d8e88ec9c1f66250c4793ca99c11aa06d5ca9 |

## DUR-R01 / DR01 修复闭合

结论：CLOSED，限本次独立冻结的两个关联冲突输入及受影响原轨迹。补充预注册由其他独立角色审查并生成 freeze-004；本报告不自批本人用例覆盖完整性，也不批准真实 Runtime 性质。

直接检查了命令 git diff e77c162 -- simulations/durability.py simulations/durability_requests.py 的输出：模型仅新增通用错误机制，以及已接受决定重交时对 payload、execution_id、source_result、harness_version 的四字段比较。正常分支任何字段变化均报告冲突并返回，完整相同元组复用原记录；没有改写原决定、建立第二责任或从预期复制结果。负对照仅将比较范围退回原两个字段。

修复前正式批次 [g1-supplement-before-repair-001](../../simulations/evidence/g1-supplement-before-repair-001/summary.json) 保留：两正例 E3/a3 实际 false、预期 true；当时未实现的新变异属于 INVALID，未计为成功拒绝。

直接打开 g1-002 的全部四个补充原始文件：两正例各 32 次比较均成立，a2 完整元组重交 conflict=false，a3 单字段变化 conflict=true。a3 与 a6 的 accepted_decisions 均保留 continue:step2/op2/R1/h1v1；a6 的实际 step_launches 只有一个 op2，仍有 step2:running 责任，全过程原效果数量都是 1。两个通用负对照各仅在 E3/a3 产生 false != true，因此新判据确实能拒绝原错误机制。

另逐文件比较 g1-001 与 g1-002 的 56 份原 DUR 原始轨迹：trace 和 checks 内容全部相同，均保留原批次裁定，没有因修复改变旧预期或观察结果。五个当前 DUR 模块哈希与 g1-002 的 implementation_sha256 一致。

正式批次 [g1-002 summary](../../simulations/evidence/g1-002/summary.json) 记录全套 55 正向、56 负向；本次闭合直接审阅其中 DUR 及补充范围，不把其它家族汇总作为本人的审查结论。summary SHA-256 为 b0ada3e68698732f92739a013d1aeb94df70e91ab04b169d1a9d5fae685e0f02。前述真实依赖、抽象动作边界、公平有限驱动与共享工作区限制仍然适用。
