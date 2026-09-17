# R/F publication 的窄接缝（实现前冻结）

仅组合已验 R/F；不 dispatch X、不终止进程、不产生策略或第二账本。来源：design/g3/s/tool-integration-map.md §4、原 R19/R22、F install/query_install 与 X016。当前独立准入/集成通过尚未授予。

`FilePublication(control, files, stopped_validator)`；`publish(principal, namespace, install_id, resource, base_ref, materialization_request_id, stopped_ref, authorization)`。resource 是原 R.resolve 完整返回；materialization_request_id 解析本 F 实例原 materialize journal，不接受自报成功目录。stopped_ref 保留完整原 X 引用并有 execution_id/generation；validator(ref, purpose, expected) 必须严格 True，expected 含完整原 namespace/principal/resource/base/execution/generation/materialization/provenance。权限、实际旧 X 停止与关联归 trusted validator；F 本体仍校验原实际根/完整集合/安装窗口。

`control_reference(ref,purpose,expected)` 仅承接 staged/installation/published/stopped；`file_reference(ref,purpose,context)` 仅承接 intent/stop。其他目的由现有可信 resolver 处理。授权 checker 保持外部注入，模块不能给自己签权限。

R 不提供公开 installation 查询，模块以 R 原锁保护的只读 SELECT 读取 installations 原行和 resources 原行；没有另写 JSON/状态目录，全部变更调用既有方法。F 原 journal/versions 是原件解析接口，读取其实际完整 materialize result 与 rooted Git/provenance，不创造 F 回执。公开返回保存原 R intent、完整 F query、投影 installation_ref、当前 R registration、R release。

先验证完整固定引用/原资源授权，再 acquire；R.prepare_install 持久受理完整 staging 投影（含原 publication 输入）后 F.install。F query 的 current_root/retired_root 与原 intent.path 组合为 R current/retired；R expected.version_ref 指完整 staging 投影，F bare version_ref 单独保留。confirm_install 后 release。重入先读取原 R intent，禁止 pending_reconcile 时盲 acquire；已有 F intent 一律 query，绝不第二次交换。R 已确认/已 release 重交也重新核原关联，不增长 revision。

同 ID 任何完整输入变化必须拒；人工编辑、错版本/错根、错 X scope、缺失原件、观察未知不得 confirm 或释放 holder。失 ACK/异常沿原意图查询；原错误传播，不能吞作业务失败/成功。截点回调只使用已有 F checkpoint 或测试包装原 R 方法，不新增产品故障协议。

无 Docker 验证范围：使用已完成 X independent-full-001/X016 原完整 base Git ref、checkpoint 和原 actual-stop Engine/namespace 观测；新 R/F SQLite/Git/真实目录承接该已停止执行的结果。新目录并非旧 X 当时获授权执行的物理根，此事实不隐瞒；测试 validator 对本次受信 fixture 显式绑定新根并验证原逻辑 resource/base/execution/generation/归档，不能作为新鲜 X 授权或撤权证明。产品 validator 仍接收完整原 root/context，正式 live 组合须原完整授权/停止证据。

固定用例（预期来自原接口而非候选返回）：
- FP01 正常：真实 R acquire/prepare、F exchange、R confirm/release；原 base/output 逐成员 bytes+metadata、当前/retired dev/ino、Git ref、SQL holder/installation/revision 直接核。原输出 effect=实际 X archive 的原 bytes。
- FP02 重交/新进程恢复：同完整原调用返回原事实，revision 仅加1、exchange 仅1、原两目录保留；同 ID 改 namespace/principal/授权/resource/base/materialization/stop 任一必须拒。
- FP03 错引用：真实可解析 X 原件的 exec/generation/base 关联错误或原 stop bytes 损坏拒绝；真实另一 F version、materialize 路径/根替换拒绝，不得形成 installation 或交换。validator 为独立原件校验，不把仅非零算通过。
- FP04 普通人工编辑：F BASE_CHANGED，原 human bytes 与两 inode 保留；R holder/未确认 intent 保留，新进程不能将 conflicting 当 installed。
- FP05 F after_exchange_before_record 失 ACK：原真实交换已完成、R 未确认；新进程读取原意图与两实际布局，确认和 release，绝不再次交换。
- FP06 R confirm 已提交后失 ACK：原 revision 已加1/holder尚在；新进程沿原 immutable installation ref release；不再次交换或再次增加 revision。

执行入口 `python3 -B validation/file_publication_probe.py --batch <fresh>`。先保存缺组件 MISSING/exit2/0 执行；候选只返回绿色但不做 R/F 操作必须 FAIL/exit1。正式作者批从复制的完整 lore_files/lore_control/本新模块/原脚本运行，无 pyc；保留每组 SQL、原文件、原异常与前后源码身份。外部 root 独立复跑，不由作者自批系统门槛。
