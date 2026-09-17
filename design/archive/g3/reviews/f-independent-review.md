# F G3 独立预审

裁定：CHANGES_REQUESTED，仅 G3 准备。根未编写F合同/driver/oracle。直接读原v5/G1/G2、F合同与实际Python用例，不据子Agent完成总结签字。

## FR01 · D02/D03

F13坏stop均被reference()的固定STOP相等检查预先拒绝，没有真实有效STOP与不同intent.execution_id/generation的关联负例。实现只调用checker而不比意图关联可过。

最小关闭：保持STOP为真实认可值，先用尚未安装的同request意图只改execution_id或generation，检查与STOP关联不符且两目录不变；不要靠已存在request的CONFLICT掩盖。

## FR02 · D03

controls missing_ignored/missing_empty_directory在rename/rmdir后没有先恢复原root mtime；assert_tree可仅因root时间戳差异拒绝。仅比较根metadata而忽略漏成员的坏oracle也能杀这两个负控，负控没有隔离所称错误。

最小关闭：每个结构负控先恢复所有仍存在对象应有metadata（尤其root），保留唯一期望结构差异；用实际快照确认差异字段集合，再断言原observer拒绝。恢复正例也重验。

## FR03 · D02/D04

F11声称关闭实际inotify句柄，但直接信record.monitor_fd并os.close，没有从OS核查句柄对象。

最小关闭：关闭前用/proc/self/fd等实际事实确认anon_inode:inotify，捕获/保存；若测试使用lease fd也应核F_GETLEASE和对象身份，不把SUT给的字段名当机制证明。

## FR04 · D02/D05

F19用固定sleep(.15)推定外部新写者已经触发lease break，未有原子ready或阻塞/信号握手。慢启动可造成无关失败，恢复未知不能靠睡眠制造。

最小关闭：使用独立子进程启动/预open的完整ready记录，并在固定deadline内实际观察SIGIO/阻塞阶段或已记录写请求；保持限时失败，不将等待超时改为通过。

完整被审摘要见 f-independent-review.json。该审查不要求先写生产F，不扩展性能范围；在原用例内补准确观察和相关关联负控。旧设施/准备批保留，修订后重新独立核对。


## 最终准备裁定

D01—D05 PASS，仅限F合同/验证准备，允许进入F独立G4实现；不是F组件能力通过。根重新读修订源码并实际复跑root-oracle-controls-001（12项）及root-driver-preparation-001、root-component-missing-001：漏成员负控只存在所称结构差异，复原正例通过；真实read lease下子进程完整ready/SIGIO且原字节OLD、释放后AFTER；实际inotify句柄被核对；缺生产组件MISSING/退出2、0/19执行。

FR01的首次有效STOP/不匹配原意图exec与generation已进入实际test_F13；FR02原timestamp混淆已消除；FR03实际FD核查已入F11；FR04固定sleep推定改为2秒有界真实握手。初审和旧准备批不改为通过。完整固定输入摘要/命令/限制见同名JSON。

F合同明确普通文件范围、Git rooted保留、权限/metadata前置拒绝、原安装身份与两布局恢复、base与人工编辑监测；可执行19例用真实文件/Git/tar/进程驱动，缺失/错误均传播。reference/authorization ports只替R/X，19个正式用例仍全部UNVERIFIED。跨设施、实际X撤权及完整恢复组合须待相应组件通过后另验。无生产F，无总Goal完成。


## FR05补充与门槛失效

作者在G4之前指出本审查遗漏：F返回archive_path/manifest_path和manifest_sha256及实际成员描述，现有capture helper只读取Git中的归档和检查ref字段非空。伪造/缺失返回路径或成员清单可能未被拒绝。根确认这是既有D02/D03输出义务缺口，不是新功能；先前F D gate已INVALIDATED，原裁定保存f-gate-001-historical.json。尚无生产F，因此不得继续该实现，先在原F01/F05等用例补真实导出字节/manifest hash/独立成员描述与相关错误对照，再独立复审。根承担独立审查遗漏，不以作者自查代替后续验收。


## FR05 独立复核与重新冻结（002）

根 Agent 逐项读取 manifest-contract、observer 和正式 F01/F05 驱动，独立复跑 17 项 oracle 控制、真实 inotify/lease 新写者握手及缺组件入口。返回路径的实际字节与两个 Git blob、归档成员事实与源目录事实、清单字段和类型现在均被直接核对；重新计算伪造成员清单摘要仍被拒绝。19 例保持，缺产品执行 0 例且退出 2。D01—D05 在当前输入版本通过，范围仅限准备。此前撤回的 PASS 和 FR05 漏审完整保留。详情及当前源绑定见 f-fr05-independent-002/review.json；物理组合与产品性质仍未验证。
