# R20/R21 局部变更影响（先行契约）

旧r-gate PASS、原独立报告和源码保存于history/input-receipt-001；当前门槛显式INVALIDATED。没有生产R实现。原审查者负责本次窄修订，根Agent独立复审，不能自批。

R20澄清confirmed只表示确定回执已保存，新增明确negative与unknown区分；E对外状态另按消息实际保存判定。失败原ID不二次dispatch，显式新accepted attempt关联原negative，未知不能换ID规避。原父策略责任与全部历史不变。

R21只填补原E文件准备与R调用之间的关联缝隙，固定原selector+唯一E目录ref；H/正文/文件列表仍以E manifest为真，R不复制生成。只有显式input_binding的invocation在绑定前不交Harness，pending仍可恢复准备；无需输入的既有请求行为不变。引入一个窄SQL关联表与两个方法，原23伴随场景保留，unit由20增为21。

先固定本契约/判据，再写真实动作与坏/缺失控制。根局部D复审及重新冻结前不开发生产R或组合系统。关联字段已直接与E作者协调，E API须同步使用同一selector/ref形状。
