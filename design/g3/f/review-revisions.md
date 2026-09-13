# F 独立预审问题与准备修订

根Agent在reviews/f-independent-review列FR01—FR04，原代码/原准备批均保留。本页是作者修订说明，最终关闭由原独立审查者裁定。

- FR01：F13保留authority实际认可STOP；对首次尚未安装的新request，分别只改接受intent.execution_id/generation，原STOP仍有效，必须因关联不符拒绝；current/staged两份独立全集合均保持。原无效/缺stop控制仍在，不能用已有请求CONFLICT代替。
- FR02：结构控制将ignored移到受测root之外，断言前恢复共同成员metadata；实际snapshot差异必须恰为missing=[指定成员]、extra=[]、changed_common_entries=[]，hardlink关系不变。每次复原另验正例。oracle-controls-003实际12项通过，isolated-difference原观测保留；旧10项批不删除。
- FR03：F11关闭前读取/proc/self/fd/<fd>必须为anon_inode:inotify并保存实际内核对象。driver-preparation-003独立建立并核验真实inotify FD，未用候选字段名自证。
- FR04：F19改为writer_worker原子ready记录（PID/目标/阶段），2秒截止内实际SIGIO+子进程仍阻塞+原字节未变三项观测。验收checkpoint先截获通知完成这一有界观察，再转交原SUT SIGIO handler（允许handler抛原错误），启动child即登记清理关系，不靠固定sleep推断。driver-preparation-003直接用真实read lease验证helper：释放前OLD/阻塞，释放后AFTER/exit0。该事实只证明验收helper，不证明未实现F。

当前MISSING批004仍真实Linux exit2且0/19执行；正式源哈希在driver-preparation-003。未写生产F，不签G4通过。

## FR05：原通过状态撤回后的补件

作者收尾自查发现原返回archive/manifest实际交付义务未被验收器读取；根独立确认遗漏并撤回门槛，历史PASS与原版本保留于d5c07b4。manifest-contract.md先固定轻量结构与两个Git blob/实际文件/范围绑定。observer现逐字节读两路径和对应Git blob，独立解析tar真实成员（不extract、不跟随symlink），用Decimal读取mtime纳秒，并与源实际lstat/字节/链接/属性生成的size/hash/metadata逐项相等；重新给假清单计算hash仍不能通过。

原F01补无.git目录/完整目录/实际archive import的三种来源及返回双artifact检查；F05补丢返回路径、manifest错误hash、实际manifest Git对象损坏。oracle-controls-004包含17项控制：完整真实Git/tar/manifest夹具通过，不存在archive/manifest路径、错误清单hash、hash正确但成员size伪造均被准确拒绝。此夹具只是验收器已知输入，未代替F实现。driver-preparation-004固定当前19例，组件仍MISSING/exit2；原所有批次不覆盖。FR05最终关闭仍由根独立复核。
