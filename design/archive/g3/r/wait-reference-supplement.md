# R 原引用关联与等待屏障增量合同 001

状态：ACCEPTED_PREREGISTERED_FOR_REPAIR。由独立RW01/02与RA01/03/04/05/07/08/09原失败驱动，根已确认范围；此合同与用例先于对应产品修复。原45与失败资产保留，不构成组件通过。

## 已知上下文的authority核验

expected是供原所有者查询的上下文，不要求opaque ref内出现这些字段。缺失/真但关联不符一律reference_invalid；不能先持久受理后再补查。

- acquire(base)传{resource_id}，来自原调用与真实登记。F仍负责当前版本/内容；不增加R文件历史。
- 普通prepare_install(staged)传{resource_id,execution_id,base_ref}，来自已核原holder与调用；实际stage root/dev/ino继续由R直接校验。不强迫原API没有的generation或未来install request_id。恢复安装保留原RF02完整expected。
- stop_ref在accept_decision与首次apply均传{parent_id,source_ref,harness_ref}，来自原parent/已保存结果/原已接受策略。authority核原S/Harness可终结记录，R不解释业务成功。原已applied重交只回原决定，不重新执行。

首次save_result仍按原合同由可信调用方先查owner-operation关系；R保完整不可变ref及后续source精确相等，不臆造统一owner schema。Harness/condition/environment/wait_ref是外部明确选择的原件，其已接受完整版本仍不可变。

## 等待使用原R holder/release事实

accept_decision的wait保持原model body不改。R在同一个接受事务额外保存`decisions.wait_barriers_json`，query_decision返回`wait_barriers`，等待时是按(resource_id,execution_id)稳定排序的[{resource_id,execution_id,base_ref}]；非wait可为null。它是控制依赖，不是另一套执行历史。

资源集合来自原parent.payload.resource_id（如有）、原input_binding.execution_targets中的resource_id（如有）、wait.target。wait.target仅原R可解析的登记ID/绝对位置；execution_targets使用已冻结的含resource_id对象，不猜opaque对象含义。每项按原principal/namespace明确resolve/write并去重，未登记not_found、无权denied、不可解析结构invalid。保存的是解析后的登记身份，不能用字符串前缀授权。

受理时集合内每个当前holder的完整{resource_id,execution_id,base_ref}成为固定屏障。body.release_refs逐个只能匹配该集合中当前holder的完整tuple，或其中某个已持久release的原tuple；必须核原stop引用及完整expected。真实但wrong resource/execution/base、集合外或没有原release关联的stop皆reference_invalid。不得从提交stop内容反推期望。

release事务在删除holder前将完整原tuple保存到`releases.holder_json`，与既有stop+published完整binding同事务。历史legacy缺holder_json或accepted wait缺已确定barriers不能视为验证完成或自动空集合；可明确拒绝旧schema或保持待核对，原已确认数据不得重建为空。

首次apply按原已接受barriers查原release ledger；须原tuple、原stop+published一致，重新authority核对应tuple。任何尚无合法release的屏障报busy，原parent保留decide、decision.applied=0、不得创建wait。这取代原未定义接续的pending_wait行为：完成既有release后重试同一个apply即可，body/decision ID/barriers不变。缺件或损坏reference_invalid，亦不结清。

所有屏障已释放后才写waiting。accept后出现的另一个新holder不能替换原屏障，也不阻止原等待依据已完成release成立；新writer仍受acquire独占规则。没有holder且没有release_refs是合法空屏障等待，前提仍是目标已授权登记；仅证明R闭世界无所需未决holder，OS/Session实际归零仍须X/S与G5。无holder但显式提供stop仍须匹配原release ledger，不能拿任意真stop抵充。

完整同身份重交、重启、新worker只复用原body和barriers。不得恢复时从当前新holder重新构建集合，亦不得静默替换已接受策略。

## 先行验证及历史

RW01—04和RA11原轨迹/原失败保留；新authority适配仅增强正夹具上下文，不弱化断言。新增RW05—10核matching未release busy、释放后原决定重试/新进程、空集合、原release后新holder、未登记及无权target。原R14仅增加实际acquire/release setup，其匹配/去重/条件断言不变。base/stop/staged夹具语义写入独立owner-context原文件，不在a1自身引用中嵌入source=a1形成循环。
