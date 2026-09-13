# S 的独立验收准备

当前无 S 产品实现、无正式组件通过；design/g3/s/contract.md / cases.json 为待独立冻结草案。真实 Pi 固定源码及只读容器加载已有准备运行。

运行方式（WSL，项目根）：

- python3 validation/components/s/probe-public.py <new-batch>：真实 Pi public API 小型机制准备，固定 faux，不联网/不读 key。
- python3 validation/components/s/probe-container.py <new-batch>：固定 Linux 镜像/Node/Pi 受限加载，仅精确 RO mount、私有 tmpfs；真实原 Session byte 输出由外部父进程读取。
- python3 validation/components/s/selftest.py <new-batch>：读取 public-preparation-003 固定原文件，验证 oracle 能拒绝坏/缺失/空跑。不是 S 测试。
- python3 validation/components/s/runner.py --bundle <collector-output/bundle.json> --output <report.json>：全部先行案例的独立离线判定。
- python3 validation/components/s/runner.py --driver validation/components/s/collector.py --run-dir <new-run-dir>：driver 收 --plan / --output，只拿 setup/actions，不拿 assertions。默认须全部 27 case，缺一 INVALID。--case 仅诊断子集，不产生完整验收结果。

退出码：0 所要求观察成立；1 至少一条实际断言不成立；2 协议/缺依赖/缺 source/缺 case/坏摘要/空跑，不计作 killed。无 --bundle/--driver 必须退出 2。没有通过的产品默认实现，也不从其他 research 批次填正式 S 结果。

bundle 是 JSON：scope=TRUSTED_COLLECTOR_OUTPUT，cases_sha256 绑定设计 cases 的实际字节，case_evidence 的 key 恰为所执行全部 case ID。每例的 source key 是 cases.evidence_required 加 other 引用源，descriptor 包含 path、sha256、origin=trusted_external_collector。path 必须指向 batch 内实际非 symlink 文件。三类固定 reader：

- session:<label>：严格解析原 Pi v4 JSONL，header、递增 seq、原 entry、value/list 原写入；直接导出 counts/values/entries/完整 stop/tool counts 与 bytes/hash。未知格式、坏完整行、缺 parent 不伪装成空 Session。
- bytes:<label>：直接读取原文件，按 bytes/hash/UTF8 比较；同长度错误内容照样失败。
- journal:<label>：可信 provider、X、OS 或调用设施 collector 的逐行原观察，各行含 type；从真实 rows 计算 count/types/targets/canonical_text。空列表只有经真实 collector 观察的零次数才有效，缺文件不能代替零。

来源标签和摘要只绑定证据，不证明采集独立。正式 collector 必须在候选不可写的位置运行并由独立角色审核、冻结；记录 SUT/collector源码版本、隔离mount、注入时点、输入与完整原输出/物理对象。S返回的 accepted_final/暂停/冲突帧可以证明其提出了什么，不能证明原结果已存/实际effect/进程已停。最后三项只能从对应原 Session、实际效果目标和可信 OS/X见证判定。原库导入清单/Runtime不含策略的分层约束另作源代码审查。

原始准备批全保留：public-preparation-001/002 两次配置错误；003 九观测；container-preparation-001 绝对路径失败；002 两轨迹；oracle-preparation-001 九控制。每次必须新目录，不能覆盖旧输出。独立复跑用新 batch，现版本准备命令也适用于其他角色。

固定依赖：Python3.10 stdlib；Node24.21.0；Pi commit71dca871bc80b6bc97be37f0ca3189399d651fff/TSX现审路径；固定python镜像digest78387bc…184ea与Moby seccomp。无需全局安装。真实 provider 另走 design/g3/s/provider-preparation.md，不能给 S 密钥或把 faux 计作模型能力通过。

实时driver已落盘：collector.py / collector_actions.py / live_ports.py；具体协议见 collector-protocol.md。S/X/F当前缺失时实际MISSING并退出2。S-017与S-011职责修订、原草案保留及R/G5追溯见 design/g3/s/scope-revision-002.md；经独立预审及上下文补件后现在27例150断言，仍非组件通过。

修复预审四项的理由、原版本和准备证据见 design/g3/s/review-repair-003.md。新增 physical_witness.py 实际读取固定 Engine exec / 原 PID namespace，不把容器清单代替进程事实。repair-selftest.py <new-batch> 只校准驱动区间计数、实际固定 Shell stdout 和最终冻结，不运行产品 S。probe-physical.py <new-batch> 只验此 OS observer 的受控真实设施。S 组合资源引用 design/g3/system/contract.md 的单 slot 三对象 / 768 MiB；原 X 二对象 / 256 MiB 不是 S 组合预算。

上下文补件004与先行协议见 design/g3/s/context-supplement-004.json / context-supplement-findings.md；context-selftest.py <new-batch> 运行真实普通文件检索脚本和明确的oracle校准样本，不运行S产品。正式S027验证大树/长diff按需普通工具检索；S020补精确有用片段/范围/原引用。旧26/109及源快照保存在history/before-retrieval-004。
