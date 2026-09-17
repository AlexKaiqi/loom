# harness 示例：research（检索与素材沉淀）

状态：UNVERIFIED 示例。只用通用原语，不新增框架目录/字段。

## 场景

围绕一个问题持续检索、筛选、沉淀素材与结论，直到信息饱和或达到约束。

## 五件套

| 件 | 定义 |
|---|---|
| 词表 + 契约 | `research.question.set{question_ref, scope}`；`research.source.added{source_ref, digest}`；`research.finding.recorded{finding_ref, evidence_refs[]}`；`research.saturation.reached{reason}`（可选） |
| 产生者 | 问题 = 外部/模型经受理；素材与结论 = harness 声明（带来源引用） |
| 触发与受理 | 新素材 / 问题变更 / 模型请求下一轮 → 开轮；同素材重复入库幂等 |
| 投影 | 问题 + **素材目录（指针）** + 上次结论；按需召回（recall 引用，成本挂 Round） |
| 逻辑 | 检索计划、引用完整性要求、饱和度停止；召回是**模型辅助调用** |

## 通用原语映射

P1 声明｜P2 受理｜P3 触发｜P4 投影（含 recall 引用）｜P5 逻辑｜P6 身份（`source_ref`/digest）｜P7 观测（预算）。

## 边界与反例

- **恢复不重放召回调用**：重放只恢复已记录事实，不重做检索（glossary:111-112；v5:163）。
- 素材正文落 `content/` 或按引用存放；模型看到的是**指针**（给指针不灌全文）。
- 反例：把检索结果全量灌进上下文；用召回结果冒充新的因果事实；把索引放进演进史。

## 框架缺口

**模型辅助召回的契约**：Projection 声明 recall 引用、成本挂 Round、恢复不重放——目前只有语义，缺正式接口与观测方式。
