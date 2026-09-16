# 最简 harness 的拓展点地图（minimal-harness extension points）

地位：本文件是接口说明，不是规范。最简 harness 在每个点上做"最简单有效的实现"，
但每个点的拓展机制是显式的、有合同的存在。特定领域 harness（M07 计算机使用、
图像输入、多模态管线……）在拓展点上完善，而不是改写最简实现。

## 所有权三层（本轮反例链的提炼）

| 层 | 内容 | 变更机制 |
|---|---|---|
| 宿主合同 | append-only 事实、投影文档完整性、X slot 包络、发布源同一性 | 修订（证据准入，反例先行） |
| 领域调参 | 包络之内的取值：归档阈值、三层截止、预算、基线声明 | 配置 / runner 值（仍须反例准入，但不动产品常量） |
| 领域拓展 | hook 行为、观测协议、领域视图 | hook 合同 + config 声明 |

判定规则：改"值"用调参，改"行为"用 hook，改"不变量"用修订。
六轮批次反例中五次的病根是所有权错位，见文末教训表。

## 拓展点清单

### 1. 模型基线（wire model scope）
- 最简实现：`lore_provider/request.py` `MODEL`/`MODEL_ALIAS` 常量；响应校验
  "精确基线 id 或钉定日期别名"二元匹配，别名轮换响亮失败（不做前缀猜测放行）。
- 拓展机制：修订（amendment-model-baseline-2026-09-15 先例）。
- 领域空间：切基线须带模态探针（glm-5.3 拒收 image_url 的 protocol-002 反例）、
  生产形状门禁（protocol-003：先证 reasoning_effort/parallel_tool_calls 已被发送过）、
  以及**自己的观测协议**（O7 已参数化为 config 声明 expected_model/expected_model_alias，
  不得静默复用旧基线仪器）。

### 2. 每步上下文投影（fixed views）
- 最简实现：投影产物是严格的 `JSON.stringify({context_blocks:[...]})` 文档；
  视图集合固定（任务、事件、历史目录、prior feedback、工作区快照）。
- 拓展机制：`transform_context` hook——**合同：返回值必须保形**（解析-修改-再序列化；
  非投影形状返回 invalid_input 响亮失败）。m01-real-2026-09-14ab 反例：
  自由文本追加破坏 JSON 完整性，observer 的 strings() 解析链断裂，O6 失配。
- 领域空间：RAG、工具结果剪枝、重排序、领域视图注入——行为任意，形状不可破。

### 3. 上下文工作集维护（历史归档）
- **普遍问题**：模型上下文窗口有限，任何 harness 都必须回答：什么留在窗口内、
  什么离开、离开后去了哪里、模型如何知道去哪找。这是与具体领域无关的
  "五脏"器官——最简 harness 必须有，且必须有完整合同：触发、移出、指针、
  耐久性（Session JSONL + 文件）、可观测性（事实记录）。
- **最简策略：threshold archive**（无具体场景时的最自然选择）：数据原样
  留在授权目录与 Session JSONL（无损），上下文只留说明与 ref；旧前缀
  归档、近期工作保留。命名上这是 archive 而非 compaction——没有有损合并、
  没有重写，只有归档与指针；pi 缝隙名（`before_compaction` hook、
  `CompactionEntry` 类型）是 pi 的实现词汇，仅限缝隙层，不代表策略名。
- 最简实现：读 `capability_limits.archive`（context_tokens/reserve_tokens/
  tail_reserve_tokens/soft_tokens 四键，结构校验由 startup_assets 白名单执行）；
  硬阈值走 pi 原生 shouldCompact，`before_compaction` hook 返回**确定性**
  CompactResult（fixed summary/retainedTail/tokensBefore/details），零 LLM 摘要调用；
  软阈值经 transform_context 注入固定文本压力提示（作为 context_block，见 2）。
- 拓展机制：**策略可整体替换，缝隙不变**（已实现为监测/策略分层：
  index.mts 的 window monitor 固定估算与阈值比较并向 strategy 发事件，
  strategy.pressureNote / strategy.archive 可整体替换）——阈值/尾部 =
  领域调参；摘要 = hook（可换 LLM 摘要器）；触发 = 协议（模型主动归档）。
- 领域空间：检索式（RAG，离开窗口的按需取回）、模型主动归档
  （before_run_end → lane.compact(customInstructions)，软阈值标记协议，
  已设计未实现）、分层摘要、工具结果剪枝。
- 设计判断（batch-ae 反例）：阈值不是越小越好，而是"不破坏任务精度的最小上下文"；
  归档点必须保留工作记忆，同时把增长压在准入边界之下。
- 实测注记（batch-ao）：推理模型 completion 含大量 reasoning tokens，
  total usage 持续高于 fire-at，压缩每个 drive 触发——但尾部保留使工作集
  连贯，任务照常闭环。触发节奏与任务完成正交，正是"合同在宿主、策略可换"的验证。

### 4. 预算准入（budget admission）
- 最简实现：max_requests / max_input_tokens（**scope 累计**，非每请求）/
  max_output_tokens_per_request / max_request_body_bytes / max_seconds。
- 拓展机制：配置（budget dict）+ 派生纪律。
- 派生纪律（batch-ai 反例）：累计输入 = max_requests × max_request_body_bytes/4。
  链型变化（归档延长链到 14-17 invocation）时从既有常量重新推导，不任意放宽。

### 5. 截止层次（three deadlines）
- 最简实现：三层互相独立——node 步 deadline（request-template budgets，上限在
  node_profile LIMITS）、runner 整链预算（m01.py drive_until）、S scope max_seconds
  （provider_owner 预算）。
- 拓展机制：各层自己的配置。
- 教训（batch-aa/af 反例）：同一个"300"曾同时是三层各自的值且互不知晓；
  领域 harness 定尺寸时必须先指认每一层截止的所有者，任何一层超时都表现为
  相同的"channel ended or deadline elapsed"，根因定位成本高。

### 6. X slot 包络（security envelope）
- 最简实现：CONTROL_BYTES/CONTROL_INODES 常量（每执行 slot 历史的字节/inode 上界）；
  helper 容器预算从常量派生（writable_bytes=3*CONTROL_BYTES、
  writable_inodes=128+CONTROL_INODES）；计划总预算（SLOT.all_active_writable_*）
  是并发预订与保留 spool 债务的和界。
- 拓展机制：修订。**这不是调参对象**。
- 容量发现的连锁（batch-ag/ah 反例）：包络 8× → helper 预订随之 8× →
  计划总预算必须 2× 同步。提升包络必须连带其全部派生预算，会计链不可断。

### 7. 事件与通知（E）
- 最简实现：JetStream 固定 profile（file storage、discard new、max_age 0、
  单副本）；emit 即外部事实；输入投影按 filters 重放事件视图。
- 拓展机制：输入投影 filters 配置。
- 领域空间：领域流、事件形状、通知语义。O6 的仪器约束：真实事件原文必须
  出现在下一步输入的投影文档中——领域视图设计不得绕开该可观测性。

### 8. 终止判定（decide）
- 最简实现：decide/settle 相位 + 外部停止应用（stop_physical）。
- 拓展机制：运行时合同（R 事实形状不可变）。
- 领域空间：领域完成语义（何为 settled）挂在 decide 之前的 harness 判定，
  事实记录形状不变。

### 9. 观测协议（observer instruments）
- 最简实现：O1-O8 仪器（链条、工具输出可达、发布、预算、事件、X/F 原件）。
- 拓展机制：config 声明（如 observation.expected_model）；新领域/新基线
  定义自己的检查，旧仪器保持绑定其通过批次（批次 z 的 glm-5.3 仪器对不替换）。
- 领域空间：领域 harness 的验收映射。禁止删检查/换数据制造成功。

### 10. 工具执行（X）
- 最简实现：shell 双域（runtime/task）、固定配额（MAXIMA）、双流 + 退出码 +
  checkpoint 冻结。
- 拓展机制：request-template 配额（领域调参）+ 包络（修订）。
- 领域空间：领域工具、更长步截止（aa 反例：真实推理模型往返 + 归档后重探索）。

## 教训表（所有权错位的六次现形）

| 批次 | 错位 | 应对的拓展点 |
|---|---|---|
| aa | 截止值散落常量，无所有者 | 5：三层截止各自显式配置 |
| ab | hook 行为破坏宿主合同 | 2：transform_context 保形合同 |
| ae | 调参（fire-at）压过任务精度 | 3：阈值是"不破坏精度的最小上下文" |
| af | 第三层截止无人指认 | 5：同 aa，runner 层 |
| ag/ah | 包络提升未连带派生预算 | 6：会计链不可断 |
| ai | 累计预算按旧链型硬编码 | 4：从常量推导，不硬编码 |

## 并发警示（2026-09-15）

本文件与 amendment-m01-output-budget 的 ae-ai 记录在另一 Agent 的
amendment-environment-profile-2026-09-15 工作落盘期间恢复/撰写；
真实批次（aj 起）须在独占工作区后执行，批次 ai 证据因混入在途改动
不作独立系统证据。
