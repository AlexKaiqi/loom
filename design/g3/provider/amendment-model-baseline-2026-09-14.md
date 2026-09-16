# Provider model 基线修订：gpt-5.6-terra → glm-5.3（2026-09-14）

## 修订内容

原 wire 基线 `gpt-5.6-terra`（原用户 OpenAI 代理）改为 `glm-5.3`（用户 2026-09-14 提供的火山方舟 Agent Plan OpenAI 兼容端点 `https://ark.cn-beijing.volces.com/api/plan/v3`）。本修订只替换 wire 层不透明模型标识字符串；被测性质（请求编码、响应归一化、usage 守恒、finish_reason 约束、function tool 契约）全部不变。

## 依据

- U009 判据（无敏感输入兼容性用例、记录实际请求与返回模型标识、不静默换模型）由 `validation/provider_compatibility/protocol-001.json` 执行，候选为用户 `.env` 中声明的 glm-5.3 / deepseek-v4-flash / kimi-k3，证据在 `evidence-001/compatibility.json`。
- [amendment-001](../../validation/provider_compatibility/amendment-001.json)：三个候选的绑定判据全部通过；minimal 探针的 finish_reason=length 是 16 token 预算被推理消耗的直接证据，不是 wire 不兼容。`deepseek-v4-flash` 回显别名 `deepseek-v4-flash-ga-260731`（与请求 id 不一致，违反响应 model 校验的固定基线要求）；`kimi-k3` 延迟最高。选择 `glm-5.3`：精确回显、最低延迟、最低推理开销。
- [probe_002](../../validation/provider_compatibility/probe_002.py) 在生产预算（max_completion_tokens=2048）下复验：minimal finish=stop，toolcall finish=tool_calls 且 shell 参数 `{target, script}` 合法（`evidence-002/compatibility.json`）。

## 影响与旧值保留

- 旧值 `gpt-5.6-terra` 保留于本文件与 `validation/profiles/openai-proxy.json` 的 history 段；历史证据批次绑定旧哈希，仍只证明其原范围（固定响应传输行为），不迁移为当前基线通过。
- 机械替换（同一不透明字符串）应用于：`lore_provider/request.py`、`lore_session/node/check_public.py`、`design/g3/provider/request-cases.json`、`design/g3/provider/cases.json`、`validation/runtime_assembly_probe.py`、`validation/components/s_provider_bridge/bridge_probe.py`、`validation/session_service/live.py`、`validation/system/m01_run.py`。
- `design/g3/system/contract.md` 的 M01 文本与 `runtime-observer.md` O7 中"真实gpt-5.6-terra"按本修订读作"真实当前基线 glm-5.3"；原文保留于 Git 历史。
- endpoint path 由固定 `/v1` 扩展为可选 `path_prefix`（`lore_provider/transport.py`，缺省 `/v1` 保持既有行为）；`/api/plan/v3` 为本基线路由。历史 G4 session-service 冻结准备协议（含 `/home/USER/...` 凭据路径检查）属旧环境记录，不在新宿主复跑。
