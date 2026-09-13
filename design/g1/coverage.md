# G1 性质、有限轨迹与真实证据去向

这是一份可机械追溯的索引，不裁定G1或系统通过。原始244项仍由G0矩阵管理；没有直接模型用例的要求不因此豁免。有限轨迹与论证只能支持相应设计解释，所有真实Runtime性质仍为UNVERIFIED。模型中的持久性、隔离、版本及资源实体是声明的抽象，不是实际Linux事实。

| 性质 | 已预注册主用例 | 真实能力前提 |
| --- | --- | --- |
| P01 | G1-BND-018, G1-STR-001, G1-STR-003 | H02, H10 |
| P02 | G1-BND-001, G1-BND-002, G1-BND-003, G1-BND-004, G1-BND-005, G1-BND-006, G1-BND-009, G1-BND-017, G1-BND-021 | H04, H05 |
| P03 | G1-BND-008, G1-BND-009, G1-BND-010, G1-BND-011, G1-BND-012 | H04, H05 |
| P04 | G1-BND-011, G1-BND-012, G1-BND-013, G1-BND-014, G1-BND-017, G1-BND-018, G1-BND-019, G1-BND-020 | H01, H06, H07, H08 |
| P05 | G1-BND-001, G1-BND-002, G1-BND-003, G1-BND-004, G1-BND-005, G1-BND-006, G1-BND-007, G1-BND-010 | H04, H05 |
| P06 | DUR-022, DUR-023, DUR-024 | H03, H08, H09 |
| P07 | DUR-006, DUR-007, DUR-008, DUR-009, DUR-010, DUR-011, DUR-013, DUR-014, DUR-015, DUR-017, DUR-018, DUR-019, DUR-020, DUR-021, DUR-022, DUR-023, DUR-025, DUR-027, DUR-028, G1-BND-018, G1-BND-020, DUR-S001, DUR-S002 | H01, H02, H03, H08, H09 |
| P08 | G1-BND-001, G1-BND-002, G1-BND-007, G1-BND-014, G1-BND-015, G1-BND-016, G1-BND-017, G1-BND-018, G1-BND-020, G1-BND-021 | H04 |
| P09 | DUR-001, DUR-002, DUR-003, DUR-004, DUR-005, DUR-019, DUR-028, DUR-S001, DUR-S002 | H01, H02, H03 |
| P10 | DUR-007, DUR-008, DUR-013, DUR-014, DUR-015, DUR-016, DUR-017, DUR-018, DUR-019, DUR-020, DUR-021, DUR-022, DUR-025, DUR-026, DUR-027, DUR-028, DUR-S001, DUR-S002 | H01, H03, H09 |
| P11 | DUR-006, DUR-007, DUR-010, DUR-011, DUR-012, DUR-019, DUR-024, DUR-025, DUR-028, G1-BND-020, DUR-S001, DUR-S002 | H02, H05, H07 |
| P12 | G1-BND-011, G1-BND-012, G1-BND-013, G1-BND-016, G1-BND-018, G1-BND-019, G1-BND-020, G1-BND-021, G1-STR-002 | H01, H02, H06, H10 |
| P13 | G1-STR-002, G1-STR-003 | H01, H02, H03, H04, H06, H08, H10 |
| P14 |  | H04, H05, H10 |
| P15 |  | H03, H08, H09 |

H01—H10定义及反驳实验见 alternatives-review.md §6。G2先核实这些底层机制是否可用，G3—G4分别验证组件，G5验证组合后的实际性质。P13实际模型闭环、P14多策略比较和P15规模结论均不能由G1推导。P14/P15的样本、工作负载、度量与通过标准须在对应实现前独立论证和冻结。

补充轨迹DUR-S001/S002覆盖原DUR-028遗漏的来源结果/Harness版本冲突，freeze-004先行冻结；根g1-002在修复后55正/56负通过，独立g1-independent-002已逐项复跑闭合，G1裁定见g1-gate.json。

机器索引 coverage.json列出每个性质的全部原文要求编号、预注册案例以及没有直接主模型案例的要求，后者仍须按原要求层级获得设计/调研/组件/系统证据。这里不把简单的ID关联当作充分覆盖审查。
