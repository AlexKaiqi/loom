# S 宿主适配：沿用原接口与原 27 项验收

本文件只把既有 S contract.md / collector-protocol.md 的接线选择写明确；不增加新阶段或变更原 27 例 150 判据。Node X 物理增量独验完成前，不运行这条组合路径。

- 一个可信宿主进程持有一个既有 ExecutionStore；短命验收端通过现有 JSON 请求转交给它。短命 caller EOF 不关闭 Session stdin，不另开同目录 X owner。服务级 Session 方法和验收端均调用同一薄 SessionRun 对象。
- SessionRun 只包装 execute、显式 call ID/offset 的双向通道、checkpoint、resume、seal 和 release。完整 X request / authority 由可信装配给定，Node 回调不能提供或覆盖这些参数。原 Pi JSONL 仍是唯一操作历史；宿主不另写模型—工具循环或业务状态账本。
- 每次 checkpoint 由 SnapshotStore 对真实原 X archive 确认独立 S 副本。原 binding 从其原 Pi 文件取出并核对稳定 Session scope；改变请求字段的拒绝例不能用新请求重写旧绑定。两份 X checkpoint 上限保持：取得真正新 freeze 并确认 S 副本后，通过既有 successor receipt 释放旧 X blob；最终原冻代 seal 后，通过 sealed receipt 转移最后一份，再 release。原 corrupt input 保留为失败材料，不能确认有效快照。
- 可信 F 装配给出四个实际只读树，配置文件在 F 捕获前加入本次 input 树；其生成值绑定原 Harness/input/capability descriptor。配置不含 key 或 provider URL。完整 workspace 仍作为同一普通工具输入，禁止截取已知目标文件替代检索。
- 普通工具结果引用仅关联 X 原完整 binding、原 result 与原 stdout/stderr/checkpoint 字节。保存宿主传输副本时明确标注原回执来源，不在原 X JSON 里追加虚构字段。F 发布只从原 X checkpoint 实际文件取材；query 只解析原执行身份，不重发脚本。
- 原 S 用例保持真实 Pi/Node、X namespace witness、独立 checkpoint tar/JSONL、真实 F Git/read 和原 effect 文件观测；原 faux provider 用于机制测试。新宿主认证扩展另用真实 localhost HTTP 验证，之后才运行预登记三次真实代理机制调用。

开发后的首个诊断必须是原 S001 的实际 accept/drive/save/seal/release；随后原 S003/query 和 S018/tools，相关问题解决后运行完整原 27 例。任何诊断通过只标其范围，不提前授予 S/G5/G6 通过。
