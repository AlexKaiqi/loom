# design/archive（历史层归档）

地位：**已结束阶段的组件契约、用例、评审与证据记录**。只读参考，不是现行设计；
现行设计基线见 [g3/README.md](../g3/README.md)。文件内容一律未改动（含其中的旧术语
Task/Workspace、冻结判据名 `task_uid` 等）——记录不回写；路径沿革由 git 追溯。

归档原因（2026-09-17）：门流程"一组件一目录"的工作文件在阶段结束后原地滞留，
与现行基线混放；按"保留历史、划清层次"整批 git mv 到此，不删一份。

## 布局与映射

| 归档路径 | 原路径 | 内容 |
|---|---|---|
| [g1/](g1/) | design/g1 | G1 阶段记录 |
| [g2/](g2/) | design/g2 | G2 阶段记录 |
| [g3/e/](g3/e/) | design/g3/e | E 事件底座：契约、用例、记录（9 文件） |
| [g3/f/](g3/f/) | design/g3/f | F 文件/版本：capture/manifest 合同与用例（18） |
| [g3/r/](g3/r/) | design/g3/r | R 账本/运行控制（10） |
| [g3/s/](g3/s/) | design/g3/s | S 会话：契约与用例（20） |
| [g3/v/](g3/v/) | design/g3/v | V 验证组件（3） |
| [g3/x/](g3/x/) | design/g3/x | X 沙箱：契约、profile、待决项（16） |
| [g3/x-node-profile/](g3/x-node-profile/) | design/g3/x-node-profile | 容器 node profile 证据链（27） |
| [g3/system/](g3/system/) | design/g3/system | 系统级 workload/oracle（21） |
| [g3/reviews/](g3/reviews/) | design/g3/reviews | 独立评审记录 R/V/X（18） |
| [g3/provider/](g3/provider/) | design/g3/provider | 模型 provider 适配记录（14） |
| [g3/tool-service/](g3/tool-service/) | design/g3/tool-service | 工具服务记录（1） |
| [g3/file-publication/](g3/file-publication/) | design/g3/file-publication | 文件发布记录（4） |
| [g3/session-plans/](g3/session-plans/) | design/g3/session-plans | 会话计划（4） |
| [g3/coordination.md](g3/coordination.md) | design/g3/coordination.md | G3 组件协调记录 |
| [g3/x-large-tool-inodes.md](g3/x-large-tool-inodes.md) | design/g3/x-large-tool-inodes.md | X 大工具 inode 记录 |
| [g3/x-runtime-input.md](g3/x-runtime-input.md) | design/g3/x-runtime-input.md | X runtime 输入记录 |
| [g3/minimal-harness-extension-points.md](g3/minimal-harness-extension-points.md) | design/g3/minimal-harness-extension-points.md | 早期接口说明（拓展点语义已被 [g3/work-directory-landing.md](../g3/work-directory-landing.md) §4 吸收） |
| [g4/](g4/) | design/g4 | G4 期 F/R 门记录（f-gate.json、r-gate.json 等） |

## 引用约定

现行文档中的短码引用（如 `e:7`、`r:9`、`f:38`、`G1:32`）指这些目录内文件的
行号，含义不变；带路径的活链接已更新为 `design/archive/...`。历史记录
（docs/validation-status.md、acceptance/、amendment-*）中的旧路径照原样保留，
不构成断链义务。
