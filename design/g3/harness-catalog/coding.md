# harness 示例：coding（改代码 / 跑测试 / 迭代）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

在授权的代码仓库里读代码、改文件、跑测试，按结果迭代直到目标达成。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `code.iteration.started{}`（可选）；`code.test.result.declared{command_ref, outcome, evidence_ref}`；`code.change.summary{change_ref}`；`code.review.requested{scope}`（可选） |
| 产生者 | harness 声明（**引用**局部事实）；原始工具/模型往返留在 Session／X，**不复制**进面 |
| 触发与受理 | 测试失败 / 评审结论 / 目标变更 → 下一轮；同一次测试结果只开一轮 |
| 投影 | 相关文件片段 + 最近一次测试结果 + 目标 + 指针；**不预展开整个仓库**（v5:250） |
| 逻辑 | 解析模型输出的执行意图（交互约定归 harness，不归 runtime）、双域分流（Surface 笔记 vs Workspace 代码）、失败重试上限与停止条件 |

## 通用原语映射

P1 声明｜P2 受理｜P3 触发｜P4 投影｜P5 逻辑｜P6 身份（`evidence_ref`）｜P7 观测（预算/截止/上下文）。

## 边界与反例

- **Workspace 在任务目录之外**：代码属于外部授权范围，不进任务目录（v5:38、G1:25）。
- **局部事实不复制**：工具结果属 Session/执行器观测域，通过引用进入面（§4.4 规则 2；r:7）。
- Surface 版本 ≠ Workspace 版本，恢复要分别选择并明确组合（G1:94）。
- 反例：把仓库放进 `surface/content/`；把工具 stdout 逐条写成面事件；用 git HEAD 冒充全部恢复依据。

## 框架缺口

**`tools/`（工具定义与交互解析的统一落点）**——已在 `../task-directory-landing.md` §4.1 列为待裁决标准点；coding 是最需要它的场景（也是"缺通用原语就补原语"的典型）。
