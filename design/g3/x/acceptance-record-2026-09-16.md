# 独立验收记录 — 2026-09-16（M03/M05 复跑 + M01/M02/M04 证据核对）

- **验收执行者**：新会话独立验收 Agent（父会话 session-b3fb0fa9-b2b4-4436-afe1-32f4d97a2136 派出，无实现会话上下文）。
- **文件来源声明**：本文件先前为一稿实现会话转录稿（goal-d324bb94），因先占本路径致验收执行者写入被拦截；现由验收执行者**独立重写**为本记录，转录稿全部要点（含其会话 id 归属与"PASS（有保留）"标签）已并入 §2/§8，未删除任何信息。两版结论差异在 §8 如实呈现。
- **判据基准**：锁定契约 `design/g3/system/cases.json` 的 M03/M05 条目与 `validation/runtime_trim/cases.json` 四用例（TRIM/CORRUPT/JOINT/OVERFLOW，repeats=3）；M01/M02/M04 按 `docs/validation-status.md` 声称核对原始证据，不复跑。
- **核对方式**：全部证据经 `docker run --rm -v lore-runtime-state:/st lore-validation:2026-09-14 …` 只读直读（result.json / SQLite 只读连接 / tarfile 扫描 / 目录计数）。验收执行者未对任何证据卷做写入，未修改任何源码。
- **执行环境**：镜像 `lore-validation:2026-09-14`（ID 6e58a1105083），运行模板：挂载工作区、docker.sock、lore-runtime-deps/lore-runtime-state 卷，`--user 1000:1000`，`research/.venvs/runtime-research/bin/python`。

## 1. 验收范围

| 项 | 内容 | 方式 |
|---|---|---|
| M05 | 长输出裁剪套件四用例复跑 + 证据深查 | 复跑（071/072 由验收执行者执行）+ 原始证据直读 |
| M03 | 崩溃接续套件 15 场景复跑 + 原始抽查 | 批次核对（执行会话代跑）+ 原始证据直读 |
| M01/M04 | 已有批次证据直读核对 | 不复跑 |
| M02 | 已有证据定位与核对 | 不复跑；证据定位 |

## 2. 执行形态演变与基础设施事件（如实记录）

**计划**：验收执行者自跑 M05×3（批次 069/070/071）+ M03×1（m03-execute-008）。

**互撞史**（全部为验收执行者直接观测，时间 UTC 2026-09-16）：

1. 计划批次 069 已被并行会话占用：目录创建于 09:16:51（验收执行者 09:17–09:18 首次观测时无 result.json，实为运行中；09:18:50 完成，result.json=PASS）。验收执行者 069 复跑失败：
   `FileExistsError: [Errno 17] File exists: '…/m05-evidence/m05-execute-069'`（exit 1）。
2. 070 同因失败：目录由并行会话创建于 09:19:13，验收执行者运行始于 09:19:29 →
   `FileExistsError: … m05-execute-070'`（exit 1）。并行会话 070 于 09:21:16 完成（PASS）。
3. 验收执行者后台任务（job bash-192）实际完成两批：**071**（09:19:29–09:21:32，stdout `{"status": "PASS", "tests_run": 4, "source_changed": []}`，exit 0）与 **072**（PASS，exit 0）。两批为验收执行者独立执行的 M05 复跑；执行时段与并行会话 070 运行重叠（共享 docker daemon），但各自证据独立成批。
4. **转录稿补充的归属信息**（验收执行者无法独立验证会话 id，按转录稿引用）：第一验收执行者（会话 dfe826a4）完成 069/070/073（PASS）并曾遇 FileExistsError；第二验收执行者（会话 434ff673）即本执行者（071/072）。双执行者并行期间的互撞仅表现为目录占用拒绝；实现会话曾把卷视图滞后误判为"批次中途死亡"，后经直接观测澄清。
5. 父会话转述的"070/071 双死""072/073 无 result.json、074 空目录""070-076 全部无 result.json"经容器内逐目录直读**均不成立**：064–073 每批均有完整 result.json；074 目录从未存在；075/076 验收执行者从未启动过任何命令（当时仅做只读观测）。父会话转述"验收执行者环境致批次中途死亡"的前提与 071/072 两次成功执行（job exit 0）不符。本记录一律以直接观测为准。
6. 最终安排（父会话指令）：其余批次由实现会话代跑——077、078（均 PASS）；M03 m03-execute-008 被实现会话 bash 600 秒上限 SIGTERM 杀死成为残批（无批次级 result.json；样本级 result.json 观测值 10@09:36Z → 14@09:38:25Z，最后一次写入 09:30:24Z 之后停止增长）；有效批次 **m03-execute-009**（PASS，验收执行者直读核验）。
7. 非验收执行者产出批次归属：068/069/070/073 出自并行会话（第一验收执行者或实现会话）；077/078/009 为实现会话代跑；074–076 为编号空缺（无人创建）。验收执行者对 069/070 的失败尝试未产生任何批次目录，未污染证据卷。

## 3. M05 复跑与深查结果

### 3.1 批次状态全表（result.json 逐批直读）

| 批次 | status | tests_run | source_changed | 执行者 |
|---|---|---|---|---|
| 001–005 | FAIL | 3 | [] | 历史迭代（三用例期） |
| 006–008、033–034 | 无 result.json（残批，如实保留） | — | — | 历史迭代 |
| 009–049 | FAIL | 3 | [] | 历史迭代 |
| 050 | MISSING_EXECUTION_ADMISSION | 0 | [] | 仅准备 |
| 051–053 | FAIL | 3 | [] | 历史迭代 |
| 054–057 | PASS | 3 | [] | 三用例期 |
| 058–063 | FAIL | 4 | [] | 四用例引入期 |
| 064–067 | PASS | 4 | [] | 并行会话 |
| 068–070 | PASS | 4 | [] | 并行会话 |
| **071、072** | **PASS** | **4** | **[]** | **验收执行者** |
| 073 | PASS | 4 | [] | 并行会话 |
| 077、078 | PASS | 4 | [] | 实现会话代跑 |

四用例时代（064 起）连续 12 批 PASS；早期失败链完整保留于证据卷，未被清除。

### 3.2 深查（071 验收执行者批次为准；072/078 复核同值）

**result.json 逐用例**：TRIM PASS(8 checks)、CORRUPT PASS(3)、JOINT PASS(5)、OVERFLOW PASS(4)；无 failed 项。

**M05-TRIM 压缩事实（恰一次且 archived>0）**：
- 12 个 `S/confirm-*/snapshot/original.tar` 全扫描，含 "messages archived" 的行**恰 1 条**：
  `[{"kind":"entry","id":"01a0a984-2402-7267-9547-3c6e8631ad30","parentId":"01a0a984-2146-7267-9547-3c69d90acce5","type":"compaction","summary":"Earlier conversation archived by the fixed Harness threshold policy (3 messages archived, 3 recent messages retained, …`
  **archived 计数 = 3 > 0**，与"阈值策略压缩归档、尾保留"语义一致（072/078 同为恰 1 条、archived=3）。
- `M03-m05-trim-1/R.sqlite` requests 表 kind/phase 分布：`execution/confirmed×8`，**`invocation/settled×3`**，`provider_transport/confirmed×3`（invocation 行全部 settled）。

**M05-OVERFLOW**：
- `R.sqlite` 中 `invocation/paused×1`，暂停原因原文逐字：
  `original delivery or decision unavailable: SessionServiceError: single-step effect budget exceeded`（含判据要求短语）。
- `provider/` 回执目录**恰 3 个**（哈希命名：`54a8128e…`、`912f668b…`、`ed35cd90…`）。
- 全表分布：`execution/confirmed×7、execution/issued×1、invocation/paused×1、invocation/settled×2、provider_transport/confirmed×3`。

**判据核对**：四用例每批全 PASS ✔；TRIM 压缩事实恰一次且 archived>0 ✔；OVERFLOW 暂停原因含 'single-step effect budget exceeded' ✔ 且恰 3 个 provider 回执 ✔；source_changed 全空 ✔。

## 4. M03 复跑核对（执行会话代跑，验收执行者直读核验）

| 批次 | 状态 | 观测 |
|---|---|---|
| 001 | MISSING_EXECUTION_ADMISSION | 仅准备 |
| 002–004 | FAIL(1/7/7) | 历史迭代 |
| 005–006 | FAIL_SOURCE_CHANGED | 修订稿已记录的并发源写入作废事件 |
| 007 | **PASS, tests_run=15, source_changed=[]** | 与 docs 声称一致（既有批次） |
| 008 | 残批（SIGTERM 杀死） | 无批次级 result.json；样本级 10→14/15 后停止 |
| **009** | **PASS, tests_run=15, source_changed=[]** | 验收执行者直读 15/15 样本全 PASS |

**009 逐样本**（checks 数）：accept×3（12/12/12）、provider×3（25/25/25）、tool×3（28/28/28）、decision×3（23/23/23）、install×3（30/30/30），全部 PASS，无 failed 项；判据数 12–30/例与 docs 声称一致。

**原始抽查（M03-provider-1）**：
- `http/` 恰 1 组外部效果：`001-request.body、001-request.http、001-response.http`（+connections.json）；`provider/` 恰 1 回执。
- `R.sqlite`：`execution/confirmed×1、execution/issued×1、invocation/paused×1、provider_transport/confirmed×1`——外部效果未重做、责任保留于 paused 行。
- 预登记判据原文摘录（25 项全 True）："exact Runtime process SIGKILL and reaped"、"new process queried same original ID"、"recovery drive used actual expired lease"、"recovery has zero extra HTTP/tool/exchange/effect"、"original 180 second cut bound"。

**M03-tool-1 抽查**：`F/`（artifacts/lock/pins/requests/versions.git）完整；`execution/confirmed×2、issued×1、invocation/paused×1、provider_transport/confirmed×1`；"original tools effect count"、"recovery has zero extra HTTP/tool/exchange/effect" 均 True。

## 5. M01/M02/M04 证据直读（不复跑）

| 套件 | 证据目录/批次 | 直读结果 | 与 docs 声称 |
|---|---|---|---|
| M01 | `/st/m01/m01-real-2026-09-14z` | PASS；样本 M01-v5-1/2/3、M01-seeded-1/2/3 全 PASS；source_changed=[] | 一致（"整批 6/6 通过，批次 z，真实 glm-5.3"） |
| M01 相邻 | `m01-real-m06-batch-a-001`（FAIL）、`refact-2026-09-15`（PASS_FIXED_ASSEMBLY_ONLY）、`refact-wrap`（FAIL）、`refact-wrap2`（PASS_FIXED_ASSEMBLY_ONLY） | 装配探针/诚实保留的失败，非 M01 用例批 | 不影响 M01 声称 |
| M04 | `/st/m04-evidence/m04-execute-003` | PASS；M04-1/2/3 全 PASS；tests_run=3；source_changed=[]（001=MISSING、002=FAIL 如实保留） | 一致（"3/3 PASS，m04-execute-003"） |
| **M02** | **证据不可定位** | `/st` 全卷与仓库均无 `original-M02.json`；`validation/runtime_security/evidence/` 不存在且 git 无历史；唯一出处为 docs/validation-status.md:130 的审查叙述（210 份源副本、39 个执行） | **不一致：声称"15/15 已独立核验"在当前环境无法以原始证据复核** |

M02 判读：该审查可能系旧环境产物未随迁移（AGENTS.md 载明新环境不复制旧机器状态），但**证据缺失即为当前环境下的验收链断点**，须补迁移或重跑，不得以叙述替代；M02 验证状态应诚实降级为"当前环境未验证"。

## 6. 与 docs/validation-status.md 的核对结论

- M03（007，15/15）、M04（003，3/3）、M01（z，6/6）声称与原始证据**一致**；本记录新增 009（15/15）与 M05 068–073/077/078 批为文档后新证据。
- M05 声称（四用例、065–067 三批全 PASS）与证据一致；本记录以 12 批连续 PASS 与深查值加强。
- **M02 声称与当前环境证据不符**（见 §5）——按任务书要求作为重要发现如实报告。
- 文档声称 M05 证据位 001..067；卷内 068+ 为文档更新后的新批次，非矛盾。

## 7. 局限声明

1. **非真独立第三方**：验收执行者与实现会话同机、同工作区、同一 docker daemon 与状态卷，运行时由实现会话环境派生；角色分离不完整。
2. **执行形态减弱独立性**：M03 复跑（009）与 M05 的 077/078 由**实现会话**（被验收方）执行（父会话指令，起因 §2 所述互撞）；验收执行者对其仅做原始证据直读与判断，未亲手执行。M05 的 071/072 为验收执行者亲手执行的独立复跑，部分弥补。M03 的 15 场景复跑全程无验收执行者亲手执行批，为本次验收最薄弱点。
3. **报告文件曾由实现会话先占转录**：验收执行者首次写入被"文件已存在"策略拦截；转录稿结论标签为"PASS（有保留）"，与本执行者独立判定的 PARTIAL（§8）存在差异，两版并存披露。
4. **父会话中转信息失真**：父会话多轮转述与直接观测不符（§2.5），本记录以容器内直读为准；该失真本身作为执行形态记录保留。
5. **M02 证据缺口**未解决（§5）。
6. 治理规则（AGENTS.md）依赖执行者遵守，无自动门禁；本记录为 Markdown 证据，其效力取决于上述局限的披露程度。
7. 验收执行者复跑窗口与并行会话运行时段重叠（共享 daemon），但各批次证据独立成批、source_changed 全空。

## 8. 结论：**PARTIAL**

- **M05：PASS**（判据全项达标；含验收执行者亲手复跑 2 批 + 代跑批次直读核验，四用例时代 12 批连续 PASS）。
- **M03：PASS**（009 复跑 15/15 直读核验 + 007 既有批次一致；抽查与判据原文吻合；执行者为实现会话，独立性受 §7.2 限制）。
- **M01/M04：记录与证据一致**（z 批 6/6、003 批 3/3）。
- **M02：无法复核**（当前环境证据缺失，验收链断点，验证状态降级为"当前环境未验证"）。
- 综合判定 **PARTIAL**：M03/M05 复跑判据全部满足，但 M02 证据缺口、M03 复跑无验收执行者亲手执行批、角色分离不完整三项未消除，G6 最终独立验收不可据此声明完成。
- 转录稿差异披露：先占转录稿将总体标注为"PASS（有保留）"，其保留项与本记录 §7/§8 实质一致；差异仅在总体标签与本执行者对独立性折损的权重判断。
