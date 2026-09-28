# 能力边界重构验证 — 2026-09-28

本次将实现权威分为持久工作（Loom）、模型访问（Model Resource Hub）、隔离执行（OnDemand Sandbox）、参考策略（Worksurface）。能力内部的代码、专用依赖、测试和说明一起维护；Loom 用 Git submodule 与 Go module 固定集成版本。Worksurface 保留原 Harness 的 subtree 历史。

## 版本与行为

- Model Resource Hub：`1f2a8e90be0a043c09eaf2a978d020cc2822c797`，Pi 单次调用和静态目录。
- OnDemand Sandbox：`cbb5e0fb20af1b7e2fe0402565afa4f76d9d475d`，提供方、NsJail 执行域、文件交接、CLI 和专用测试。
- Worksurface：`a97e4a983aecf7b79d6e122a0a70a7123df98678`，投影、模板、修复判断、Pi Agent 循环。
- 共享 RPC SDK：Loom `d77e37925df2e31bbddbc20601647a034152e8ab`。依赖走 HTTPS 固定提交。

模型请求先由 Loom 持久化再调用；响应先持久化再交给 driver。Driver 不持有模型密钥，不能通过自报事件完成模型责任。未确认的调用阻止后续调用。修复次数由策略保存为 `policy_state`；宿主执行通用环境限制。沙箱工作目录来自测得的结果，测试使用 `/custom/task` 验证未推断固定路径。创建 Work 与运行策略共享 manifest 类型。

## 本次证据

| 检查 | 结果与范围 |
| --- | --- |
| Loom `go test -race -json ./...` | 101 项通过；覆盖请求与结果保管、未知效果拒绝、跨 worker 大消息、持久化、授权、历史和协议 |
| 模型组件 Python 测试 | 16 项通过；真实 Pi + 受控 HTTP/SSE，单次请求、原生消息、凭据隔离、取消、失联及不重试 |
| Worksurface | 19 项 Python 投影／wire 测试 + 2 项 Node 循环测试通过 |
| Loom 模型／策略组合 | 7 项通过；真实独立进程、Pi 循环、工具结果、继续判断、保管拒绝与未知工具结果 |
| OnDemand Sandbox Go 模块 | 28 项通过，24 项真实服务测试跳过；Go CLI 可构建 |
| 安装后的设计书交付 | 3 项通过；安装副本链接与资产、分篇摘要和冻结来源检查 |
| Docker Linux 实际安装 | 5 项通过；在源码目录外运行 `setup → new → ask`，受控模型只收到一次调用；真实 Python Harness、NsJail、Pi 和持久检查点；升级保留原进程绑定、失败构建不激活、不覆盖无关入口、拒绝错误引擎 |

安装验收首次发现创建 Work 的旧 manifest 定义拒绝 `driver` 字段；改为共用策略 manifest 类型后完整复跑通过。最终安装记录：`/private/var/folders/5c/rc2cpzh94z13t6jk4_qpm3lh0000gn/T/loom-install-validation-qq26hhvs`。仅清理该套验收创建的容器，镜像、日志、原生调用和 Work 文件证据保留。

未完成的范围：没有真实 SSH/OpenSandbox 端点或付费模型验收；未运行独立 Linux 主机的 native 安装（macOS 上该用例按前提拒绝）。Docker 安装通过不替代这些范围。保留 schema-2／loom/1；本次不实现设计书中尚未落地的 schema-3／Temporal 迁移。详见[迁移说明](../capability-migration.md)。
