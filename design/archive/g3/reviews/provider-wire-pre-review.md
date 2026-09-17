# Provider wire 修订预审 002

裁定：**PASS_REVISED_WIRE_SAMPLE_DESIGN_ONLY**。本次只通过先行合同及样本设计的局部复审，尚无 mapper/HTTP/S 或真实模型执行通过。

PW-R01—03 的旧发现和原报告保留在 `provider-wire-pre-review-002/prior-review.*`；根保存的旧合同/15项预期在 `../provider/history/pre-review-001/`。24 响应原件、9 原Pi请求的直接检查结果及输入摘要见 `provider-wire-pre-review-002/input-audit.json`。原15响应字节与上次独立SHA完全一致，无原件替换。

- PW-R01：成功预期均具有完整 Pi message、原 id/model/created/finish、完整 raw usage 与原wire关联。PW16 的 11 prompt/7 completion、4 cache-read/2 cache-write、3 reasoning 对应 Pi input=5/output=7/total=18；reasoning属于output而不另加。必需cost数字0仅占位，同返 pricing.UNKNOWN；PW24拒绝缓存超过prompt。
- PW-R02：PQ02 的原call-feedback-1、参数、`原反馈 雪\n10\n`及消息顺序直接对应原wire。3个正例原件SHA/长度/工具schema/固定model/n/stream/预算匹配。6个拒绝例包括错反馈关联、任意URL、2049预算、错reserved response、65消息及请求超字节。独立实量PQ08为65536字节；只替换成PQ09原输入后编码65537，预期0HTTP。
- PW-R03：content_filter、未知finish、stop+native、重复call ID、非对象args、refusal、33层参数各有具体拒绝原件。原length/代码fence及双工具预期继续保留，mapper的0动作不冒充Harness gate。

比对依据是固定 Pi `types.ts:383–449` 与 `openai-completions.ts:1518–1544`，以及首次审阅已读取的[官方请求文档](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create)与[原工具关联字段](https://developers.openai.com/api/reference/cli/resources/chat/subresources/completions)。官方说明不证明第三方代理兼容、身份或计价。

两条不阻断样本设计的澄清已发根：旧开头content_filter→error措辞应服从新段落的明确拒绝；cache_write_tokens是Pi/OpenRouter兼容扩展，并非官方OpenAI保证字段。未据此变更任何样本或阈值。

本轮没有运行HTTP或mapper，也未调用真实provider。后续独立collector必须从实际socket观察完整/短传输、27次预定HTTP及拒绝时0请求，不能采用complete标签自证；bad/missing/空跑控制仍须实际运行。S原provider准备第1—7步、物理隔离、原Session保存/恢复和M+X系统义务均保持，未借本预审结清。
