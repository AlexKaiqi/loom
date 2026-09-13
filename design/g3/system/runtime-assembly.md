# 实际 Runtime 装配边界

沿 entry-contract.md 与原 M01 可执行入口；只构造现有 R/F/X/S/Provider/E 实例，注册原全引用回调。`assemble(config, credential_provider=None)` 返回原 Runtime，其 `initial_refs` 和 `registrations_spec` 是实际 StartupAssets/F 结果。配置显式携带 runtime、startup_root、startup、provider 与 initial_session_ref，密钥只走函数回调。

装配不得运行 Harness/模型/工具或创建任务容器。Engine 构造允许原能力只读检查；Runtime.open 仅打开固定共享 JetStream，register/start/query 保持原语义。F 授权按 purpose 路由，不能将拒绝的工具安装回退成通用 host 许可。R 仅把匹配 owner/kind 的原 receipt 交给相应 owner。SessionSources 只从当前实际 R 与健康 S 原件解析，不能从任意输入路径构造权威结果。

同步工具回调在已有 S worker 线程，emit 通过 `run_coroutine_threadsafe` 提交给 Runtime.open 捕获的原 event loop；不得创建第二客户端/循环、不得从主 loop 阻塞等待自己。每次等待有原 30 秒设施上界，超时保留未知责任；query 不调用该入口。close 只关闭共享句柄。

先行可执行检查沿 validation/system/m01.py 原 missing 入口，并补 validation/runtime_assembly_probe.py：RA01 实际原件配置装配后 start/query 为零效果；RA02 固定响应实际 R→S→Node/Pi→Provider→普通双域 X/F→emit/E→下一 Step；RA03 主 loop 同步误用与未 open/closed 明确拒绝。RA02 是接线范围，不能替代原两输入三次真实 M01。独立观察直接使用原 R/F/X/Pi/provider/JetStream 数据，任何缺失都不能 PASS。
