# SoL-Pi：可插拔观测投影与原文召回，归档完整性仍需外层保证

研究问题：P01/P07/P12、H02/H10。commitd7ecfc089944f0d04b80122a0a9a6ca0d786f3d0；根版本0.1.0，锁定Pi组件0.84.2。它是独立Pi扩展，不是另一个持久执行Runtime。MIT及固定依赖见[identity.json](identity.json)。

## 实际调用链与归属

[ObservationPack](https://github.com/NVlabs/SoL-Pi/blob/d7ecfc089944f0d04b80122a0a9a6ca0d786f3d0/src/sol-pi/extensions/observation-pack/index.ts#L142)在公开context hook复制消息数组、替换被投影的工具结果，未修改Session条目。纯文本成功工具结果超过10KiB才参与；前2次完整发送，以后转placeholder。字数/4是token估计，阈值是候选策略，未冻结为lore需求。

[observation.ts](https://github.com/NVlabs/SoL-Pi/blob/d7ecfc089944f0d04b80122a0a9a6ca0d786f3d0/src/sol-pi/extensions/observation-pack/observation.ts)以toolName、toolCallId、内容SHA256生成会话内短ID，原文对象置于Session目录派生的sol-pi/session-id下。ensureStored使用O_EXCL/O_NOFOLLOW，已存在对象校验大小及哈希；失败时保持完整观测。obs_recall按字节和行分页并避免UTF8末尾截断。但readRecallChunk只检查普通文件/分页范围，不重新校验内容hash。对象路径本身不是内容完整性的证据。

扩展其他机制已读取实际路径：
- evidence-preserving-reducer/index.ts58—175先archiveBody，再模型生成receipt，validateReceipt校验source/hash/引用；不可验证或不更短则保留原结果。它在tool_result hook工作，归档和journal是额外资产，不能仅把receipt当原始输出。
- online-context-compact/extension.ts314—415在agent_settled后执行compact，成功后sendMessage(triggerTurn:true)，用内存continuation promise等到子回合settled。恢复从Session分支custom entries重建部分策略状态；这不是任意崩溃切点的durable continue责任账。
- action-fusion通过公开registerTool扩展write/edit及then_run，减少交互轮次。工具融合不自动提供效果原子性或权限隔离。

## 先行协议与实测

[protocol.json](protocol.json)先登记；[experiment.py](experiment.py)/[worker.mts](worker.mts)实际执行候选扩展和真实公开SessionManager。上游FakePi仅派发context hook并取得已注册tool，未使用FakeSessionManager。工具原文是固定fixture；没有AgentSession/provider runner或真实模型，因此不冒称完整Pi宿主集成。

[mechanism-001](evidence/mechanism-001/run.json)保存5个独立进程阶段、原始输出、Session前后文件：
- 前2次投影等于原文，第3次减少为带ID的placeholder，中段标记不可见；原Session JSONL前后字节完全相同。
- 新进程打开原Session后，实际obs_recall分页重建原文，SHA256为968cd0c216b41288942f857fc339538514b7fad186e8d742b9429313bd19a1d1。
- 归档后改写首个字节且大小不变，再用新进程召回：没有报错，返回错误内容；其hash为3844a88da7e4b8d243803de8b180fa02d7794cfcef86f0269c4d600c635425af。
- 随后投影检查既有对象发现hash mismatch，保留完整原文；未知ID召回拒绝。此正对照没有掩盖召回完整性缺口。

运行status=OBSERVED表示边界被观察；RECALL_INTEGRITY_GAP仍是明确失败能力，不能填写P12整体PASS。

## 候选使用与不采纳项

可独立拆出“投影引用→原始对象→分页召回”适配器和receipt引用校验方法，引用绑定来源、内容hash、会话和适用版本。正式候选必须在G3补只读/不可变权威对象、召回时校验、保留期/缺失显式错误，并用真实宿主验证扩展顺序及压缩后查原文。不另造Session数据库来替代Pi的原始历史。

暂不整套采用在线经济阈值、自动压缩和融合写工具：它们是策略选择，未经lore价值用例/权限边界验收。此次只读取这些路径，未实测其模型reducer、compaction回调生命周期、树导航、故障恢复或收益。

Pi0.84.2 SessionManager与本次研究Pi0.85.1的lane/operation API不同；SoL与当前Pi的直接组合未验证。没有修改Pi上游、安装全局扩展或声称完成SoL managed install。npm ci使用冻结lock且ignore-scripts；完整依赖树/执行环境与证据索引见identity。归档fsync/断电、目录竞争及对恶意宿主的隔离不在本实验结论内。
