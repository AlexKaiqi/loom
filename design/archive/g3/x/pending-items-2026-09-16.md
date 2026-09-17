# M05 后未决项清单（2026-09-16）

**性质**：工作项登记，非验收声明。每项含证据来源；独立验收（AGENTS.md 完成门槛）尚未执行，本清单各项均为单 Agent 工作记录。

## 1. M05-JOINT：暂停后保留回执的重放校验失败

- **现象**：恢复轨迹已实现（双响应夹具 + wait_cut 切割 + 租约等待 + M03 drive 恢复 + 原 ID/无重做检查），但 R 行暂停原因为 `original delivery or decision unavailable: SessionServiceError: original provider reply is retained but not a valid Message`。
- **源码位置**：`lore_session/service.py:143-152`（replay 检查 `result['wire'].get('accepted')`）；触发链 = 运行时工具等待窗过期 → drive 暂停 → S 进程内继续（工具完成 → pi 循环再次调用模型 → 第二个 provider 回执被保留）→ 重放校验失败。
- **对照**：M03 崩溃恢复（跨进程重放）通过（15/15）；失败的是同进程暂停后继续路径，两者差异未定位。
- **证据**：m05-execute-046..049（R.sqlite 暂停行、S receipt 目录）。
- **地位**：真实运行时发现，需独立调查；可能同时回答第 2/3 项的设计答案。

## 2. 溢出路径压缩结构性空转（设计级缺口）

- **现象**：`prepareOverflowCompaction` 的准备仅覆盖 systemPrompt 投影（三次实验 tokensBefore 恒 3375，与消息文本规模无关），`messagesToSummarize` 恒空 → 归档 0/0（pi 源码 `structural.ts:1155` + `transcript.ts` readBoundedEntries 只扫 systemPrompt 投影边界）。
- **含义**：若期望"溢出触发的真实裁剪"成为能力，harness 需设计修订：准备条目读取包含消息，或溢出响应结束当前步、由后继机制在新步内完成压缩再驱动。
- **证据**：m05-execute-025（49600 声明溢出）、修订稿续四~续七。

## 3. 单步预算与压缩再驱动的结构性冲突（设计决策待定）

- **现象**：每次 drive 至多 1 个 provider 效果（`lore_session/service.py:119`，m01 记录不变量）vs pi 溢出后同一 drive 内再驱模型 → 守卫在派发前拦截（正确工作，R 保留未决责任），链路必然暂停而非恢复。
- **待决**：步边界压缩 vs 预算豁免规则的门级决策。
- **证据**：修订稿续五、续七。

## 4. 真实内容规模的溢出不可达（事实约束，需配置评审）

- **事实**：wire 请求上限 65536 字节（`lore_provider/request.py:126`）把真实上下文压在 ~16k token（chars/4 实测密度 0.377 tok/byte），低于 contextWindow 49152 → 溢出路径（input>49152）用真实内容不可达；阈值路径（>8192）可达且已验证（M05-TRIM 8/8）。
- **待决**：context_tokens=49152 配置值在传输上限下无真实含义，配置与传输能力匹配需修订评审。

## 5. 独立验收未执行（AGENTS.md 完成门槛）

- M05 套件（TRIM 8/8 六连批、CORRUPT 稳定）目前只有实现者连续批次证据；按最终验收清单，需独立验收者从锁定契约出发直接核对原始证据并复跑核心检查。单 Agent 工作时须记录角色未分离及其局限。

## 6. 工具链：套件编辑后容器侧一致性核验惯例未机制化

- virtiofs 陈旧缓存导致多次新旧混合文件（KeyError/IndentationError 反例，修订稿续二、续三）；现行惯例 = 编辑后 sleep 5 + 容器侧 grep/ast 核验，尚未固化为协议。

## 2026-09-16 增补：Temporal 调研授权

用户指定 [temporalio/temporal](https://github.com/temporalio/temporal) 为调研对象（思想与 Loom 高度重合：durable execution / 持久推进责任），要求记录未决项（即本文件）后 clone 并充分调研，产出：可直接复用组件、应借鉴设计（映射本清单未决项与 v5 架构）、不应借鉴及理由。调研记录：`design/g3/x/temporal-research-2026-09-16.md`（进行中）；clone 位于 `research/repos/temporal`（gitignore 内，head=172d1b409）。


## 2026-09-16 晚更新：未决项 ①②③ 处置结果（goal-a0d0b8c8）

- **JOINT 重放校验（原未决 1）**：已解决——根因为套件夹具 bug（非运行时缺陷），修复后 JOINT 全绿（m05-execute-054 起连续复现）；终态语义经证据修正为 M03 同型。
- **A 级项①（双戳回执）**：诚实放弃——既有重放校验（_verify_wire 重导 normalize）三轮实证有效，双戳无可验证增量。
- **A 级项②（重建+事件充分性）**：语义收束——诚实边界=切割点前证据完整（JOINT 判据固化）；既有机制在全部观测路径充分。
- **A 级项③（步边界决策）**：已决策并验证——预算守卫即步边界实现，OVERFLOW 用例预登记并验证（064-067 全绿）；m01 不变量无需修订。
- **仍未决**：真实规模溢出不可达的配置评审（未决 4）、独立验收（未决 5）、工具链惯例机制化（未决 6）。


## 2026-09-16 深夜更新：用户两项裁定与执行（goal-d324bb94）

- **独立验收**：用户裁定"现在立项：新会话复跑"。验收执行者（新会话、无实现会话上下文）已派出，从锁定契约复跑 M03+M05 并直接核对 M01/M02/M04 证据；报告将写入 design/g3/x/acceptance-record-2026-09-16.md。局限如实声明：同机同工作区，由实现会话运行时派生，非真独立第三方。
- **运行包络**：用户裁定"现规模为准"。已对齐（m01_run.py archive 16384/8192，硬阈值 8192 不变；OVERFLOW 声明 16896）；m05-execute-068 四用例全 PASS。**M06 ARCHIVE 未同步**——登记为后续项：对齐+自有批次重跑。
- 原未决 4（真实规模溢出不可达的配置评审）就此关闭。


## 2026-09-16 深夜增补（goal-d324bb94 收尾）

- 独立验收完成：报告见 design/g3/x/acceptance-record-2026-09-16.md（M03 15/15、M05 十二批全绿+深查达标、M01/M04 在位；执行形态与角色局限如实记录）。
- **新缺口（验收发现）**：M02 证据未随环境迁移——original-M02.json 全卷零命中，validation-status 中 M02 "15/15"无法以原始证据复核，已诚实降级为"当前环境未验证"。后续动作二选一：重建 M02 证据（重跑其套件）或在 validation-status 标注其历史证据失效。
- M06 ARCHIVE 对齐 + 自有批次重跑仍为后续项。
