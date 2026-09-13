# E 验收准备：实际入口已准备，组件仍缺失

正式入口为 research/.venvs/runtime-research/bin/python validation/components/e/run_contract.py <新批次名>。它固定运行8个 oracle/实际文件/runner控制，再恰好15个真实 EventService case；缺SUT、缺G4 R、错误、超时、零项、缺项或skip都非零。没有理想 E 替身。LORE_EVENT_MODULE/lore.events、LORE_CONTROL_MODULE/lore.control；LORE_R_GATE 的固定字段见 design/g3/e/interface.md。真实R到位仅是依赖门槛，不替代E验收。

- native-preparation-001：FAIL，NATS配置中换行被错误转义；原配置、stderr、source和EP01原因保留。
- native-preparation-002：11项设施准备观察通过；修复前后仍不算E通过，绑定的旧源码已按原hash保留在其source目录。
- native-preparation-003：按先行 amendment-002 运行12项。真实丢PubAck→客户端超时、独立直连读取原seq/字节、服务器SIGKILL后恢复；真实容量负回执精确关联原PUB，不把无关NotFound误认发布回执。所有自有NATS进程已回收。
- missing-components-003：总入口实际完成8个准备控制，15主项全为MISSING/ERROR，0 skip、实际进程退出2。该状态是未实现，不是组件通过。
- preparation-commands-00N/commands.json 保留实际命令、退出码和stdout/stderr，防止外层shell退出码遮蔽。

support.py 是实际NATS启动/有限字节代理/独立原消息观察，fixture.py 加载真实R/E、使用真实SQLite与独立reference authority；worker.py执行真实SUT子进程并在真实切点等待SIGKILL；test_events.py/input_cases.py冻结实际动作与独立字节预期。后者通过真实文件fd观察os.fsync，不信任complete标签。固定输入具体字节格式、R21选择绑定及REJECTED/UNKNOWN区别均在interface.md。

本轮只进行了设施和验收器准备；15正式E场景需要真实E、已通过R及实现源码独立复核才可运行完成。当前不能推断R/E组合、真实wait调度、Surface挂载权限、F/S版本真实性、模型调用、掉电持久性或高并发能力。E14仅验证按原事件起点扫描，不运行条件策略；E15只核实际NATS连接/consumer，整系统等待资源归零另验。真实来源/目标fixture文件不冒充F/S已验资产。

独立复核可先运行 preparation.py <全新批次>（真实设施，约1秒，固定40秒上界），再run_contract.py <全新批次>；须直接检查raw消息、wire audit、lifecycle及缺组件输出，不能把准备检查数量当产品验收结果。

ER01 修复：receipt-binding.md 是 R20 完整包装契约，receipt_authority.py 独立读 SQL + 原设施。run_contract.py 现在强制9个准备测试（新增真实NATS的29项receipt authority/连接边界检查），再运行15个真实E用例；故障或缺组件始终非零。receipt_preparation.py 可单独运行新的批名，SQLite rows 明确仅是原请求夹具，不冒充ControlStore。旧21输入保留history/before-receipt-wrapper-004；旧NATS准备不是E-R接缝通过。

当前修订后的实际入口记录：evidence/missing-components-007/result.json。9个准备测试通过，其中receipt-authority-controls的29项实际设施/错误关联/连接边界检查通过；15个真实E用例仍MISSING/ERROR、零skip、原子进程退出2。ER02保留004/005停止条件偏差与006实际失败，不追溯覆盖。
