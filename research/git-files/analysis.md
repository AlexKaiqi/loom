# 普通目录与Git：作为AgentFS的机制对照

这是由H06/普通文件语义缺口驱动的既有设施专题，不增加另一批必须项目。protocol.json先于experiment.py和运行保存；实际Linux git版本、命令、返回码、tree ID、原始archive及恢复内容在evidence/run-001。所有操作仅针对本批新目录。

原生Python直接读取Surface模板与blocks；Git元数据位于工作面之外，模型可操作的目录不必暴露.git。受管理范围内强制加入的ignored-input也从固定tree archive恢复出原NEEDED0，反例的普通git add则漏掉它。两个版本域独立前进，恢复旧Surface仍保持Workspace的REPORT1及控制域已发生op1事实。

实验同时捕获了T1/B0的中间tree：Git确实保存当前字节，但tree存在不证明这组多文件构成一致的应用输入。停写/共享写者协调与允许版本组合须是单独合同；H06不能通过只检查Git对象ID解决。5项直接检查通过，4条预注册问题均有原始观察。

与AgentFS比较：Git路线保留普通文件和现有Shell工具，不需把Surface改成SDK/数据库对象；AgentFS提供DB内metadata/文件/调用记录和overlay机制，但本轮SDK证据不能代替普通Shell/FUSE验证，根许可文本也待核。暂将普通目录+已有版本设施保留为较少适配的候选，正式组件选择仍待G2综合审查。

此脚本只验证已列明的普通文本fixture，不是通用安全restore实现。Git默认跟踪/ignore集合、attributes/filter/export-ignore、symlink、空目录和POSIX metadata的覆盖仍要在G3受管理状态合同中明确；不得把简单archive恢复升格为全部目录语义完整。恢复到新目录的切换、旧FD对新权威对象的影响和进程故障切点亦未在本专题通过。源码与版本元数据须留在受限控制侧，而不是模型可写Surface中。

引用：[git add官方说明](https://git-scm.com/docs/git-add)、[git archive官方说明](https://git-scm.com/docs/git-archive)。原生Git作为外部CLI依赖，适用其自身GPLv2及发行包许可；本实验没有复制Git源码或声称所有依赖继承同一许可。复跑命令：python3 research/git-files/experiment.py NEW_BATCH。
