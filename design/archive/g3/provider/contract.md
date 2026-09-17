# 可信 provider wire 映射先行合同

范围：S 可信桥内的有限非流式 Chat Completions 映射和 HTTP 原件收集；不是新模型循环或业务策略。S G3 原协议第2步的独立子准备，尚未实现/验证，也不允许据此宣称真实代理工具能力。原用户模型5.6-terra对应已实测代理ID gpt-5.6-terra，底层供应商身份仍未证明。

官方接口依据：[Chat completion](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create) 的 native function tool_calls 原ID/名称/JSON arguments 和 finish_reason，以及 [指定模型](https://developers.openai.com/api/docs/models/gpt-5.6-terra)。官方协议说明不保证第三方代理全部兼容；当前只知原非流式文本批成功。保留原 response 的 model/id/usage/finish_reason，不把截断或错误改成 stop。

有限请求输入来自已验 S 的原 provider intent，可信侧检查 Session/operation/responseEntryId/原 Harness 与 input capability 后才能构造 wire。只接受固定模型、n=1、stream=false、最大completion tokens<=2048、messages有限原Pi文本/assistant toolCall/toolResult以及一个固定shell(target,script) native函数schema。模型和容器不能传URL、Authorization/headers、host path或更大预算。tools定义属于版本化外部Harness；可信侧核获准工具和target，不能从文本代码块执行工具。

响应转换先收HTTP原status、长度、完整body并保存sha256；非200、断流或长度不足不是完整响应。body<=1MiB，严格UTF8 JSON、不重复key/非有限值/过深结构；固定object=chat.completion、一个index0 assistant choice、明确id/model/finish_reason，usage原非负整数保留。缺失或不合格字段显式失败，不制造零usage或替代回复。当前精确model须为代理已解析ID，服务如返回不同模型先留原证据调查，不能默默改白名单。

正常content字符串转Pi text（null可伴tool_calls），每个原function tool call保留稳定id/name与完整解析arguments对象，不从文本提取动作。stop→Pi stop，tool_calls→toolUse，length→length；content_filter/error及未知结束理由遵循下方 strict profile，在保存原 wire 后以 unsupported_finish_reason 拒绝，不返回成功 Pi message。工具个数原样保留（包括双工具），由已冻结Harness单步规则在任何X交付前整体拒绝双工具/length/未知。映射器不执行工具或定final。text含代码fence仍只是一个text块。usage映射按下方PW-R01修訂的固定Pi口径；工具调用样本保留原usage，与本次wire引用关联。

原先行15个固定样本及预审补件在cases.json+fixtures，预期与原件先于映射实现冻结。另真实本地HTTP fixture发回这些原bytes（含服务错误与短body断流），观察请求/响应同一原件和调用数；不读密钥、不连接代理。执行前准备最大1loopback server/2连接、最多32请求（扩大是新增先行反例，尚未执行）、单请求2秒、总45秒/64MiB输入输出上界。模型/工具调用数均0；普通函数字段转换不当作Pi原Session保存证明。

未来真实兼容批仍须满足S原provider-preparation.md第3—4项的实际物理隔离、公开Pi接线与许可闭包后另开：固定3请求（文本、native工具、真实执行反馈后续），每请求<=1024completion tokens、总输入<=8192tokens、60秒/请求和180秒/批，无自动重试。未公布代理计价不伪造金额，记录实际usage/call及官方参考价来源但不等同代理账单。当前不实呼，真实M/X仍依其原独立预算。

## 独立预审PW-R01—03修订

输出是{message,wire:{sha256,size,http_status,response_id,raw_stop_reason,raw_usage},pricing:{status:"UNKNOWN",currency:null,actual_cost:null}}。message严格为Pi AssistantMessage：role=assistant、content原text/toolCall数组、api=lore-proxy-completions、provider=lore-authorized-proxy、model原固定ID、responseId原id、timestamp=原created秒乘1000、rawStopReason原字符串、stopReason明确映射。usage含input/output/cacheRead/cacheWrite/totalTokens及原服务提供时的reasoning子集；input=prompt_tokens-cacheRead-cacheWrite，output含reasoning，不再另加，totalTokens必须等原prompt+completion。cacheRead来自原prompt_tokens_details.cached_tokens，cacheWrite只来自明确cache_write_tokens（固定 Pi/OpenRouter 兼容扩展，不是官方 OpenAI 保证字段，也不声称当前代理支持）；细分缺失是未声明缓存（当前有限profile用0），但原完整usage保留，不能称真实未缓存。任何细分为负/非整数、cacheRead+cacheWrite>prompt或reasoning>completion拒绝。Pi要求cost数值字段，固定全0仅为未计价占位，pricing.UNKNOWN始终同返，不可把0当真实费用。完整结构预期在每个成功fixture中保存。

content_filter与未知finish在保存原wire后拒绝成功（unsupported_finish_reason）；stop含任何native tool、tool_calls却没有完整tool、重复tool ID、非对象args、非空refusal皆invalid_wire；length即使含完整tool也仅归length，不能final/dispatch。本映射没有动作/业务final接口，原case中0 action/final=false限定为映射本身，真实Harness仍按S原例独立核验。

请求函数接受原Pi context(systemPrompt/messages/tools)、明确本次model/max_completion_tokens和可信scope固定的Session/operation/responseEntryId/input/Harness/capability绑定；只构造固定POST /v1/chat/completions的JSON bytes。context最多64messages、系统与消息仅纯文本或Pi text/toolCall/toolResult类型；工具结果保留原toolCallId，并匹配此前尚未反馈的唯一assistant原id/name，不可丢弃、替换或改变顺序。工具schema为本有限profile冻结shell(target,script)，context仅传该固定定义，工具名与definition不静默改写。拒绝额外url/headers等控制字段、错scope绑定或超2048completion预算；拒绝时HTTP实际请求数必须0。n=1/stream=false及模型由受信构造固定。

界限先行：编码后的完整wire请求UTF8<=65536字节（包括模型/messages/tools/n/stream/max_completion_tokens），65messages拒绝；严格JSON容器最大深度32（根容器深度1，字符串中native arguments另独立深度计数）；response原body<=1MiB。请求有恰好65536与65537拒绝样本，响应有native args33层拒绝。request-cases.json保存原Pi输入、独立原wire bytes/或0HTTP拒绝预期；响应原件只扩不改。HTTP fixture分别观测完整已收请求与实际send/short disconnect，样本complete标签不能自证传输。

实施接口与独立 HTTP 验收序列见 api-contract.md / collector-protocol.json。此处两项文字澄清的原文/SHA保存在 history/pre-implementation-001，33样本预期与原件不变。
