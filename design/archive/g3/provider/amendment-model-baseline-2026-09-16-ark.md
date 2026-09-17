# 修订：验证模型基线切到 ARC plan（ark）+ glm-5.3-flash（2026-09-16）

状态：**准备性探测记录**，不是组件或系统验收结论。用于新任务目录 runtime 的真实模型验证；凭据**不落库**。

## 依据与授权

用户 2026-09-16 指示：实际验证模型用"用户 .env 目录下的 ark"，模型 `glm-5.3-flash`，URL `https://ark.cn-beijing.volces.com/api/plan/v3`。

## 凭据引用（不含值）

- 文件：`~/.env`（仓库外，权限 0644，用户主目录）。
- 变量：`ARC_PLAN_API_KEY`（长度 46）。**值不写入仓库、证据、日志或任务目录**；运行器只从该文件读入进程内存，并把变量名（不是值）记入证据元数据。

## 探测观测（2026-09-16，单次 curl，不含密钥）

- 端点形状：`POST {base}/chat/completions`，`Authorization: Bearer $ARC_PLAN_API_KEY`，OpenAI 兼容 JSON。
- `POST {base}` → 404；`POST {base}/chat/completions` → **200**。
- 请求：`{"model":"glm-5.3-flash","messages":[{"role":"user","content":"reply with the single word pong"}],"max_tokens":16}`
- 响应要点（原字节已在当次会话读取，未落盘）：
  - `choices[0].message.content = ""`，`choices[0].message.reasoning_content = "The user wants me to reply …"`（**reasoning 模型**）
  - `choices[0].finish_reason = "length"`（16 token 被 reasoning 吃掉）
  - `model = "glm-5-3-flash"`（**请求名 `glm-5.3-flash` 与回显名不同**，与既有 `MODEL`/`MODEL_ALIAS` 先例同类）
  - `usage = {completion_tokens:16, prompt_tokens:18, total_tokens:34, completion_tokens_details:{reasoning_tokens:15}}`
  - `id = "021789572533165b3148bc0f12eba71a521be8450222824b56972"`，`object = "chat.completion"`

## 对实现的约束

1. **请求模型名** `glm-5.3-flash`；**回显校验**接受 `glm-5-3-flash`；回显既非请求名也非已知回显名 → 响亮失败（不静默放行）。
2. **`max_tokens` 必须计入 reasoning token**：预算把小请求卡在 length 上，不能把空 `content` 当"模型没说话"。
3. 轮次记录必须保存 `reasoning_content` 与 `usage`（观测域），但**不把 reasoning 当事实**。
4. 不假设该端点支持 function calling / 图像输入：最小 runtime 先用 harness 自己解释的动作约定（JSON action），工具调用协议另立探测后再改。

## 局限

- 单次探测、无固定版本源码核查；未验证并发、限额、超时、错误码族、工具调用、流式。
- 未记录端点的服务端版本或 alias 轮换策略；上述回显名是**当次观测事实**，轮换时须重新探测并新增修订。
- 不构成任何系统性质通过；凭据、端点与模型仅用于本仓库开发验证。
