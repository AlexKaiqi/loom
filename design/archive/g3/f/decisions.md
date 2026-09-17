# F G3 决策与待关闭问题

- F-D01：普通目录→GNU pax tar完整归档→受限bare Git rooted commit/ref；用户.git/attrs仅为数据。设施FP01/02支持，不用原生Git tree遗漏空目录或mode/ACL，不执行工作区过滤器。
- F-D02：版本/授权/保留控制位于控制侧；历史引用绑定resource/domain/version/path/type/hash。S/E原事实不进入文件回退。
- F-D03：X交固定generation的prepared只读产物，真实stop后F才发布；X tmpfs能力与F host能力分别检查。直接docker cp失败已保留，不采用。
- F-B01原阻断：普通未协调编辑不能仅靠generation/双hash/inotify推断稳定。FP03支持read leases拒绝旧FD/mmap；契约现明确递归watch+lease+实际base+受限窗口、错误/overflow/重启失效。G4正式算法必须跑真实并发反例，设施不替代它。
- F-B02原阻断：完整metadata/安全解包。FP01同owner可读fixture证实ACL/xattr等保真；host不可读/不支持身份显式拒绝，X更窄profile先拒绝。恶意archive由正式独立cases测试，未提前实现。
- F-B03原阻断：目录与R绑定无跨设施事务。FP04支持renameat2 exchange但不撤销FD；R/F缺口G3-RF-01已报根Agent并接受：prepare_install→F实际布局查询→confirm_install推进原resource；不确定布局保护两份、占用不释放。

上述是G3设计与设施准备，不是生产组件通过。正式接口/用例/oracle和独立审查齐备前不得签D门槛；G4故障证据需独立验收。
