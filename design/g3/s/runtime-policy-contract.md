# 外部 Runtime Harness：原 R 决定与待确认 Session locator

已获根确认，产品修改仍遵守当前live窗口。只新增harnesses/runtime，委托已验minimal.create的lane/prompt/hooks/afterDrive。单次decide调用原minimal.decide，再在外部策略内部构造原R body；minimal源与全部原用例不改，宿主不重新解释final/continue。

## 固定接口

策略导出 `decideControl(boundary, original, binding, source, runtime_context)`，供create返回的单次decide复用及纯策略验收。保留原boundary_kind、proposal.final/continue、source_result_ref、compact harness_ref/input_ref；新增 `proposal.control={parent_id,harness_ref:<原R完整ref>,body}`。decision_id对完整binding/source/control摘要，后继id对原parent/source/完整payload摘要；不覆盖可变同身份决定。

runtime_context是可信plan写入只读普通config的 `{invocation:{id,principal,namespace,kind,payload},node_binding,input:{selector,range},execution_id,continuation_session_ref}`。invocation只取R原语义，不含phase/token/lease/result；node_binding保留本次已核compact对应；input取原R.query_input和E manifest，不重抓H。

tool.reply可多一个publication_ref，直接保留FilePublication.publish完整原返回 `{R_intent,F_query,installation_ref,registration,release}`。Node只另存toolResult.details.publication_ref；原X result_ref/stdout/native content不改。ToolOwner仅在实际R/F安装确认/释放后返回；宿主提交前重新核原记录，不把这个JSON自身当权威。

## 逻辑locator和接受边界

`{owner:'S',kind:'confirmation',confirmation_request_id:'s-'+sha256(canonical([execution_id,'s-service-final'])),session_scope:<完整四字段>}`由可信plan预分配；它不是snapshot/grant。成功终态cp固定s-service-final，沿现SessionRun确认ID公式，与callback数无关。该execution_id对应本次drive，accept/query各保留自身原身份，不换ID重写已存body。

原confirm前可保存提议，但不得据locator构造新grant/计划或受理/实施R决定。可信提交前和apply前必须SnapshotStore.query+resolve_original，以原parent/source/binding检查原scope/execution/operation、原prefix/result、实际保存boundary.control/body和full↔compact对应。缺失、Q、错source/body拒绝，不回退latest/empty/重新推理。R当前successors只结构检查，不能声称reference_checker自动执行上述检查；此调用点由根负责。

## 原successor/stop选择

仅原minimal完整工具反馈分支构造一个successor：复制原R payload，input_ref=None，source_result_ref=本次原source，session_ref及input_binding.previous_session_ref=locator。namespace/Harness/capability/source/filters/page_size不变。start_sequence严格用旧manifest.range.next_sequence；E分页未遍历完时它是end+1，不是high_water+1，不能跳过旧余量或工具后新emit。

原publication.registration和F_query.version_ref只更新同resource_id的execution_targets；Surface发布才同时更新payload.resource_revision/input_binding.surface_ref，Workspace发布不动Surface。其他目标完整保留。原release/installation/execution关联不匹配、无publication不能据stdout猜新版本。

完整final的body为 `{stop_ref:{owner:'S',kind:'runtime-policy-stop',confirmation_ref:<locator>,operation_id,source_result_ref:source}}`。stop_ref不含decision_id避免自引用；存在/有效性来自后续真实确认的完整answer/boundary。当前M wrapper不产生wait；无合法proposal保持原blocked边界，不造stop；后续外部等待策略原范围未删。

## 有限先行入口

`python3 -B validation/runtime_policy/run.py --batch NAME` → 实际module.decideControl，缺候选MISSING/0。六组：Surface更新；Workspace只更本域；原answer；无合法proposal；错误context/缺publication/错scope精确拒绝；相同输入确定且输入不变、同父/source不同publication改变完整决定身份。纯策略fixture复用原S018/S003数据，并显式派生输入上下文；不声称新R/F发布、原S受理或物理执行。原件/候选/driver摘要与失败保留。

固定终态cp已由根原21+4 locator查询检查；提交前真实owner/body校验和Node publication透传仍是独立必要接缝，六组不替代它们。当前live期间只写wrapper草稿与先行用例；Node callback补丁单独保留，待窗口关闭。原S27/M01/G5/G6判据不变。

HP06同组还实际调用runtime.create→原minimal.create（Pi设施为显式stub，不drive），核原lane/hooks委托与真实minimal.decide输出包装一致；不只检导出的纯映射函数。
