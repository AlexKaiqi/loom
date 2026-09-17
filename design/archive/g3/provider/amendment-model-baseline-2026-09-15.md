# Provider model 基线修订：glm-5.3 → deepseek-v4-flash（2026-09-15）

## 修订内容

wire 基线 `glm-5.3` 改为 `deepseek-v4-flash`（同一用户火山方舟 Agent Plan 端点 `https://ark.cn-beijing.volces.com/api/plan/v3`），用户 2026-09-15 授权（"可以，基线切换也允许"）。与 2026-09-14 修订不同，本次含一处产品行为变更：响应 model 校验从单一精确匹配改为"精确基线 id 或钉定的日期别名"二元匹配。

## 依据

- 模态前提（M07 computer-use）：[protocol-002](../../validation/provider_compatibility/protocol-002.json)（[evidence-003](../../validation/provider_compatibility/evidence-003/record.json) 首跑、[evidence-004](../../validation/provider_compatibility/evidence-004/record.json) 含逐字错误体重跑，两跑一致）：`glm-5.3` 对 OpenAI image_url content part 返回 HTTP 400 `InvalidParameter: "Model only support text input"`；`deepseek-v4-flash` 与 `kimi-k3` 接受（HTTP 200/stop，usage 守恒）。
- 生产形状门禁（切换前必须）：[protocol-003](../../validation/provider_compatibility/protocol-003.json)——protocol-001/002 从未发送 `reasoning_effort` 与 `parallel_tool_calls`，不验证不得切换。[probe_004](../../validation/provider_compatibility/evidence-005/record.json)（切换前，production_text=stop、production_toolcall=tool_calls 且 shell 参数合法）与 [probe_005](../../validation/provider_compatibility/evidence-006/record.json)（切换后，真实 `encode_request` 字节含 system 消息，200/stop）全部通过。
- 选择 deepseek-v4-flash 而非 kimi-k3：protocol-001 证据中延迟更低（3.92s vs 7.61s）、toolcall 探针推理开销更低（50 vs 37 tokens）。
- [amendment-002](../../validation/provider_compatibility/amendment-002.json)：探针层判据修订（回显规则、选择覆写理由）。

## 回显规则与别名事实

端点对该模型固定回显日期别名 `deepseek-v4-flash-ga-260731`（protocol-001/002/003 四次运行一致）。`lore_provider/request.py` 新增 `MODEL_ALIAS` 常量钉定该观测事实；`lore_provider/response.py` 的 `model_mismatch` 校验接受 `MODEL` 或 `MODEL_ALIAS`。别名轮换会在此处响亮失败，须以新修订更新常量——这是有意设计，不做前缀猜测式放行。

## 影响与旧值保留

- 产品文件（发布清单同步更新）：`lore_provider/request.py`（MODEL/MODEL_ALIAS 及注释）、`lore_provider/response.py`（回显规则、usage 注释）、`lore_session/node/check_public.py`（公开描述符 id）。
- 机械替换（同一不透明字符串）：`design/g3/provider/request-cases.json`（9）、`design/g3/provider/cases.json`（7，期望归一化消息的 model 字段）、`validation/runtime_assembly_probe.py`（3）、`validation/components/s_provider_bridge/bridge_probe.py`（2）、`validation/components/s_wire_pi/bridge_probe.py`（1）、`validation/runtime_provider_budget_probe.py`（2）、`validation/runtime_security/fixtures.py`（1）、`validation/components/provider/check_host_transport.py`（2）、`validation/session_service/live.py`（2，沿用 2026-09-14 先例；该冻结协议仍属旧环境记录，不在新宿主复跑）。
- **保持绑定批次 z（不替换）**：`validation/system/m01_run.py` 与 `validation/system/runtime_observer.py` O7 是 M01 整批通过（m01-real-2026-09-14z，真实 glm-5.3）的仪器对；其证据只证明原范围。新基线的真实模型批次须定义自己的观测协议，不得静默复用 O7。
- `validation/profiles/openai-proxy.json`：provider_model 切换，history 追加 glm-5.3 段；credential_file 路径沿用现状（文件名为历史命名，凭据在仓库外受限目录，未变动）。
- **fixture 缺口（如实记录）**：本工作副本从未发布 `design/g3/provider/fixtures/`（PW01–PW24/PQ01–PQ09 原始字节），`run_contract.py` 的 33 例组件套件在本副本不可运行。旧 fixture 原始字节内含的模型串需在持有 fixture 的环境中按新基线重新生成后整批复跑；在此之前不宣称组件套件对新基线通过。
- 本地替代验证：[alias-echo-cases.json](alias-echo-cases.json)（3 例离线：精确回显/别名回显/旧基线串拒收）+ [baseline_offline_check.py](../../validation/components/provider/baseline_offline_check.py)（含生产编码字段集与 evidence-006 逐字节复现），证据 `validation/components/provider/evidence/baseline-offline-001/`，全部通过。

## 验证汇总

1. protocol-002（模态矩阵）：evidence-003/-004 一致。
2. protocol-003（生产形状门禁）：evidence-005（切换前）+ evidence-006（切换后真实字节）。
3. baseline-offline-001（别名规则 + 编码复现）：PASS。
4. runtime_provider_budget_probe（PO01–07）与 runtime_provider_race：基线切换后复跑（见验证状态页）。
5. simulations 单测与 check_source.py（含更新后的发布清单）：通过（见验证状态页）。
