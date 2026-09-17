# X 执行与私有存储：先行判断

状态 DRAFT_G3，产品尚未实现。目标来自 v5 §4.1/4.2/5.3 与 G1 §6；G2 9b6ec8b 已通过，只授权本阶段契约、判据和环境准备。

直接把权威 Workspace/Surface 以 RW bind 给不可信任务会把宿主 ext4 容量暴露给任务。CPU、pids、memory、周期 du 和 RLIMIT_FSIZE 均不能证明多文件总分配上限，删除仍开放的 FD 也不受路径计数完整覆盖。这条配置不能成为 X 正式资源保证。

候选以每一执行对象的私有有界普通文件副本承载修改，外部权威目录由 F 保持；v5 明确允许复制。旧写者保留在私有对象上时，控制租约过期或 pause 不等于已失权，不能发布/授予当前权威目录新写者。必要版本及原结果确认保存之后才释放环境。

先比较容器直接 tmpfs + pause/Docker cp 与内置 local-driver 私有 named tmpfs volume + pause/只读可信 exporter。Docker 官方 cp 文档明确其 tmpfs/user mount 复制限制，不能从接口名推导导出成功；官方 volume create 文档支持 tmpfs local volume。先行实测见 storage-probe-protocol.json。固定 Engine/image/profile 与 C04 现有外部设施相同，不修改宿主挂载/配额配置。

候选通用 checkpoint 为 exec_id + request_digest + object_generation + F base binding/version → 全 namespace 冻结 → 同一实际对象只读导出 → 外部保存/manifest → resume 原对象或继续 final stop。checkpoint 用于 S 原 Session 前缀 barrier 时，须明确尚未撤权；用于 F publish 时还须实际 stop 的独立证据及 F base 没改变。pause 不冻结外部人工编辑，F 必须在发布时核对当前 generation/内容。

模型 key、Engine socket/句柄、宿主 Session 可写目录不交给任务或 S 受限进程。provider/tool bridge 的可信接收者可以在收到原 intent 后暂停 S/export 原 JSONL；只有外部存储完成后才交付真实调用，不能把进程内 hook 误认为持久确认。该责任由 R/S 契约明确，X 仅提供实际冻结/导出/停止事实。

总资源不能止于工作目录：tmpfs 字节和 inode、所有临时/依赖落点、/dev/shm、内存/无 swap、pids/CPU/时长、stdout/stderr、Engine日志以及归档导出均需预算。已确认原输出不得被“裁剪”删除；生产 X 的输出通道/停写策略必须在正式合同中明确完整保留与超限停止的关系，当前不能仅凭日志轮转声称满足 v5 §6.4。

来源： [Docker cp](https://docs.docker.com/reference/cli/docker/container/cp/)、[tmpfs](https://docs.docker.com/engine/storage/tmpfs/)、[local tmpfs volume](https://docs.docker.com/reference/cli/docker/volume/create/)。固定现场能力由保存的真实探针决定；文档不代替运行证据。

## 准备探针后的候选决定

上述两个候选已执行：直接cp否决，named tmpfs+RO exporter进入正式X候选合同。增加固定root/cap0 keeper只解决普通exec先退出导致tmpfs内容消失，任务UID1000实际无法kill该keeper；它不参与Harness推进或持久等待。原始输出由可信外部有限流保存，接受明确不完整/暂停而非盲重跑。真实结果、失败修正及剩余采用条件详见preparation.md；G3/G4门槛仍由独立审查和实际组件决定。
