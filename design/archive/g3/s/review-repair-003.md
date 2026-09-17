# S 独立预审后的局部准备修复

本轮仅修复验收准备，不实现 S/X/F 产品，不裁定 G3/G4。原独立报告 `design/g3/reviews/s-pre-review.md` 结论为 REVISE_BEFORE_G3_PASS；修复作者即该预审者，最终修复裁定必须由根独立复审。

修复前的七份原输入和 SHA 保存在 `history/pre-review-003/manifest.json`；原 index 为 98ddde9b0d6847a3c61d4aaf3733ed7e7a6128632d44839b55687d38006d2152。此前失败批次及原 25 例 / 94 断言没有删除。

| 问题 | 先行修订和真实驱动行为 | 独立判据 |
| --- | --- | --- |
| S-R01 原 accept 已存但受理 ACK 丢失没有明确切点 | 新增 S-026。Pi accept 的原 JSONL 经 X 暂停导出；从原值直接核完整 lore.s.binding，包括显式 null 字段；外部原字节和恢复描述 fsync 文件与目录。在 durable admission ACK 交付前真实 seal/release。下一执行对象清空内存 accepted 状态，重读磁盘恢复描述及原 archive 后同 ID 重交、查询。S result 帧是未完成外部持久化屏障的临时响应，不能算已经交付的受理 ACK。 | 原受理有一个 user / 零 assistant；前后原 SHA 相同；丢失 ACK 零、恢复交付 ACK 一；provider/tool 零；原 namespace 无残留。此接收 fixture 不代替 R-S G5 责任持久化。 |
| S-R02 S-025 把此前正常 final 也要求为零 | 保留累计 accepted_finals，另记录 recovery_finals。恢复开关只标识当前真实调用区间，不清除旧记录。 | 正常前序 final 仍一；坏 Session 恢复新增 final 零、完整性错误一。 |
| S-R03 S-018 标记不来自实际 Shell 输出 | 固定 bootstrap Shell 实际 printf 标记；通过 X 原 result_ref 解析原 stdout 并核字节/摘要，保存独立 bytes 源；工具回复给 Pi 同一原引用及这些原字节。 | 原 stdout 精确等于标记及换行；下一 operation 的 provider 输入必须在原生 toolResult 内容出现它，旧 toolCall 脚本文字不能替代。 |
| S-R04 Engine 清单冒充实际进程 | 新增 physical_witness.py：完整 container/exec/generation 绑定，EngineExec 实际 argv/UID/cap，可信观察器读取原 task/keeper PID namespace；它们相同且区别于宿主。最终按原 namespace 枚举真实 PID。容器/volume 清单另列 remaining_execution_objects。 | 停止后原 namespace PID 数为零且物理对象清单为零；缺原 ID、错 generation、不可检查均不得输出零当通过。 |

同时修复同一冻结/失权边界的驱动错误：中间 checkpoint 明确 resume；最终、故障 checkpoint 保持冻结到 seal。原先无条件 resume 后以旧 receipt seal，可能使外部保存的前缀之后继续变化。校准明确分别执行两条共享分支；pause 本身仍不证明失权。

当前 26 例 / 109 断言。新增两个操作已进入有限操作词表；产品只收到具体请求，不收到用例 ID 或断言。所有正式案例仍 UNVERIFIED。S-017 已保存 step / 原 query 零调用责任保留，R11/R12 与 G5 的 A 已接受后崩溃接缝没有删掉或转成 S 自证。

## 准备证据

- `validation/components/s/evidence/physical-preparation-003` 实际验证新 OS collector 的前后 PID。更严格的 task/keeper/宿主 namespace 比较在协议 amendment 后以 `physical-preparation-004` 复跑：同 namespace 原 keeper+task 两 PID，task UID1000/cap0，task namespace 与 host 不同，停止后为空，2.88 秒。仅固定 Engine 设施，不是 S 行为。
- `repair-calibration-003` 四项、`repair-calibration-004/005` 六项：累计/恢复区间、错误新增 final 被观测、实际固定 Shell stdout、错 generation 拒绝、最终不 resume / 中间 resume。checkpoint 校准使用明确 test receipt 包装真实已保存 Pi bytes，只检驱动分支，不把它当 X/S 实现。误将 `--help` 当 positional batch 的额外六项校准保存在 `evidence/--help`，没有删除或替代失败。
- `oracle-repair-003` 九项原 oracle 错误/缺失校准；原 Pi public/container 机制与旧失败仍分别保留。它们不证明完整新 S-026 行为。
- `live-driver-repair-004` 保存完整 26 例动作计划、collector MISSING exit 2 和 runner 实际 exit 2。缺真实 S 入口与已验 X/F，拒绝产生组件通过。最终元数据词表修订后的发现/缺失检查另见 `live-driver-repair-005`。

## 有限资源与仍待真实验证项

S 准备目标显式绑定 `design/g3/system/contract.md`：单 slot S512 + tool128 + 串行 helper128 MiB、最多三个产品对象，keeper 计入对应 PID 预算；S/tool exporter 共用一份预留 helper。不能挪用 X 独立设施二对象 / 256 MiB 成为 S 组合承诺。新 OS probe 只有 S512 加顺序 helper128、最多同时两个对象；正式 S 完整流程仍需 G4 在共享预算中验证。

原 JSONL 的持久化、同 ID 恢复、原 stdout 接线和边界帧行为必须等实际 S 与已独立通过的 X/F 后由当前 driver 执行。现有 OS 探针、固定 faux / Pi public API 和校准不得冒充这些结果。目标示例仍是未配置示例；真实依赖门槛/共享资源版本缺失或改变时失败关闭。独立审查需同时核真实来源权限、动作与输出，不以 origin 标签自证。
