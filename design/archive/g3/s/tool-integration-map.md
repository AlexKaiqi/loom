# 普通工具与 ExecutionPlan 的最小产品接线映射

状态：ANALYZED；只读接口审查与接线设计，不是 S 或系统通过。仅新增本文，未改当前 full27 批次的源码、合同或用例，未运行 Docker。依据 [v5 §4.1、§5.2—5.4、§6.1/6.5](../../../harness-runtime-revised-v5.md)、[S 宿主接线](host-adaptation.md)和 [Runtime 入口](../system/entry-contract.md)。

## 1. 当前可复用部分与真实缺口

[execution_plans.py](../../../validation/components/s/execution_plans.py) 已用真实 F 完整目录构造 Node 四挂载与 schema1 普通工具请求；[tool_results.py](../../../validation/components/s/tool_results.py) 已执行 X → 原 checkpoint → 实际 seal → F import/materialize → 原 stdout 回注。它的 `Peer.allow`、`fixture-manifest.json`、随机 fixture 身份、固定 revision=1 和 `execution_outputs` 都是验收装配，不是产品授权或状态来源。

当前 tool_results 在另一目录物化输出版本，没有调用 `R.acquire / prepare_install / confirm_install / release` 或 `F.install`。因此它证明封存与读取，不能证明 Surface/Workspace 的权威目录已更新。生产最小差异是替换测试引用解析，并接上既有安装链；不新增工具 DSL、结果账本或调度器。

## 2. 一个可信原件解析接缝

产品装配只需注入一个宿主侧函数 `resolve_reference(full_ref, purpose, expected)`：传入原所有者的完整引用与可信调用范围，返回核实后的原记录/原件描述；现有 R/F 三参数 checker 用它核验后返回严格 True。它是既有引用校验的薄实现，不是公开给模型的新 API，也不接受任意 owner/path 路由。

- `full_ref` 必须来自已受理的 R 请求、R 输入关联、原 F/X/S 回执；模型 `{target,script}` 与 Pi/provider 的 `{id,sha256}` 都不能充当它。可信 Runtime 确定 principal、namespace、invocation、Session、资源/版本/代与允许操作，不能从待验 ref 自取 expected。
- 解析入口的所有者集合和权威根由宿主配置固定。每次核原范围、原完整身份、实际文件/目录身份及摘要；已知路径不是授权。F 文件读取调用真实 `FileStore.read_reference`，X 查询原记录/原 blob，E 读取其原固定输入目录，S 读取原快照/Pi JSONL。未知、缺件、错范围、变化均传播原错误，不生成替代 ref。
- 不落第二份“最新引用表”。必要传输描述符可以作为真实 F 普通文件封存，内含全部原来源；它的 compact ref 仅是该原件的传输投影。动态 S owner 原件仍沿已固定的可信根单调登记，不能用可变 latest 路径替代完整原引用。

| 调用需要 | 唯一依据与保留内容 |
| --- | --- |
| 输入与可用目标 | `R.query_input(principal,invocation_id)` 的原 selector + 唯一 E input_ref；保留 namespace/source/start_sequence/filters/page_size/surface_ref/previous_session_ref/execution_targets。H/end/next/正文由 E 原 manifest 决定；不重新抓取 H，不把 F compact ref 写回替代 E input_ref。 |
| Harness、capability、Session | 本次已接受的完整 refs、完整 session_scope/operation/source_result；当前 capability/Harness 不能从旧 input 文档偷取。S snapshot envelope 保留 full snapshot、原 archive、owner record 与 storage charge；初态复用真实 `SnapshotStore.empty`。 |
| F 版本与位置 | 完整 `resource_id/domain/git_ref/archive_sha256/manifest_sha256/profile`，原 archive/manifest、实际 materialization 路径及 dev/ino；历史文件 ref 再带原 member path/hash，仍需当前访问授权。 |
| X 工具效果 | 原请求、binding、execution_id/object_generation/request_digest、原 stdout/stderr/checkpoint/stop refs；原 bytes 与完整作用域不因传输投影丢失。 |
| 已发布结果 | 原 R 安装意图/确认、原 F query/install 记录和完整新版本、实际当前位置及新 R revision；不使用测试 execution_outputs 索引。 |

输入装配可复用现路径：从原 E/F 对应原件组成普通目录，加入 keyless `node-config.json` 后真实 F capture；记录原来源与生成配置。Node 只见 `/input/surface`、events、feedback、originals 和独立 `/workspace`；依赖/Harness 保持固定已验内容。配置依赖当前 compact H/input/cap，但 full refs 始终由可信宿主持有。S 节点、Runtime 都不导入 validation。

## 3. 普通工具请求与责任边界

| 模型目标 | X 原 domain | F 原 domain | 输入与写入边界 |
| --- | --- | --- | --- |
| runtime | runtime | surface | 原登记 Surface 的完整 F 版本；普通 Shell 在私有目录编辑，安装才更新权威目录。 |
| workspace | task | workspace | 原登记 Workspace 的完整 F 版本；不删减文件以迎合容量。 |

内部 X `session` 只承载 S 的普通快照，不是模型第三个 Shell target。模型不能给 mount、principal、authority、state_root、generation、预算或任意宿主路径。原 script 字节、`cwd='.'`、普通 `/bin/sh -c` 保持，scope 来自原已授权 resource_id/实际 revision/dev/ino。工具 profile 维持 CPU .25、128 MiB 内存、6 MiB 卷等原预算；小输入显式128 inode，完整大输入显式1024，不能静默修改收到的请求或提高总预算。

稳定效果身份沿原 Pi `pi.op.state` 中的 pending `invocationId/resultEntryId`、完整 Session/operation 绑定与已定义 effect_id，关联 R 原 execution 请求和 X 原 execution_id。产品不能沿用 fixture 随机 UUID 或收到重试便另起身份。pending 先保存到真实 Session 原件再发效果；R 持久受理/mark_dispatched 后才调用 X。失 ACK 查询原 R/X/Pi 身份，不能重发脚本或再调用模型解释同一未知结果。

R 的 facility `request_digest` 针对完整受理请求（含可信 principal），X 的 `request_digest` 针对原 X request；两者不是同一个散列域。R receipt 投影保留原 X 完整回执与两个原关联，positive/明确 negative/unknown 按原 R 契约区分，不向原 X JSON 追加这些 R 字段。`confirm_delivery` 只确认设施原回执已保存，不等于目录发布或业务完成。

## 4. 沿用现成安装链，明确字段投影

1. 从 R 原登记与输入目标解析完整 base、实际根和 revision；原执行受理后用 `R.acquire(resource_id,execution_id,base_ref)` 保留该资源责任。claim lease 不是写权限；另一资源可继续。
2. 用可信 plan/grant 执行 X 原请求，取得原退出、输出与 checkpoint。按原冻结代 `X.seal`，核原实际 namespace 停止与写能力消失；仅 request_stop 或 candidate 声明不够。未知继续查原件。
3. 用实际已登记权威根作为 F binding，将同一打开的原 checkpoint bytes 交 `F.import_archive`；source context 绑定原 base/resource/execution/object/freeze generation、archive path/size/hash 和 stop ref。再 `F.materialize` 到独立 staging。二者不冒充 publish，原 base 的实际集合仍由安装窗口复核。
4. 先 `R.prepare_install(...,expected_revision,base_ref,staged_ref)` 持久受理原安装意图，保持原 holder；再 `F.install(original_install_id,intent,stopped_ref)`。普通人工编辑造成实际 base/根变化必须拒绝；不能只比 R revision 或两遍 hash。
5. 失 ACK 用 `F.query_install(original_install_id)` 对原两根实际布局和内容恢复；不再 exchange。只有实际 installed_pending_confirmation 对应原意图时，调用 `R.confirm_install` 更新同一资源身份/revision。unknown/conflicting/not_installed 不伪造成功。
6. 用原 stop 与真正 published ref 调用 `R.release`；将原安装事实、新 revision、完整 F 版本和可访问位置交给外部 Harness 构造下一原请求。Runtime 不事后改写已接受 body 的 resource_revision/input refs。

| 实际接口差异 | 最小无损接法 |
| --- | --- |
| F `materialize` 返回 `{path,root:{dev,ino},version_ref}`；R staged.root 要 `{path,dev,ino}` | 由原返回生成 staging 引用投影，保留完整原返回/版本及 execution/base/stop 关联；R checker 回读实际 F 原件与目录，不能由投影自证。 |
| X `artifacts.stopped` 是原 proof 的 `{path,sha256,size}`；F install 要顶层 execution_id/generation | 保留原 blob ref，附原 X binding 的 execution_id 与 `generation=object_generation` 投影；checker 从原 proof/query 核全部 exec/资源/base/代/物理停止关联。不能改写原 proof JSON 或只验附加字段相等。 |
| F query 的 current_root/retired_root 是 dev/ino，R confirm 要 current/retired 含 path | path 来自原 F intent，结合原 query 生成扁平引用；保留 original_intent/version_ref/stopped_ref/request_id 与原状态。原 F query 不返回 `confirmed`，不得凭空升级。 |
| R 普通 confirm_install 的 expected.version_ref 实际是完整原 staged_ref | checker 应对原 staging 投影整体及其中 F version_ref，交叉核 F 原 query 与 R 原意图；不要误把此 expected 当成裸 F Git version_ref，也不要丢 staging/stop 关联。 |

字段投影只在受信组件适配层进行，所有事实仍回到原 R/F/X 记录。它们不是新的安装状态机。上述完整发布链目前尚未在生产组合中执行，属于明确待接线项。

## 5. 单 slot 归还、保留字节与结果回注

`X.release` 与 `R.release` 释放不同责任。schema1 普通工具实际移除原 CID/volume 后可归还共享 tool role；原 stdout、checkpoint、记录仍可查询，并由 `retained_spool={path,root:{dev,ino},allocated_bytes,inodes}` 按原实际块/目录/仍打开 deleted FD 计费。新工具准入计入全部旧债务及 slot 控制开销；不能重命名或只返 role 就退还字节。schema2 Node 仍必须完成原 S ownership transfer 且无 read pin 才可释放，不能套用普通工具例外。

这一窄差异已有[独立原件与失败修复记录](../../g4/x-tool-slot-release-001/independent-review.json)：两次同 slot 普通工具实际执行、旧 bytes/inode/债务保留及 schema2 分支拒绝；它不代替整个 X/S 组合验收。完整大目录的 1024 inode 接线复用[原四场景独立记录](../../g4/x-tool-inodes-independent-001/review.json)，不截取 S027 workspace。

回注仍复用 [callbacks.mts](../../../lore_session/node/callbacks.mts) 的原 `tool.reply`：result_ref 指原 X 执行回执，stdout 为实际原 stdout 的 bytes/hash/base64；不从脚本推算、不把改动文件串接成 stdout。明确执行/发布关联未成立时先核对或暂停。工具退出/发布事实及位置可作为独立可信反馈交 Harness；它们不能被塞入原 X JSON 冒充 X 自有字段。Pi 原 JSONL 保存返回值，S 原 operation_result_ref 保存对应原快照关联；R.save_result 直接保留该原 S ref。Harness 读取原 invocation/selector/发布事实后给完整 R 决定 body，Runtime 不把兼容的 final/continue 标记翻译成第二种决定，也不让 Shell exit0等于业务成功。

最小产品职责可分两处：`lore_session` 内 plan 构造只装配既有 X request/config；普通 tool 接线只做原调用/回注。可信 owner resolver 与 R/F 发布协作放 Runtime 装配处并注入，不让 S 导入 R 内部表或复制账本。沿原 S018/S026/S027、R 安装用例、X016 和 M01 验证实际关联即可；不建立新验收平台。Runtime Shell 的 emit→可信 E.submit 仍需原事件薄 transport 接线，本文不声称普通工具文件链已经覆盖事件往返。

## 6. 本次只读源身份

下列是审查时字节身份；现有 full27 批次结果未被本文预测或授予通过。原文件与当前证据按原批次保留。

| 文件 | SHA-256 |
| --- | --- |
| `validation/components/s/execution_plans.py` | `ade5d0b365712509d94534d0f1b1bd86cd34abe827ecfef175ab6a1c08dd2a5b` |
| `validation/components/s/tool_results.py` | `65b285a1b243b3fe18e9875c6cc32d40b703bf99d881c0659bef1ca56d2bb627` |
| `lore_files/store.py` | `c37134892743c96ff44ef4bd1679cfb439df82c878011a062b2e9256ad24583c` |
| `lore_files/history.py` | `a4e10a62a4a47329223c05347d0ec61e86ba0b636dcd9af2409945e838f4e636` |
| `lore_files/install.py` | `2dd82e6e481d82efb27bedce89a1bafb88b2c4e5fe51d2981ebb1f5ce43c009e` |
| `lore_control/facilities.py` | `4bc1774017192ad1f90bb4edd32981497e297fe5ae241584b45a712967ed8701` |
| `lore_control/installations.py` | `0d0e79f29b65a5c96e9583f0283312edb18913289b093ab0d5ee179a710bd081` |
| `lore_control/holders.py` | `c2f06f09c2529d79780cedbe3af4059c055150c00fe1f6a0d0fa55b7718f2557` |
| `lore_execution/slots.py` | `6265a996d94d7f206338ce8f30881950c769f7d35e786099a274a4558e37bc9e` |
| `lore_session/node/callbacks.mts` | `82e60af5af5537538c7a11a35c0aada0b7fcb4f29a16ce6e71dce906b5ba66eb` |
