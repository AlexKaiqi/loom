# Node Session 增量接口草案（第2版）

原 Python schema1 请求与 X28/97 保持不变。Node schema2 只接受固定 profile、普通 command_argv、完整 readonly_mounts 和内部 Session 绑定；不解析 Pi 业务。字段与拒绝范围以 interface.json/request-template.json 为准。第1版保存在 interface-prior-001；本版吸收根对权限、原 digest 命名、共享资源与字节回执责任的审查。

权限来自共享 X 实例的外部可信注册，不从 peer body 的 caller/transport_principal 得出。传输层注入 principal，body 不得覆盖；每次 query/read/release/retry 均校验原完整授权 context，release 对应 stop。使用唯一 request_digest 维持原 X 命名；真实 grant/slot 关联也固定到原请求。错误沿原 UNAUTHORIZED/ID_CONFLICT/INVALID_REQUEST/INCOMPLETE_OBSERVATION，仅新资源拒绝增加 SLOT_EXHAUSTED。

S snapshot 必须是已有实际原件：snapshot-manifest-contract.json 冻结完整成员、类型、字节、纳秒metadata和空初态真实tar；X负责保留/核对，不将Session装成Surface或Workspace。普通输入和Workspace RO view仍出自真实F，较大规模已先行实跑，后续还须实际Node只读挂载。

X本体负责共享slot的创建前持久预约和实际回收确认、原通道write/cursor/partial/失ACK记录；bridge只是测试传输和现有通道持有者，不成为唯一可靠性机制。一个控制进程直调与多个短peer必须走同一X API/原记录。运输进程退出不隐式关stdin；未知不能重写或新起Node。

原 Engine --shm-size 并未证明64 inode。mount-bounds-protocol.json先冻结对默认值观察和显式/dev/shm tmpfs设施验证，待Docker窗口才能运行；当前64仍是必需但未证实的上限，不能填数字即通过。工作/tmp/全部spool同样须真实核对。原profile/12问题/已有load只作相应有限证据，不替代此增量门槛。

## 动态事实与固定授权规则

可信配置固定 authority root/resolver身份、namespace/principal、profile/slot/grant规则，不提前虚构未来Engine ID。实际owner/restore原件由可信所有者完整保存并fsync后单调登记；peer无登记或替换规则操作。X预期仍取自身原受理execution tuple，逐完整ref读取实际记录，不能把最新可变路径当原件。普通快照record与S ownership record是两份不同来源记录。Node控制信封上限2MiB仅容纳1MiB原bytes的base64；原decoded payload/frame限制不变，旧Python无参数入口不变。
