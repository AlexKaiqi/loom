# 修订记录：预算准入规则（budget-admission-001）2026-09-14

## 依据（反例在先）

历史 M01 真实批次（m01-real-003/004/005）中，第六个合法步骤被预检拒绝：

- 005：used 7140 tokens + 第六请求 9886 字节 = 17026 > 15360；
- 004：6196 + 10881 = 17077 > 15360。

旧规则 `used + len(raw) <= max_input_tokens` 把"下一请求的字节数"当作"token 数"预留，
混淆了两种度量。诊断（validation/provider_budget/diagnosis.md）表明仅靠压缩投影文本
无法保证六次请求（第六次预测裕量 −158）。

修复前反例证据：`validation/provider_budget/evidence/admission-001-before/`
（run_kind=BEFORE_FIX_EVIDENCE，PBO-01 以 `budget_exceeded` 复现阻断，源码哈希捕获；
其余 PBO-02..05 保持旧行为）。

## 新规则（预检投影）

- 主体硬上限独立保留：`len(raw) <= max_request_body_bytes`（不变）。
- 准入：`used_total + projected_next <= max_input_tokens`，其中
  `projected_next = tokens_last + max(0, bytes_next − common_prefix_bytes) + 64`；
  无已接收尝试时回退 `projected_next = bytes_next`（原字节预留语义）。
- `tokens_last`、`used_total` 全部来自已归档回执的 normalized `raw_usage`
  （服务器实测值）；最新尝试的归档 `request.body` 经 sha256 摘要校验后才参与
  公共前缀计算；不可读时按 `budget_unknown` 拒绝（保守失败）。
- 响应后的实际用量总检查不变：累计 ACTUAL 输入 token 仍不得超过 15360。

## 健全性论证

1. 服务器分词对相同字节串确定：与最新归档主体相同的字节跨度在上一次请求中
   已经计入 `tokens_last`，不会产生超出该值的新 token。
2. 对任何"每个 token 覆盖非空字节跨度"的分词器，tokens ≤ bytes，故前缀之外的
   每个新/改写字节至多贡献一个 token。
3. 64 token 裕量覆盖：服务器聊天模板对至多 3 条新消息的包装增长、结尾 assistant
   引导、以及跨前缀边界的分词合并。

## 探针与结果

`validation/runtime_provider_budget_probe.py`（PBO-01..06，真实 R + ProviderBridge +
本地 HTTP 服务器，无 Docker、无真实模型、无凭据）：

- admission-001-before：BEFORE_FIX_EVIDENCE，PBO-01 FAIL（budget_exceeded），HTTP 14。
- admission-001：AFTER_FIX_EVIDENCE，PBO-01..06 全部 PASS，HTTP 15，
  PBO-06 记录 recorded_shape_bound=3464（m01-real-005 形状：新规则准入、旧规则阻断）。

回归：runtime_provider_probe（PO01–07）PASS；runtime_provider_race PASS（唯一受理）。

## 影响分析

- 只改变预检准入；请求计数、输出上限、期限、wire 配置文件、响应后总量检查均不变。
- 首请求回退保持原字节预留，PBO-05 固定。
- 旧记录（m01-real-003/004/005 批次、diagnosis.md）全部保留，不覆盖。
