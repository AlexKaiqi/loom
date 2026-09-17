# M01 原设施独立观察器

沿 entry-contract.md、artifact-oracle-contract.md、system contract 原 M01，不新增业务标准或启动器。API `Observer(config:完整bootstrap dict, output_dir)`；`await begin(sample, registration_ids)` 在受理前；`await collect_m01(sample, request_id)` 在停止后。`mark_accepting()` 在原 start 前、`mark_finished()` 在 drive 返回/异常结束时记录单调时间；只计算两者之差，collect 的独立读耗时不算任务300秒。`notify(*_)` 仅唤醒只读采样，不接收成功事实。begin缺必要配置/原输入拒绝；collect缺项逐项FAIL。旧链未begin不能追认运行时/时间证据；固定响应绝不计真实M01。

原义务8组：O1 原R受理链/外部决定/安装holder-release；O2 原F Git双blob+完整manifest/tar和原整数、report、notes；O3 正常S owner原tar/Pi JSONL、原binding/result/boundary及R决定来源；O4 原provider prepared/HTTP原请求响应/usage、Pi原assistant/native工具及后续反馈；O5 原X双域原requestdigest/result/stop/released、实际Engine GET与完整历史input实际读；O6 独立JetStream client按原seq读正文与下一Step原E四文件输入；O7 真实gpt-5.6-terra、原6响应/6步/2048输出/15360输入/300秒；O8 实际对象资源/配置边界与最终释放。每组有具体checks，不能空组PASS。

原F引用只能从R原selector/安装与原受理工具计划取得；当前注册principal/namespace/read授权逐项核，Git cat-file固定ref:archive.tar与manifest.json均独立SHA。完整tar成员/文件内容与manifest对应后才输出验收副本，无任意宿主文件由模型指定。历史为node_config.input.history_views单项完整version_ref与`/input/history/`+sha(canonical(version_ref))；工具真实原script/输出与该版本字节、实际只读mount和checkpoint共同核对，notes文字不够。此观察是有限正常M01轨迹证据，不外推任意恶意Shell程序的语义等价。

原R SQLite mode=ro/query_only读取；原件都有限读并存SHA。S只用validation.components.s.oracle.pi_jsonl，不导入Runtime/SessionFacts/产品decision或产品求和作oracle。provider仅读原wire，不发模型HTTP。NATS只新共享客户端stream_info/get_msg，不建consumer、不ACK/PUB。Engine仅固定Unix GET，不create/start/kill/exec。后台0.1秒采样原Xroot记录绑定的自有CID及相同slot_owner/slot_id标签的helper，必要通知只缩短错过短对象的窗口；未观察到则缺证据。

单slot同时最多3对象/768MiB，原网络/UID/只读根/能力与原各角色pids限制核实际inspect；各私有源实际块/inode及slot原账同观，预算仍128MiB/8192。共享host/NATS RSS从当前observer宿主PID与本地NATS监听socket唯一PID读取，无法确定则失败；不读进程环境/凭据。输出只写独立output_dir；begin/collect不改变任何目标设施。总体/6样本终验由原M01driver汇总，单次collector不会自授G5。

准备入口：validation/system/observer_probe.py。缺产品前先MISSING，随后空配置/缺原件仍必须拒绝；父任务实际fixed链只供关联/缺项诊断，正式M01须begin+全部真实设施。实际读取只对既有原路径，不重跑组件全套。
