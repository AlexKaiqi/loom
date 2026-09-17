# S G3 独立预审：需要修订后再审

裁定：当前 D01—D05 准备不能整体通过。此审查基于 preparation-index.json SHA98ddde9b0d6847a3c61d4aaf3733ed7e7a6128632d44839b55687d38006d2152；154 项绑定逐项核hash一致。Pi实际HEAD为71dca871bc80b6bc97be37f0ca3189399d651fff。审查者未参与原S契约/用例/driver编写，未用origin字符串认证物理事实，也没有运行/批准S产品。

## 必须修复的四点

1. **S-R01：缺独立受理ACK丢失切点，D01/D02/D03阻断。** contract.md:43明确accept原记录已写、外部ACK丢；S-003却先正常完成drive，再重交。collector.py:115–134正常接收result、导出、seal/release，没有“实际原accept+完整binding已被外部保存，但durable admission ACK未交付”的故障动作。S001、S002、S015/16不能组合代替该窗口。最小新增独立case：持久保存原Pi JSONL/binding→在外部确认交付前截断→保存接收方ACK计数0及原引用→真实停止并新执行对象从该外部字节恢复→相同ID/完整内容重交与query；原user/op.meta/state关联不增加、原hash不变、provider/tool均0。错误机制为丢ACK后再次裸accept/覆盖binding。不能只延期到G5；G5再组合真实R受理责任。

2. **S-R02：S025累计final计数与正确前序行为矛盾，D02阻断。** collector_actions.py:52先drive complete-answer；collector.py:124会记accepted_finals=1。随后坏Session查询，S025却断言同一累计journal=0。正确实现同样失败。最小修订为保留原final的独立前序事实，并独立计算坏Session恢复区间新增final=0，禁止清空原历史伪装通过。

3. **S-R03：S018正式真实工具没有产生必需marker，D02/D04阻断。** collector.py:45–58的工具脚本只把runtime-write/workspace-write写文件，没有stdout产生ORIGINAL_TOOL_RESULT_雪。该marker只存在probe-public.mts:29直接返回的局部工具fixture。正式collector_actions.py:30–33的真实X bootstrap不能借旧faux工具回执当来源。最小修订让bootstrap真实普通工具stdout写指定marker，独立读X原stdout保存其hash/bytes，再确认当前operation provider输入的原Pi native toolResult包含它；不能从旧toolCall脚本/提示含marker或F wrapper造值判通过。

4. **S-R04：资源对象inventory被命名成PID namespace证据，D02/D04阻断。** live_ports.py:95–108只查container/volume是否仍在列表；collector_actions.py:16–18把其结果记live_namespace_processes。实际对象存在/删除不是该字段声称的原namespace进程观测。最小补实际执行开始时核完整container/exec ID并从真实PID取得namespace，停止后独立枚举原namespace。固定任务UID/keeper UID分别观察，保留原始命令；未知/缺失不是0。对象清理inventory可继续作另一项事实，且关联已验X的原exec/generation停止证据。

## 已有准备价值与适用范围

D01职责分离、原Session唯一语义记录、完整绑定与版本、双向限权provider/tool桥、Pi completed不等于业务final的方向可保留。固定Lane.getResult（runtime/lane.ts:271）与accept(:480)是不同入口；generation.ts:132–171先存assistant.effect_pending；recovery.ts:43–83把孤立pending原frames归为interrupted/error，并不消费wire缓存为成功。这与当前有据暂停边界一致，不能扩成自动恢复任意provider回执。

D02已有真实driver主体，缺X/F正式gate时MISSING非零，而不是空bundle通过。原JSONL reader直接解析v4记录、seq/parent/value/list及hash，未共享Pi reducer。它读到的受理/结果事实仍须由外部已保存实际文件证明。S017范围修订合理：继续保留真实saved-step、释放后原记录相等、query零新调用；R11/R12和G5另验已存S+已受理决定A→崩溃→不重算B。

D03已有坏/缺source/hash/空跑等校准，不代表25正式case所有bad机制已实测。D04 public-preparation-003和container-preparation-002的实际原Session/进程/只读挂载及Node加载有效；它们明确是有限fixture，没有实provider、X工具全链、权限/ACK/持久性通过结论。旧retry配置和绝对路径加载失败保留，不能删除。D05保留原准备上限；正式S组合需要补完整有限资源预约，不能套单X实验的2对象/256MiB。

## 共同接口需收束

S活跃Session等待X工具时，可能同时存在S进程容器、工具容器和导出helper；Node准备profile为512MiB，工具/导出各128MiB的既有样本对应最多3对象/768MiB的可讨论上界。实际选择由共同G3资源记录固定，包含CPU/pids/tmpfs/output/时长及helper预留，不能丢掉S活跃资源或因无法导出而临时扩权。

S测试peer与X具体字节字段（data_b64/data_base64、volume命名、静态argv/profile与完整request）必须有明确薄适配映射并绑定已验gate；不能因方法同名就宣称已经接线。真实provider协议映射仍按provider-preparation.md由可信控制侧准备，faux不认证真实代理API。

本报告冻结旧输入。根随后授权审查者只修上述有来源的S局部准备资产；修复者将不自批自己的修改，最终由根独立复审。
