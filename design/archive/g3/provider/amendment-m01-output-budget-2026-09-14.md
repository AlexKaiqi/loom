# 修订记录：M01 每请求输出预算 2048 → 16384（m01-output-budget-2026-09-14）

## 独立理由（反例证据先行）

provider-compatibility-001 amendment-001 已记录：glm-5.3 在内部推理上消耗
completion 预算（16-token 探针全部耗尽为 reasoning_tokens，无正文）。该记录
保留了修订后的判据：以生产预算完成 probe A/B。

新反例（m01-real-2026-09-14，M01-v5-1 真实样本）：

- 生产请求 prompt_tokens=932（含 surface 输入与 shell 工具定义），
  max_output_tokens_per_request=2048；
- 响应 finish_reason=length，completion_tokens=2048 全部为
  reasoning_tokens（completion_tokens_details.reasoning_tokens=2048），
  正文与 tool_calls 均未产生；
- 链在 provider_transport 确认后停在
  "original result has no external control decision"，O1/O3/O5/O6/O2 检查失败。

即 2048 输出预算在推理型模型上不足以产生任何首个有效步骤结果，M01 无法在
该预算下闭环。这不是 wire 兼容问题（usage 一致、HTTP 200、模型回显精确）。

## 修订内容

- LIMITS.response_tokens：2048 → 16384（validation/system/m01_run.py）。
- model.maxTokens：2048 → 16384（runtime 每请求 max_tokens 语义）。
- capability_limits.max_output_tokens_per_request：2048 → 16384。
- lore_runtime/provider_owner.py：DEFAULT_BUDGET.max_output_tokens_per_request
  与 Wire profile 上限 2048 → 16384（max_request_body_bytes 上限 65536 不变，
  原始请求体预算仍为 15360 字节）。
- design/g3/x-node-profile/request-template.json：budgets.deadline_seconds
  30 → 300（真实推理型模型的外部模型往返超过 30 秒步进截止；旧值保留于
  design/g3/provider/amendment-m01-output-budget-2026-09-14.md；original-host
  副本同步重新生成；模板 schema 不引入新字段）。
- lore_execution/node_profile.py：LIMITS.deadline_seconds 上限 30 → 300
  （与模板一致）。
- lore_provider/request.py：encode_request 的 max_completion_tokens wire 上限
  2048 → 16384（此前该上限使 16384 意图预算在 wire 编码处被拒，
  m01-real-2026-09-14g/h/i/j 批次的 provider 调用从未发起）。
- lore_session/provider.py：ProviderBridge 模型范围校验
  max_completion_tokens ≤ 2048 → ≤ 16384（同一 16384 意图预算的桥接侧上限，
  m01-real-2026-09-14e..k 批次由此在桥接校验处被拒，provider 调用未发起）。
- lore_runtime/provider_owner.py：ProviderOwner transport timeout 上限
  60 → 300（m01-real-2026-09-14m：glm-5.3 真实推理往返超过 60s，transport
  以 complete=false 中断，效果停在 issued）；validation/system/m01_run.py 的
  provider timeout 60 → 300 同步。
- lore_session/provider.py：ProviderBridge timeout 上限 60 → 300
  （m01-real-2026-09-14n：transport timeout 修订后桥接侧 60s 校验先行拒绝，
  provider 效果未创建）。
- lore_provider/client.py：WireClient timeout 上限 60 → 300
  （m01-real-2026-09-14o：桥接通过后 wire 客户端 60s 校验拒绝，
  reason=invalid_endpoint）。transport timeout 修订链至此完整：
  bridge/provider_owner/wire client 均 ≤300。
- validation/system/m01_run.py：每样本墙钟预算 LIMITS.seconds 与
  scope max_seconds 300 → 1800（m01-real-2026-09-14p 实测：glm-5.3
  非流式推理往返 159s（step1 成功，49KB 响应）与 125s（step2 连接被
  对端中断，complete=false）——多步真实样本不可能在 300s 内完成；
  300s 原值按固定响应探针时延标定）。transport/bridge/wire timeout
  上限 300 维持不变，scope deadline 取 max_seconds=1800。
- reasoning_effort 修订（m01-real-2026-09-14q 反例）：glm-5.3 无法关闭
  thinking，16384 输出预算全部被 reasoning_tokens 消耗（finish=length、
  completion_tokens=16384、reasoning_tokens=16383、无 tool_calls，provider
  wire 已确认 200/70KB）——批次 c（2048）与批次 q（16384）同一失败形态，
  证明 token 上限本身不构成推理深度控制。实测（独立探针，plan/v3 同端点）：
  reasoning_effort=low 时 glm-5.3 以 22 reasoning tokens、1.6s 返回
  tool_calls。因此 wire 请求体新增 reasoning_effort（取值 low/medium/high/max）：
  - lore_provider/request.py：encode_request intent 集合与请求体增加
    reasoning_effort；
  - lore_session/provider.py：model_scope 增加 reasoning_effort 并传入
    intent；
  - lore_runtime/provider_owner.py：budget 接受 reasoning_effort（默认 low），
    model_scope 传递；validation/system/m01_run.py budget 设
    reasoning_effort="low"。
  旧请求体形状（model,n,stream,max_completion_tokens,messages,tools）保留于
  本修订记录；发送端为既有严格 schema 之上的显式扩展，不放宽任何校验。
- 输入预算修订（m01-real-2026-09-14s 反例）：M01-v5-1 全样本通过后，
  M01-v5-2 在 4 次 provider_transport confirmed（均 200）后，第 5 次请求被
  准入拒绝 'projected original request exceeds the input budget'——
  真实工具调用链每轮累积工具结果，15360 token / 15360 字节的输入预算
  按 2048 时代单轮往返标定，不能容纳多轮真实上下文。修订：
  - lore_runtime/provider_owner.py：DEFAULT_BUDGET.max_input_tokens
    15360 → 49152、max_request_body_bytes 15360 → 65536（与 wire
    encode 上限一致；owner 校验 max_request_body_bytes ≤ 65536 不变）；
  - validation/system/m01_run.py：LIMITS.total_input_tokens 与 budget
    max_input_tokens/max_request_body_bytes 同步。
  旧值保留于本记录；模型响应/输出预算与步进截止不受影响。
- reasoning_effort 取值修订（m01-real-2026-09-14t 反例）：M01-v5-1 第 5 次
  provider 往返（finish=tool_calls）返回畸形工具调用参数
  {"script": "..."}（SHELL 工具声明参数为 command），wire/Message 校验正确
  拒绝，invocation 暂停——low 档推理过浅导致参数名漂移。实测 medium 档
  12 reasoning tokens / 1.6s 且参数名正确。M01 预算 reasoning_effort
  low → medium（validation/system/m01_run.py；DEFAULT_BUDGET 默认值同步）。
  低档反例 wire 证据保留于批次 t。
- usage 校验修订（m01-real-2026-09-14u 反例）：Ark glm-5.3 的
  reasoning_tokens 可略大于 completion_tokens（实测 completion=120、
  reasoning=122，finish=tool_calls 正常），'reasoning ⊆ completion' 的
  子集不变量是该供应商的假设而非普遍事实。lore_provider/response.py：
  require(reasoning<=completion) → require(reasoning<=totalTokens)；
  原检查保留于本记录。wire 证据批次 u。
- 步数预算修订（m01-real-2026-09-14v/w 反例）：真实样本的显式 Step 流
  （初始输入 + 通知驱动的后续 Step，每个 Step 1-3 次真实工具调用）在
  会话累计第 6 步触发 'fixed Harness step limit reached'
  （harnesses/minimal/index.mts 按 pi.result 计数）；随后的新 Step 的
  accept checkpoint 里没有新 binding，descriptor 回退到上一 Step binding，
  触发 facts 'original confirmed Session binding differs'（批次 v/w 的
  可观测性差异输出证实：owner op=runtime-next-81d62… vs x op=
  runtime-next-2190a…）。修订（原值 6 保留于本记录）：
  - validation/system/m01_run.py：LIMITS.model_responses/steps 6 → 24、
    capability_limits.max_steps 6 → 24、budget.max_requests 6 → 24；
  - lore_runtime/provider_owner.py：DEFAULT_BUDGET.max_requests 6 → 24。
- validation/system/runtime_observer.py：O7 original_step_token_time_limits
  观测阈值同步修订（墙钟 ≤300→≤1800、rows/provider ≤6→≤24、
  completion ≤2048→≤16384、prompt 累计 ≤15360→≤49152），使独立观测
  与修订后的合同一致；旧阈值保留于本记录。
- parallel_tool_calls 修订（m01-real-2026-09-14y 反例）：M01-v5-2 首个
  drive 步的 glm-5.3 响应包含 2 个并行 tool_calls，参考 Harness 只接受
  单一 shell 调用（native.length>1 → committed abort → blocked_invalid），
  invocation 以 'no external control decision' 暂停。请求体新增固定字段
  parallel_tool_calls=false（实测 plan/v3 接受，响应单一 tool call）：
  - lore_provider/request.py：encode_request 请求体加入
    parallel_tool_calls=false（固定常量，不属于 intent）。
- 有界上下文归档修订（batch-s 反例准入；组件证据 assembly-2026-09-14j）：
  真实多步工具链的上下文随步数线性增长（输入预算被迫 15360→49152），
  阈值归档成为第 8 项必要机制。实现（pi 原生阈值 compaction + hook 供给
  确定性摘要，无额外模型调用，不触碰 wire/service 合同）：
  - harnesses/minimal/index.mts：limits.archive 读入 {context_tokens,
    reserve_tokens, tail_reserve_tokens, soft_tokens}；contextWindow 必须等于
    context_tokens；before_compaction hook 返回确定性 CompactResult
    （fromHook=true 事实条目，含 trigger/archived_messages/policy details）；
    transform_context 在 soft_tokens 以上注入上下文压力提示。
  - lore_runtime/startup_assets.py：capability_limits 白名单加入 archive
    （四键正整数、reserve<context、soft<context）。
  - validation/system/m01_run.py：archive=dict(context_tokens=16384,
    reserve_tokens=13312, tail_reserve_tokens=1024, soft_tokens=1536)，
    model.contextWindow=16384；fire-at 3072 估算 token，低于 wire 准入
    49152。注意 contextWindow 兼任 pi 溢出检测（usage.input>contextWindow
    判 overflow），窗口必须大于真实最大 usage——probe 曾以 40 触发误判。
  - validation/runtime_assembly_probe.py：固定响应 usage 递增（10/280/2980，
    保持 total=prompt+completion 不变量），archive 阈值 4096/3968 触发；
    PASS_FIXED_ASSEMBLY_ONLY 且 compaction 事实落盘（组件证据，非系统验收）。
  - 模型主动归档（软阈值标记协议）为下一准入候选，需边界/决策合同扩展；
    本轮仅记录设计，未实现。
- 投影完整性修订（m01-real-2026-09-14ab 反例）：transform_context 软阈值
  提示曾以自由文本追加在 systemPrompt 之后，破坏 {context_blocks} 投影
  文档的 JSON 完整性（observer strings() 解析失败 → O6 通知匹配为空）。
  修订：提示作为新增 context_block 写入 JSON 内部（index.mts 解析-追加-
  再序列化，非 {context_blocks} 形状则 invalid_input 响亮失败）。
- O7 模型范围基线参数化（履行 amendment-model-baseline-2026-09-15 的
  "新基线批次须定义自己的观测协议"）：observer O7 original_real_model_scope
  改为断言 config 声明的 expected_model（请求）与 {expected_model,
  expected_model_alias}（响应回显），details 记录所断言基线；批次 z 的
  glm-5.3 仪器绑定保持不变。m01_run 新基线批次声明
  deepseek-v4-flash / deepseek-v4-flash-ga-260731。
- 归档点再修订（m01-real-2026-09-14ae 反例）：真实模型批次在 fire-at 3072
  下每二至三步即归档，模型反复丢失报告精确发布路径，notes 写出不精确
  链接（O5/O4 级联）。修订 m01 阈值：context_tokens 16384 → 49152（= wire
  输入上限）、reserve_tokens 13312 → 40960（fire-at 3072 → 8192）、
  tail_reserve_tokens 1024 → 4096、soft_tokens 1536 → 8192。设计判断：
  归档点必须保留可完成任务的工作记忆，同时把增长压在准入边界之下。
  旧值保留于本记录。
- runner 链截止修订（m01-real-2026-09-14af 反例）：系统 runner 存在第三个
  300 秒截止（m01.py drive_until 的整链预算，与 node 步截止、S scope 预算
  互相独立）。归档启用后真实链达 8+ invocation，runner 恰在 start+300s
  弃驱并 seal。修订：m01.py 链截止 300 → 900（仍在 O7 的 1800 墙内）。
  旧值 300 保留于本记录。
- X slot 包络修订（m01-real-2026-09-14ag 反例）：归档链 14 个 invocation
  全部 settled、通知匹配（O6）通过后，通知步的重验证 invocation 打满
  X 有界 slot 历史（SLOT_EXHAUSTED）。修订：lore_execution/slots.py
  CONTROL_BYTES MIB→8*MIB、CONTROL_INODES 128→1024（helper 容器预算
  从常量派生）。旧值 3MiB/128 保留于本记录。
- 计划总预算同步修订（m01-real-2026-09-14ah 反例）：slot 包络 8x 后，
  helper 预订使并发总量超出计划总预算，首个 invocation 即
  SLOT_EXHAUSTED（retained spool writable_bytes）。修订：
  startup_assets.py SLOT 与 design/g3/x-node-profile/profile.json 的
  all_active_writable_bytes 134217728→268435456、
  all_active_writable_inodes 8192→16384。旧值保留于本记录。
  startup_assets 探针在本工作副本不可运行（缺
  validation/components/x_node_profile/evidence/node-independent-full-001
  冻结证据包，预先存在缺口）；门禁以 check_source + 真实批次代替并如实记录。
- 归档尾部保留修订（m01-real-2026-09-14ak 反例，两因叠加）：
  （1）batch-ae 的 m01_run 阈值修订曾被并发工作区写回悄悄回滚
  （archive 回到 16384/13312/1024/1536，fire-at 3072），节点在估算 6242
  时即触发压缩——本次重新应用并已在树内核验；
  （2）before_compaction hook 的 retainedTail 回退为空数组，preparation
  未预计算尾部时整段历史（含新鲜 toolResult）被归档，模型连续三轮
  盲执行工具（O4 三工具 later_provider=false）。修订：hook 自行按
  tail_reserve_tokens 计算保留尾，尾部止于最新条目、起于 user 边界
  （保证 assistant/toolResult 配对完整），archived 计数改为
  messagesToSummarize.length − retained.length。
  修复后压缩语义：归档旧前缀、保留近期工作——与 O4 的"工具输出必须
  到达模型"仪器重新一致。
- 尾部保留再修订（m01-real-2026-09-14an 反例）：ak 修复的尾部循环在
  最新条目自身超预算时立即 break，retained=0，压缩后模型再次盲跑且
  三次重复 emit（emit 循环与压缩周期一一对应：压缩擦除"已 emit"的
  会话记忆，模板的"Do not emit it again"失效）。修订：最新条目无条件
  保留；向后延伸到最近 user 边界（assistant/toolResult 配对完整）；
  其后仅在预算内延伸。压缩-emit 循环的根因是记忆擦除，尾部保留恢复
  后由模板指令自行约束模型行为，harness 不做领域特判。
- 累计输入预算修订（m01-real-2026-09-14ai 反例）：max_input_tokens 是
  scope 累计输入预算（O7 的 sum 检查同源），按归档前 5-8 次调用链型设计；
  归档链 14-17 个 invocation 累计超限（projected request exceeds input
  budget）。修订：max_input_tokens 49152 → 393216，推导自既有常量
  max_requests(24) × max_request_body_bytes/4(16384)，非任意放宽；O7
  镜像同步。旧值保留于本记录。
- node 驱动期限修订（m01-real-2026-09-14aa 反例）：阈值归档生效后，模型
  失去已归档历史会在步内重新探索（如 find .lore），单 drive 实测在
  deadline_seconds=300 处被 stop_physical 强杀（工具请求待回、无结果帧，
  O1/O4/O6/O7 失败）。修订：
  - design/g3/x-node-profile/request-template.json：
    budgets.deadline_seconds 300 → 600；
  - lore_execution/node_profile.py：LIMITS.deadline_seconds 上限 300 → 600；
  - original-host/request-template.json 同步再生成。旧值 300 保留于本记录。
- lore_execution/channel.py：stop_physical 触发时在 journal 保留
  result.stop_reason（可观测性修订；不再让 seal 覆盖后丢失停机原因）。

## 旧记录保留

- 旧值 2048 见上方修订内容；其来源为 openai-proxy 基线
  （gpt-5.6-terra，非推理计费形态）时期的 recorded LIMITS。
- amendment-001（provider-compatibility-001）保留其 16-token 反例与修订判据；
  evidence-001/evidence-002 原样保留。
- 失败批次 m01-real-2026-09-14 全量证据保留（六样本，首样本 FAIL，其余未运行）。

## 影响分析

- 输入预算不变：total_input_tokens=15360、max_request_body_bytes=15360、
  model_responses=6、steps=6、max_seconds=300 均维持原判据。
- 预算准入规则（budget-admission-001）不受影响：其判据针对输入侧投影，
  输出预算仅进入 X capability limits 与 per-request max_tokens。
- 更大输出预算可能延长单样本时延；M01 仍以 6/6 PASS、每样本 ≤300s 判定，
  不放宽任何检查。
- 若未来换成非推理形态模型，预算维持 16384 仍是上限而非目标值，不构成放水。


## 工作区并发警示（2026-09-15，恢复记录）

本记录的 ae–ai 五条曾于 2026-09-15 14:0x-14:2x 落盘，随后被并发写入覆盖
丢失；本次为恢复重写（产品文件改动经树内核验仍在）。批次 ai 运行窗口与
另一 Agent 的 amendment-environment-profile-2026-09-15 工作落盘
（lore_execution/{backend,engine,requests}.py、lore_runtime/tool_plans.py、
environment_profiles.json）重叠，该批次证据混入未完成的第三方改动，
不作为归档机制的独立系统证据；其失败（input budget）的机理分析与预算
推导仍然成立，但须在独占工作区后以新批次复证。在此之前暂停真实批次执行。


## 批次结果（2026-09-15，batch-ao）

- **M01-v5-1 / v5-2 / v5-3 全部 PASS**（归档启用，真实 deepseek-v4-flash，
  每样本 12+ 项独立检查：链条、工具输出可达、双域发布、历史真实读取、
  通知匹配、预算、Engine inspect、资源界）。归档机制在真实链条端到端
  闭环：阈值压缩 + 确定性摘要 + 尾部保留 + 通知匹配全部被真实行使。
- 推理模型下的压缩节奏：deepseek 的 completion 含大量 reasoning tokens，
  total usage 持续高于 fire-at → 每个 drive 都触发压缩，但尾部保留使
  工作集保持连贯，任务仍闭环（v5 三样本证实）。
- 残留（M01-seeded-1 FAIL，3/4）：① 双重 emit（O6 events==2）：压缩频繁
  触发下模型偶发丢失"已 emit"语境而重复 emit，任务模板已明令禁止仍违例，
  属基线模型行为残留；② O4 一个盲工具 + O8 两个缺失 inspect（捕获竞态）。
  runner 在首个失败样本处停止，seeded-2/3 未运行。
- 判定：归档机制的机制证据以 v5 三样本为准；seeded 残留作为
  deepseek 基线行为发现记录，不归因归档机制。

- 监测/策略分层重构（2026-09-15，行为保持）：index.mts 内检测半边
  提升为固定 window monitor（estimate + 阈值比较 + 缝隙接线），处置半边
  收敛为 strategy.pressureNote / strategy.archive 两个可换函数。此前软阈值
  的估算与比较内嵌在 transform_context 处理器中，违反"发事件固定、处理
  逻辑可换"的接缝纪律；重构后衍生 harness 复用监测层、仅替换 strategy。
  组件证据：runtime_assembly_probe --batch refact-2026-09-15
  PASS_FIXED_ASSEMBLY_ONLY（链条 settled、emit 与通知匹配、source_unchanged）。

- O8 尾部采样修订（2026-09-15，batch-ao seeded-1 反例）：required_ids 取
  最终记录全集，observed 只扫 tick 捕获；最后一次 tick 之后落盘的绑定
  记录（2 个 s-exec）从未被采到（1473 tick 零错误），检查结构性不可满足。
  修订：O8 计算前对未被捕获的记录容器补一次直接采样；已退出的容器以
  Engine exec 记录（inspect 200 + ContainerID 匹配 + user 1000:1000）作为
  活体执行证明。修订前"仅 Running 捕获"的要求与本反例保留于本记录。
  验证：check_source PASS（102 项）；下次真实批次行使。
- 批次/探针调用封装（scripts/lore_batch.sh）：deps 卷必须挂载在
  dependencies-manifest.json 记录的物理路径，任意挂载点会触发
  startup-assets 物理身份检查失败（'original directory required'）；
  仓库根由脚本位置推导并以同一路径挂载。
- 封装烟测记录（如实）：lore_batch.sh probe 烟测运行时链条在
  assembly-start 处 paused（首个 s-exec issued 未 confirmed，0 次 wire
  调用，1.7s），与此前直接调用（bash-96 同挂载 PASS）条件一致但结果
  不同；封装的 docker 参数与手动模板逐项一致，机械管道正常（探针 JSON
  正常传出）。根因未隔离（疑内层任务容器启动或运行时状态残留），
  下次会话从探针 out 目录（R rows/begin.json）取证。手动命令模板仍是
  已验证路径；封装在烟测通过前不得视为可用。

## 批次 ap 与封装烟测的共同根因（2026-09-15，已定位待处置）

- 两处失败同因：SessionServiceError('fixed-node-pi-session-v1') → 链条
  在首个 invocation 处 paused（ap 的全部 O 检查失败是其下游）。
- 根因：并发 Agent 的环境档案注册表（lore_execution/environment_profiles.json
  + requests.py 的 profile_sha256 绑定检查）只注册了 fixed-python-linux-v1
  与 linux-browser-v1；M01 的 node 档案 fixed-node-pi-session-v1 不在
  注册表中。generic 路径的绑定检查要求成员资格，归档期链条行使该路径
  即失败。batch ao 通过说明该检查的触发与批次链型相关（其"零行为变化"
  声明对归档期链型不成立）。
- 处置选项（留给下一会话，属对方修订的所有权范围）：
  （a）为 fixed-node-pi-session-v1 补注册表条目（绑定当前
  original-host/profile.json sha256=51dc06a7…）；
  （b）修订 requests.py：未注册但经 startup_assets 准入的档案按既有
  准入证据放行（回退路径），恢复零行为变化语义。
  治理：此为对方所有权文件的修订，须按修订纪律记录；在处置前，
  m01 真实批次与探针均被此缺陷阻塞，O8 尾部修订的真实行使顺延。

- 回退实现（2026-09-15，接根因节）：store.py 注册表查找改为
  PROFILES.get + 未注册环境回退引擎内置 PROFILE 事实（镜像/默认 seccomp），
  与集成前行为逐字一致（git diff 佐证）；注册环境不受影响。引擎
  options 对 seccomp=None 沿用默认路径（签名本就如此）。
  门禁：check_source PASS（399/102，store.py 身份已随修订刷新）。
  行使验证：批次 ap 重跑 + 封装烟测复验（见下）。

- 批次 aq 结果（2026-09-15，经封装 lore_batch.sh 运行）：v5-1 PASS——
  store.py 回退在真实链行使通过，注册表缺陷处置完成。v5-2 FAIL（11
  settled 0 paused）：① O4 一个工具 exit_code 1（模型脚本错误，行为残留）；
  ② O8 仍缺尾部执行——seal 的容器清理先于任何事后采样，事后直接采样
  得 404，结构性证据缺口，需运行时在 seal 前发终通知（下次会话，
  运行时侧修订）；③ O7 KeyError('volumes') 为本次合成 tick 缺全形字段
  所致，已修（volumes/slots/volume_transitions/private_storage 全形）。
  门禁：check_source PASS。

- seal 终采样实现与批次 ar 结果（2026-09-15）：observer 新增
  final_tick()（确定性完整采样并落盘），m01.py 在 mark_finished 之后、
  rt.close 之前 await 之（成功路径与 finally 路径各一处）——消除"最后
  一次采样与容器清理赛跑"的结构性竞态。批次 ar：v5-1 PASS；v5-2 FAIL
  为 emit 循环 ×3 级联（O6 events=3 → O1 外部停止缺失 → O5/O7/O8 下游
  连锁，与 batch an 同型），属基线模型行为残留；O8 修订在此异常链型上
  验证不充分，需在正常链型（v5-1 型）上再确认。门禁：check_source PASS
  （399/102）。移交：一次正常链型批次即完成 O8/O7 双项验证收口。

- 终采样定位再修订（2026-09-15，batch-as 反例）：final_tick 原在
  rt.query 之前，query/close 期间新建的执行记录落在采样之后，O8 仍缺。
  修订：final_tick 移至 rt.query 之后、rt.close 之前——容器仍在、记录
  已全。行使验证留给下一批次（as2/at）；check_source PASS。

## 批次 at 中断记录（2026-09-15，非本工作流改动）

- at 在启动准入即失败：ExecutionError('fixed admitted Node profile/slot
  differs')——早于本工作流的任何修订路径（runner/observer）。
- 证据：original-host/profile.json mtime=Sep 15 14:02（本工作流最后同步
  在数小时前；request-template.json 仍为 12:32）——admitted profile 在
  as 与 at 之间被外部工作区活动修改，startup_assets 的 SLOT 一致性
  校验拒绝之。
- 治理处置：该文件属被治理的 admitted 档案，本工作流不擅自再生成
  覆盖（可能抹掉外部流的有意变更）。移交：与工作区所有者确认 14:02
  变更的意图；若为误改，从 design/g3/x-node-profile 重同步
  （profile+request-template 成对）后跑批次 at 即完成 O8/O7 收口。
  O8 终采样定位修订（query 后、close 前）已落，check_source PASS，
  待行使。

- at 阻塞处置（2026-09-15，经所有者"继续"授权）：诊断确认 14:02 的
  外部变更是设计档的有意修订（design/g3/x-node-profile/profile.json：
  tool 内存 128MiB→768MiB、cpus tool 0.25→1.0、all_active_writable_bytes
  256→512MiB，startup_assets.SLOT 已同步）——original-host 副本为本
  工作流早前的陈旧再生成。已按设计档重同步 original-host 两件。
  行使：批次 au。

- 批次 au 结果（2026-09-15）：启动准入通过（重同步生效），但链条在
  F 工件解析失败（'MISSING: independently resolved original F artifacts'，
  0 工具、双域无产物），且 O8 actual_original_resource_bounds 失配——
  外部设计修订（tool 内存/cpus/总包络上调）的涟漪超出 profile 文件本身：
  本工作流的 O8 计划总包络镜像（ag/ah 期 256MiB）与新计划 512MiB 不一致，
  其它 SLOT 派生镜像（helper 预算、计划合计）亦需按新包络重新推导。
  定性：归档工作需在新包络上做一次镜像重定基（rebase），属新修订周期。
- 移交（新会话）：①按新 SLOT 重推导并更新 O8/O7 及计划镜像；
  ②诊断 F 工件解析失败与新 profile 的关系（platform_revision/引用链）；
  ③重跑批次行使 O8 终采样 + 镜像。全部背景见本修正案与
  docs/validation-status.md；check_source PASS（401/102）。

- 会话流注册表回退（2026-09-15，goal-ce467e61 第 1 轮，batch au→ax 诊断链）：
  au 的 'F 工件缺失' 为症状，真因经 node_profile.guarded 内因上浮
  （两轮强化：异常类型+最深帧）锁定 tool_plans.py:56——
  _load_environment_profiles()[environment] 直接索引，会话环境
  fixed-node-pi-session-v1 未注册即 KeyError，链条首 invocation 暂停。
  外部流的'零行为变化'声明对会话流不成立（batch as 正常、au 失败的差异
  即 original-host profile 重同步前后——实际触发与链型无关，as 的通过
  属侥幸窗口）。修订：.get + 未注册环境回退历史固定天花板，注册环境
  行为不变。另：guarded 现携带内因类型与最深帧（永久可观测性改进）。
  门禁：check_source PASS。行使：批次 ay。

- 注册表回退三部曲完成（goal-ce467e61 第 1 轮，batch ay/bb/bc 诊断链）：
  会话流共有三道注册表门，逐一施以同一回退原则（未注册环境=集成前语义，
  注册环境=注册表绑定）：① store.py 镜像/镜像 seccomp（ap 期）；
  ② tool_plans.py 预算天花板 + profile_sha256（ay/az：NoneType 下标，
  回退取 trusted-X-config 的节点档案 ref sha256）；③ requests.py
  unapproved execution profile（bb）。bc：链条完全复活（6 settled、
  0 paused、emit 确认），仅剩 O8 镜像失配。
- O8 镜像改为 SLOT 派生（bc 失配后）：计划总包络/每角色容器内存与
  cpus 全部从 startup_assets.SLOT 导入计算，外部包络修订不再需要追改
  镜像。行使：批次 bd。

- 观察器寿命派生（goal-ce467e61 第 1 轮，batch bd seeded-3 反例）：
  _watch 硬编码 310s 寿命先于 1800s 预算修订存在；12 invocation 长链
  超出后观察器停止采样，其后全部执行失去 tick 证据（O8 missing）。
  修订：运行器把 LIMITS.seconds+100 作为 observer_seconds 传入，
  观察器寿命随之派生。行使：批次 be。

- be 批次作废与 bf 收口（goal-ce467e61）：be 因容器侧瞬时 SyntaxError
  未运行（目录未创建，复跑导入正常，属一次性环境态）；bf 直跑：
  v5-1 PASS（O8 missing 清零、O7 干净——seal 终采样、SLOT 派生镜像、
  观察器寿命派生全部行使），v5-2 FAIL 仅为 O4 一个工具 + O6 双重 emit
  （修正案既有归类：基线模型行为残留，不计入本工作流失败）。
  与 bd（5/6，含长链 seeded-1/2 的 O8 全绿）合并，O8/O7 验证完成。
  归档工作收口。
