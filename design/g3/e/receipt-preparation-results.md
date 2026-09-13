# ER01/ER02 当前准备证据

ER01 已在契约与先行可执行验证口修正：R 的原完整 request_digest 包装与对应用 facility_ref 分开。E03/E05/E07 正式用例读取真实 ControlStore query 的包装，并用只读 SQL 原请求、独立 NATS 原消息/同PUB负回执核验；负查询另启动新 E worker。没有将请求正文复制进R。

最新实际命令为 research/.venvs/runtime-research/bin/python validation/components/e/run_contract.py missing-components-007，子进程原退出码2，stdout/stderr见 validation/components/e/evidence/receipt-commands-007。9个必须准备测试通过；内嵌真实NATS/SQLite原请求夹具的29检查通过，完整ID集合必须匹配先行协议，坏/缺/错范围证据不能通过。正式15个E用例仍全为MISSING/ERROR、0skip，未实现组件没有性质通过。

负回执关键原始证据：missing-components-007/receipt-authority-controls/wire-observations.jsonl 将实际原PUB与对应inbox的原PubAck绑定；negative-fresh-process-original-PUB.json 是无旧proxy对象的新进程验收结果；negative-wrong-original-PUB-bytes.json、negative-no-observer-evidence.json 等保留拒绝证据。positive-original-facility.json 及 reference-checks.jsonl 保留另一独立NATS查询进程的原bytes/hash/subject/header核对。explicit-request-fixture.sql 明确是仅供authority测试的SQLite夹具，不能冒充真实R受理或E运行。

ER02 原004/005批有最多2连接文字与短时3连接的偏差；006实际准备失败，原因是client.close后NATS连接尚未消失。原输出/源码均保留，当前007在每个新probe前最多2秒等待实际connz基线，最大2连接未放宽，保存所有观测；全局40秒边界不变。准备的局部绿色不追溯更改旧批合规状态。

当前只请求独立G3准备审查。没有E/R组件通过，没有真实模型调用，没有总G3/G4自批；G5父invocation与完整系统交接仍须独立验证。
