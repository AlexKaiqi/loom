# 策略与模型组合验证

`python -m unittest discover -s tests/model -v` 使用真实 Worksurface Pi 循环、独立单次模型 worker 和受控 HTTP/SSE，检查请求／结果保管顺序、工具未知状态、截断、继续判断与凭据隔离。需要初始化 submodule，并按根开发说明安装 Node 24 与 Python 依赖。

单次模型和目录测试由 Model Service 维护；投影和循环策略测试由 Worksurface 维护。此目录的 RPC peer、HTTP fixture 仅供组合验证，不能替代 Loom 的持久化或真实 Linux／付费供应商验收。
