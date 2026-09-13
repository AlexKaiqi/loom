# S 失败原件的隔离保留

状态：先行窄契约；未实现产品。来源：S-025 必须拒绝坏 JSONL，保留先前正常 final 累计事实且坏恢复区间新增 final=0；S contract:41 要求保留原件并实际停止后回收；X checkpoint-retention 明确 X 只核原字节、作用域与所有权，不解析 Pi 健康状态。

现 `SnapshotStore.confirm` 和 `_verify` 必经 `session_original`，因此合法普通 tar 内的坏 JSONL 或尚无 accepted binding 原件不能取得正常确认。不能以空 Session、修补坏行、编造 binding、测试 cleanup 或直接写 owner 绕过。新增接口只分离原件保留和正常 Session admission，不新增 X/Pi 状态机。

接口固定：

- `quarantine(request_id, expected_scope, checkpoint_full_ref, reason)` 返回精确 `{quarantine_ref, owner_record_ref, storage_charge_ref}`；`quarantine_ref` 的内部格式沿现 X 普通 snapshot 全引用，绝不返回正常 `snapshot_ref` 槽位。reason 是可信宿主给定的非空 UTF-8 字符串，最多1024字节，记录为何未接纳，不据此声明任何 Pi 内容为真。
- `query_quarantine(request_id)` 是专用只读查询：检查原保存文件及作用域/归档/charge/owner关联，返回相同隔离结果。不得注册、写入、分配新 inode 或更新原件；原 X blob 已合法移交后不存在仍可读 S 原件。
- 正常 `query(request_id)` 必须拒绝隔离记录。正常 `confirm` 对坏/torn/缺 accepted binding 继续拒绝；`empty` 不能隐藏原数据；正常 S session_reference/open/restore 路径不得把 quarantine_ref 变成 healthy Session 或 accepted binding。
- 现 `receipt(receipt_id, old_fullref, retained=隔离结果, sealed=True)` 允许输出原 `sealed_ownership_transfer` 结构。`sealed=False` 必须拒绝；隔离记录不得充当 healthy successor。相同 receipt ID 参数改变仍冲突。

所有原物理保障不变：expected_scope 从可信原 X/Session 登记取得，完整 namespace/surface/session/generation/execution/object/request/CID/exec/volume/freeze/state 一致；读取原 fullref 的真实 SHA/长度；完整 ordinary archive 的成员集合、元数据与现 profile 原限制；保留原 raw bytes 到不同 inode，文件与目录真实 fsync；真实 archive/manifest/owner/charge 均为不可变原件、同 namespace 的可信 registry 单调登记。全局原上限20GiB，单确认控制预留2MiB/16对象，raw<=18874368、logical<=16777216、members<=512 均不豁免。此契约只接合法 ordinary tar；损坏 tar、特殊成员、错scope/hash/缺源或超限不得因‘quarantine’获准。

X 兼容格式不变：普通 record.origin 和 owner.source.kind 仍为 `checkpoint`，绑定原 fullref；不引入 X 不认识的 quarantine origin。owner 仍 `lore-s-original-snapshot-owner/v1`，额外明确 `retention_only=true`、`session_admission="NOT_ADMITTED"`、`quarantine_reason=reason`，`original_session=null`。这些表示未授予正常 Session admission；不伪造原 metadata/JSONL/binding。X 现验证器照常核真实 scope、tar/manifest/hash/独立 inode 与实际 charge；实际停止、read pin、释放intent→unlink→credit仍由 X Retention/Engine 原门槛判定，NoEngine 准备不宣称已停止。

相同 quarantine request ID 完整 expected_scope/fullref/reason 必须一致，成功重交只返回原结果与原 charge，不重复分配；不同请求不得借同路径或硬链接冒充独立原件。损坏、缺失或被替换的保留物/owner/charge 必须拒绝，不能降级为正常或空结果。S 可信入口须只接受有效正常 owner 来建可恢复 Session；当前 X 普通装入接口不检查 Pi 语义，不能声称 X 自动阻止隔离原件健康化。

独立有限验证入口 `validation/s_quarantine_probe.py --batch <fresh>`：复制实际候选 Python 源和既有 artifacts/snapshot_fixtures/registry 模块，使用两个已保存真实 Pi 原件的独立测试副本：一份追加完整非法 JSONL 行；另一份仅取原真实 header 前缀，明确没有 accepted binding。原件不改，合成 X IDs 仅为登记 fixture，0 Engine/模型/网络。

| ID | 可反驳判据 |
| --- | --- |
| SQ01 | 正常 confirm 拒绝 complete-invalid、torn 与无binding三种原件；不产生正常确认或charge |
| SQ02 | 既有正常原件可 confirm，真实 NodeProfile 能核其 sealed receipt，校准无Engine验证环境 |
| SQ03 | complete-invalid 原件 quarantine 后逐字节、成员/manifest、独立inode/实际fsync/原scope与实际charge成立；真实 NodeProfile 接受原 sealed receipt |
| SQ04 | 无accepted binding 原件同样仅取得隔离保留，original_session=null；真实 NodeProfile 核同一原byte receipt |
| SQ05 | 同ID精确重复无新额度/文件，换reason或另完整scope/ref冲突；新ID错scope/hash与缺原源拒绝 |
| SQ06 | 新Python进程 query_quarantine 原文件/registry完全不变且0注册；原Xblob暂不可见仍读同S原件；正常query与正常session_reference拒绝隔离结果 |
| SQ07 | sealed=False拒绝、sealed同ID幂等与变参冲突；NodeProfile对真但另一Session的原record/ref拒绝 |
| SQ08 | 逐次缺/坏owner、坏charge、保留archive缺失或hardlink别名：专用查询和真实NodeProfile都拒绝；恢复测试原件后可复核原结果 |
| SQ09 | raw/logical/member/global预算原边界拒绝，无新增已确认隔离结果或有效owner/charge |

所有原正负判据先于增量实现冻结；旧产品缺 quarantine/query_quarantine 是 MISSING/失败，不能把 AttributeError 当负控通过。NoEngine 成功只支持文件保留及现 X receipt 数据协议，不取代真实 S025 或 X stop/pin/回收证据。
