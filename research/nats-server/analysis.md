# NATS JetStream：确认、历史与重交机制

状态：G2相关机制已实测，待跨项目独立复核；不是Runtime事件契约已通过。固定源提交3c80d8f89eac613bdbae473efb59ec76f8d4ed09，原生Go1.27.1编译，实际binary v2.15.0-dev；build-001.json绑定源码、命令及二进制摘要。开发分支只用于固定版本研究，不自动成为生产依赖选择。

## 职责与状态

Core NATS负责连接、subject路由、身份及服务请求；JetStream的stream持有消息/序号/保留配置，consumer独立持有交付与ack位置。持久consumer不是每个等待任务的专属Agent进程；也不自动知道本系统的请求正文冲突、Harness版本或已受理推进责任。Runtime的受理规则、普通代码依赖和文件视图需在其公开边界之外表达。

源码锚点：server/stream.go:6956—6972按Nats-Msg-Id查ddmap并返回duplicate ack；ddentry为身份/序号/时间，未比较完整内容。server/opts.go:2711支持sync_interval=always；stream.go:1100—1111把真实配置下传file store，并有async persist模式覆盖，不能只看到配置字段就忽略具体stream模式。server/consumer.go负责历史起点与确认恢复，server/filestore.go保存磁盘块与确认相关数据；Go模块实际依赖由go.mod/go.sum锁定，包含nats.go、jwt/nkeys、compress及x/crypto/sys等。

## 预注册与真实结果

protocol-001.json先定义N01—N06；experiment.py直接运行上述NATS二进制和nats-py2.15.0，使用localhost与测试专属目录。evidence/run-001/result.json、server.conf及两段服务日志保存实际观测：

| 问题 | 实际观测 | 对本系统的含义 |
| --- | --- | --- |
| 已确认历史 | file stream显式sync always，收到r1/A的PubAck后SIGKILL，旧PID被回收，新服务/新连接读回同序号、同原始A及身份 | 支持所测进程故障恢复；未测试OS断电、磁盘损毁或复制集故障 |
| 重复与冲突 | r1/A重复、r1/B冲突均得到相同seq及duplicate=true，实际存储仍是A | 原文未被覆盖，但服务没有向调用方拒绝内容冲突；不能把去重直接当P09完整受理契约 |
| 先发生再等待 | 先发布，再建DeliverAll durable pull consumer，得到原A；连接丢失/重启后未ack的同序号再次交付，delivery次数增加；ack_sync后ack floor前移 | 支持历史起点和可恢复交付，业务处理/下一步受理仍须独立可靠交接 |
| 保留边界 | max_msgs=1/discard old下第一条被删除，第二条存在 | consumer持久不抵消stream保留限制，承诺期内不能配置成悄悄淘汰必要事实 |
| 错误对照 | memory stream在进程重启后缺失；DeliverNew晚建时收不到先前事件 | 同一观察能拒绝错误存储或错误历史起点，未将这些负对照包装为正向能力 |

9项观察检查全部通过。这里的PASS表示协议中的能力事实/反例得到观察，不是NATS满足全部Runtime性质。没有任务或远端副作用，也未运行真实模型。

## 复用、适配与不采纳

保留候选：复用JetStream公开publish/read/pull/ack与subject权限、磁盘历史；管理凭据仅在共享服务侧，向Harness注入文件视图/受控薄提交。必须补足严格请求身份与完整内容冲突校验、接收端权威事件来源、下一步受理交接、保留期和历史起点合同。跨这些设施的全局原子性未被证明。

不采纳直接使用Core NATS通知作为唯一责任；不采纳每任务常驻订阅Agent；不采纳bounded duplicate window等于永久请求去重；不采纳Interest/WorkQueue等会因当前消费兴趣而删除未来等待所需事件的默认推论。以上是本系统所需语义的取舍，不是否定这些模式用于它们自己的适用场景。

源码许可证Apache-2.0，具体LICENSE摘要见identity.json；二进制复用需保留对应许可/NOTICE和依赖记录，未把其他商业NATS服务加入已核范围。首次构建与实验使用固定checkout且git状态干净。

复跑：先按build-001的Go命令构建固定checkout，再运行research/.venvs/runtime-research/bin/python research/nats-server/experiment.py NEW_BATCH。环境来源与客户端依赖在research/environment；不覆盖已有批次。

官方概念依据：[JetStream](https://docs.nats.io/concepts/jetstream)、[固定源码](https://github.com/nats-io/nats-server/tree/3c80d8f89eac613bdbae473efb59ec76f8d4ed09)。文档声明与上表的实际观察分开；本轮采用的是源码和实验给出的有限结论。
