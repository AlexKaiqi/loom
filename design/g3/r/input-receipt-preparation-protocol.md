# R20/R21 局部准备协议

登记于运行 preparation-004 前。本批不含生产组件或功能通过。合同已先明确 RE-02/03，才追加测试序列。原20单元/23进程记录、原PASS及失效原因保存在history/input-receipt-001。

预期：语法及固定发现必须为21单元+原23进程；原oracle三项继续通过。真实输入authority控制使用独立实际目录，原四文件+固定selector为真；缺目录、同长破坏、目录对象替换、缺manifest文件成员为假；实际完整但另一selector的引用自身可校验，和原expected关联不匹配为假。恢复原bytes后可校验。所有原件、原控制观测、源码hash持久保存。

正式入口指向不存在lore.control必须MISSING、退出2、零执行；只返回PASS字样的missing_capability必须FAIL、退出1、全部21单元确实尝试，原始unit/process失败目录留存。错误夹具不提供R功能证据。R20/21真实SUT状态、SQL、新进程行为在组件实现后依同一先行driver执行；本批不通过其功能。

冻结候选需绑定合同/cases/inventory/全部实际driver及fixture源码，保留完整stdout/stderr/准确Linux退出码。仅根Agent独立局部审查可重新批准D门槛；本补件作者不自批R。
