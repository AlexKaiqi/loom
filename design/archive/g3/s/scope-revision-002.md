# S 案例责任修订 002

原完整草案保存在 history/cases-001-before-scope-002.json，SHA256 27131950853dd4a30c519838c11eb559a2febba2df6302dc78a1e96ae00bde2a。没有原始要求删除，没有产品通过。

独立职责判断经根确认：原 S-017 后半实际检查 R 保存的外部决定 A，在 S 独立阶段用 fake R 得绿不构成独立证据。修订 S-017 只用真实原 Pi step、X实际释放和新调用的原字节查询，要求不新推理/不重执行。仍保留 V5-B028/V5-B084 来源。

三处追溯义务：
1. S-017：已保存原 step/query/ref 与实际释放，属于 S。
2. R11/R12：R 自身受理决定 A 的完整绑定/内容不变、原子交接，不重算，属于 R。
3. G5 R-S 接缝：同一原要求下“Pi结果已保存；R已接受 A 尚未实施；控制进程/环境崩溃；复用原Pi结果与A，不能执行重新评估的B”。该组合必须在真实独立组件E gate后验证；本修订不提前认领它通过。

S-011 同时把“next_accepts=0”改成可由真实 S 帧观察的“continuation_proposals=0”：S普通最终回答不提出继续；真正无R接受/启动后继属R/G5。避免以不存在Runtime的空日志自证。原provider/tool精确计数和原Session stopReason检查不降级。

S组件测试依赖实际已验 X/F 设施；R/E权限/输入/运输回执使用明确可信fixture，仅反映S收到的合法边界。provider回执缓存是外部固定响应夹具的实际已生成wire字节与原effect/responseEntryId，不模拟R调度、不当真实provider通过。
