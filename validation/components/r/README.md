# R 独立验收入口

正式入口：python3 validation/components/r/run_contract.py --module lore.control --batch <fresh-id>。必须同时发现并运行design/g3/r/execution-inventory.json中的22个unit和23个真实进程伴随场景；少case、重复、skip、进程未运行、错误引用、源码/契约变化均不能通过。原组件当前不存在，MISSING退出2，任何组件性质均不记通过。

unit和process的实际目录/SQLite/原引用原件持久保存在同批，失败finally也留raw-final.json和可导出的raw.sql；不以traceback替代原始失败状态。fresh batch禁止覆盖。reference authority是明确的R/X/E/S边界夹具，不能证明真实撤权、事件或模型能力。

oracle-controls仅检验判据反例；missing_capability.py是只会返回PASS字样的已知坏夹具，必须被真实driver拒绝，不是组件替身实现。preparation-001/002是历史准备批，其中TemporaryDirectory保留与总入口缺口已被独立RR01/RR02发现；后续批使用持久fixture与固定完整清单。无生产代码，无G4通过。

R20/21局部补件先行见 design/g3/r/input-receipt-change-impact.md。历史PASS已显式失效，必须由根Agent独立局部D复审。input_fixture为真实四文件E authority夹具，只负责R关联试验；不替代E/NATS组件。22个unit含R21新进程重开查询，原23进程伴随场景保持。

RF02/R22先行补件见restore-plan-change.md和restore-preparation-protocol.md：22unit内含实际accept失ACK切点SIGKILL/新进程原计划与部分安装查询；仍保留原23进程伴随。原gate002已保存并局部失效，真实F/X仍是待组合依赖。
