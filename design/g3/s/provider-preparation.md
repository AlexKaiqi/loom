# S provider 最小增量准备协议

状态：PREREGISTERED_PREPARATION_PLAN；未调用真实 provider，不认证真实模型或 API 兼容。U009 的模型标识 5.6-terra 保留，不能偷偷改成另一个模型。

1. 可信 Python 侧先核对用户已授权代理的实际 API 类型、官方协议/允许接口、返回模型身份与必要许可/服务使用条件；不猜测它一定支持 Responses 或 Chat Completions，不因类似 OpenAI 字段便声称兼容。Python 标准库 HTTP/TLS 路线优先，无新第三方 provider SDK；若依赖变化，调用前补来源/固定版本/原 LICENSE 或 NOTICE/hash。当前 Node/Pi/TSX 固定许可见 research/reuse/pi-license-boundary.json；Python/image 动态库见 linux-tools-licenses.json，容器准备批另留实际 ldd。
2. 不读 key 的准备：可信本地 HTTP fixture 记录原 request bytes，给完整文本、一个完整 native tool、双 tool、length/partial、错误/断流五类原协议数据。Pi custom provider callback 与所选协议映射单独冻结，保留原 wire bytes/hash、model/stop/usage/tool id/name/完整 arguments，验证 normalized Pi assistant 来源一致；普通文本代码块不能成为 native tool。这是协议 fixture，不是真模型。
3. 授权实呼范围由根与用户现有资源授权解析；密钥仅可信 Python 进程持有，日志/环境/argv/输出不得包含 key；不传给 Node/Pi/Harness。S 在 X network-none 容器仅有 scoped bridge。Python 核对当前 Session/operation/reserved responseEntryId、模型白名单、输入版本、最大调用数/输出预算和目标 capability，拒绝任意 URL、headers、hostpath、请求类型或重放跨任务 token。白名单/预算是可信受理机制，不能由模型正文修改。
4. 真实兼容性批在上述 fixture 与物理分离成立后新开：固定非敏感微型输入，一次完整普通文本、一次合法单 native tool 请求及执行反馈后的独立后续 operation。读取真实传输原始结束标志及完整 response，确认指定模型身份（服务不暴露可证明身份则如实记未确认）、原 Pi assistant/tool/result 引用和 actual provider 次数。调用数量/耗时/费用上限在批次前按用户资源定下，不用结果反定合格线。
5. 完整输出判据预定：合法普通回答须 complete terminal、无未决 native tool、非 length/error/aborted、符合固定 Harness 解析；工具须完整 JSON 参数/明确工具和 target/script，动作交付前原 Pi assistant entry 已保存并 checkpoint。失败/截断文本保存，0 action、0 accepted final。代理未暴露足以验证完整性的字段为接口缺口，不能拿固定响应绿灯覆盖。
6. provider wire 完成但 Pi 未保存窗口保留 narrow delivery receipt，绑定原 responseEntryId；固定 Pi 恢复 public API 不消费该缓存为原成功，因此 paused_reconciliation_required。未取得完整回复是 paused_unknown。都不新推理/重发不明效果。已保存 Pi 结果新进程直接原查询，provider/tool 新调用为 0。
7. 真实模型闭环属于 M 系统验证（V5-B077/U009），还需真实模板/blocks、两个工作位置、报告/notes 与事件往返。协议兼容通过不能当系统闭环或策略价值通过。后续 M+X 的策略对比及规模测量不以本准备结束。

待根确认的是代理实际协议与可信 HTTP transport 接线，不向用户新增例行审批；现阶段未取得物理分离及接口证据前，不把凭据交给候选。
