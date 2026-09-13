# G1 决定关联补充预注册独立审查

审查角色：long_task_drift，独立于补充案例与模型作者。裁定：**READY_TO_FREEZE**；仅授权本补充模型分支修复与验证，G1总体仍待运行和独立复核。

完整读取cases-durability-supplement.json两例、共同观察规则/操作语义，并直接对照top-level-contracts.md draft3 §3/4与原cases-durability.json的accept_decision定义。原DUR-028只改变payload/execution_id；本次补source_result/harness_version关联，不修改原冻结oracle或既有结论的证据范围。

- DUR-S001与S002各从独立初态开始，先完整同元组重交，E1要求无冲突、E2要求尚未执行，防止一律拒绝重交。
- a3仅改变一个字段：S001使用另一已确认可读源R2；S002改为h1v2而保留R1。两例不共享conflict标志，不能由首个冲突掩盖第二个缺口。
- E3必须显式冲突；E4—E7及E10—E11要求原source/version/payload/execution关联保持；崩溃恢复后原op2仅启动一次。全过程原结果、可解析确认内容和旧实际效果保持，拒绝冲突不等于丢掉原后续责任。
- 共享错误机制ignore_decision_association_conflict只忽略关联字段比较；必须因E3失败被拒，不能读取expected、按case ID返回结果、抹除冲突源或用崩溃替代错误被检出。
- 28条静态断言及all展开后的64条正向比较均可由预定操作/初态和独立环境事实观察；另2个对应错误对照各完整执行，64条比较。操作无未知项，时点/断言ID/因果引用有效。

这是完整关联比较的有限解释，真实序列化规范化、版本真实性、持久确认与任意回调副作用仍是G2/G3债务。h1v1/h1v2为独立符号版本，本批只比较关联身份，不冒充已执行两种真实Harness。

补充文件SHA256：b09e071a2adc9faeafc34deb94d7708f14ef582354cc7dc58eeda2f2c4b0f26a。独立执行清单由审查者直接遍历冻结候选JSON生成，使用原execution-inventory schema且不调用runner枚举器；与本报告、原契约和base cases共同进入freeze-004。初始源码缺口及修复前实际复现由发现角色另存，不能覆盖。
