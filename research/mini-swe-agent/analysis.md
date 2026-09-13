# mini-swe-agent：简明可替换循环，默认路径不提供持久执行身份

研究问题：P01/P07/P12、H02/H10。固定版本2.4.6、commit04d809ceab9df28f9adaed044884180159172930；身份/许可证/依赖见[identity.json](identity.json)。结论是局部候选研究，不是G2或系统验收。

## 源码事实与状态归属

[DefaultAgent](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/agents/default.py#L91)的run先清空messages，再调用step；step=query→execute_actions。模型返回先进入进程内messages，工具执行完才产生观测；每轮finally调用save，save以Path.write_text普通覆盖JSON。serialize保留messages、模型/环境配置、成本和终止结果；它是轨迹导出，并非执行身份表、事务日志或查询旧执行结果协议。默认run没有从此文件恢复控制点的分支。

[LocalEnvironment](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/environments/local.py)使用真实shell子进程；工具输出首行的完成标记可触发Submitted。该完成约定、默认成本/步数上限属于候选策略，不是lore的任务验收。环境继承调用进程环境，不是隔离器。此次严格白名单环境，并设置MSWEA_GLOBAL_CONFIG_DIR为空实验目录，避免root包导入时dotenv读取用户配置。

外部策略入口是普通Python多态：Model/Environment协议、AgentConfig和query/execute_actions覆写。实际DefaultAgent实现只有约200行，职责容易阅读；代价是持久受理/恢复/授权边界需另外承担。没有必要复制整个项目。

## 实验与独立事实

先写[protocol.json](protocol.json)，再执行[experiment.py](experiment.py)+[worker.py](worker.py)。使用上游DeterministicModel固定回复、真实DefaultAgent和LocalEnvironment；审计子类只记录query调用，策略子类在实际super.execute_actions后抛上游Submitted，不替换循环或工具执行器。

[mechanism-002/run.json](evidence/mechanism-002/run.json)记录：
- 正常：2次query、实际效果文件1行，磁盘JSON包含原始UTF8工具观测和done。
- 外部停止策略：1次query、1次相同实际效果，完整观测保存后由外部策略停止。
- 在首个工具append完成、step未返回时对唯一实验worker发送SIGKILL：退出-9，效果1行、query1行、轨迹文件不存在。新进程重新run产生第2次效果及新增2次query。这是重复执行，不是恢复。
- 观察器从目标文件计数；增加一条未报告效果的副本被拒绝。上游源文件哈希不变。

首批[mechanism-001](evidence/mechanism-001/run.json)因固定完成命令多输出一个末尾换行，正常分支不满足预注册done；失败和原脚本保留，仅修fixture输出，不调整oracle。

## 可复用点、缺口与选择建议

| 候选 | 能支持的局部性质 | 限制/建议 |
|---|---|---|
| Model/Environment协议与小Agent子类 | 策略外置、固定回复测试、可读的局部执行 | 可参考接口/测试方法；不必引入整个框架 |
| DeterministicModel | 无真实模型请求的机制实验 | 不证明模型质量或provider兼容 |
| serialize/保存轨迹 | 正常结束后的记录导出 | 不作为P07权威Session：已实证效果与保存间隙 |
| LocalEnvironment | 简明shell适配 | 不作为权限/沙箱层；不采纳默认完成标记为lore验收 |

若采用其Agent主体，必须另写稳定受理ID+内容/版本关联、结果登记和未知效果处理，会产生新的并行状态权威。与已有Pi/DeepSeek持久Session相比，目前不建议作为lore权威局部Session。该拒绝仅限实测默认路径，不声称项目所有可选Agent/Environment都无恢复。

许可证MIT；只安装实际测试所需jinja2/pydantic/python-dotenv/rich/platformdirs/requests，解析版本在[requirements-resolved.txt](requirements-resolved.txt)，Python3.10.12。没有安装/验证litellm、数据集、可选容器后端或线上benchmark。无机器断电、全量输出截断、安全隔离、长期资源活性证明。

## 原清单补充：双 Shell 与历史/Surface 分工（独立复核后补充的静态分析）

固定源码的 [Environment.execute(action, cwd)](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/__init__.py#L61) 接口允许提供路由适配器，但 [DefaultAgent.execute_actions](https://github.com/SWE-agent/mini-swe-agent/blob/04d809ceab9df28f9adaed044884180159172930/src/minisweagent/agents/default.py#L154) 只有一个 self.env；LocalEnvironment 也只有命令/cwd/env，不含 Surface/Workspace 域、独立权限或授权身份。因此“双 Shell 可通过适配入口接入”是源码可行性判断，域路由、结果绑定与隔离尚未实测；切换 cwd 不提供权限边界。其 messages 同时供模型输入和轨迹序列化，没有独立可编辑 Surface 及不可变 Session 权威的现成分工；文件字节留在环境，serialize 只导出环境配置。若作为参考，历史应保持原始证据并派生投影，Surface 则归 Lore 单独管理；不能把精简/改写 messages 当作原始历史恢复。此段不增加采用承诺，既有默认路径耐久性否定结论不变。
