# Harbor：独立产物验收与失败证据

官方 harbor-framework/harbor 固定提交1b50bd025832d6c69f85a4d91cd8a99eaebc661a，版本0.23.0，Apache-2.0。对应 P14 和外部验证器，不承担本系统的持久调度底座。研究重点是“实际产物”与“执行者声明”分离。

## 权威与调用链

源码 src/harbor/job.py:148 解析任务、创建 trials；trial/single_step.py 驱动 agent、收集产物与 verifier。agents/oracle.py 的 OracleAgent 真实上传 solution 并调用环境执行；即便输出成功，其文本不是奖励权威。trial/trial.py:793 起独立 verifier 环境先清空验证日志、上传已收集产物，再创建 Verifier；独立环境不是复用原 agent 的可写容器。tests/ 的 Docker定义构建 verifier 镜像，不是 environment/ 默认目录。

verifier/verifier.py 执行测试脚本，将 stdout 写 verifier 日志，再读取 reward.json/reward.txt；缺失、非数字/非有限奖励都会报错，解析结果与 trial exception 分开记录。trial 输出目录保留 config/result/exception/agent/verifier/artifacts。任务目录内的 verifier 是我们预定义判据，OracleAgent 仅为不调用模型的固定执行者。

## 实际运行与对照

protocol.json 先登记四个固定问题，再用源码 editable 包真实跑 `harbor run -a oracle -e docker`。同一预置 solver 都打印 SUCCESS 并 exit0；单独镜像/容器的 test.sh 只读收集的 /logs/artifacts/answer.txt、要求42。evidence/artifact-004 原始产物经 assess-evidence.py 再直接读取：

- 正例：answer42→验证器日志 saw=42、reward1；
- 错产物：answer41→saw=41、reward0，solver 仍打印成功；
- 缺奖励：原始产物42仍留存、验证器诊断留存，RewardFileNotFoundError，无成功奖励；
- 非有限奖励：nan 文件及诊断留存，VerifierOutputParseError，无成功奖励。

四次 CLI **均 exit0**；需要读取实际 trial reward/exception，不可单用退出码，也不可把 completed_trials 包含 errored 的统计误解为业务通过。

预登记最后一条误把异常类名写为 RewardFileInvalidError。真实类为 VerifierOutputParseError；assessment.json 明确 `exact_label_match=false`，没有改写旧 protocol 或伪称精确名称匹配。原本要检验的“非有限奖励拒绝、没有成功结果且保留原始证据”满足；名称偏差作为研究驱动缺陷保留，由 G2 独立审查核对，不更改系统标准。

## 失败批次与环境界限

artifact-001 的 task network enum 写成 none，任务未有效选择；artifact-002 改成正式 no-network 后，实际 Docker provider 未启用可选 egress control，拒绝不支持的策略。这两批不能计验证器运行。artifact-003 agent实际执行并保留42/41，但 verifier缺 tests/Dockerfile，trial报 FileNotFoundError；CLI仍0，未计支持。

每次按真实错误修 fixture、登记 protocol amendment、保留旧输入哈希/日志；artifact-004 为成功执行批次。固定 Compose main.network_mode=none，任务 policy public；此设置和 Harbor可选网络策略支持不是同一主张，不声称已验证其 egress enforcement。基础镜像固定 python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea。运行在当前 WSL Linux Docker engine；无模型、真实密钥、遥测、远端上传。

## 可复用模块和不采纳

优先候选：任务/产物/验证器契约、独立环境验收路径、reward解析器、错误与原始证据并存的 TrialResults。下一层可独立构建“产物验证执行器+证据收集器”，让本系统完成由外部验收决定，而不是把 Harbor 整个 benchmark Job 驱动塞入调度底座。

本次固定正常脚本不是对抗安全证明。恶意 agent 篡改挂载、后台子进程、打包路径穿越、证据链与被验版本绑定、验证器权限/可信分发必须另定 G3 契约并独立测试。通用奖励标量不自动覆盖本系统所有性质；系统资源限制、Linux生产部署、真实模型质量仍未验证。不采纳：以奖励平均值替代全部必须条件、仅以 Agent/CLI 成功判断完成、把单个 trial 检测通过当完整系统通过。

identity.json、dependencies.json、source-anchors.json 保存官方源、许可证、Python3.12真实环境及版本。复现先按 setup-002 建隔离环境，再 run-experiment.py 新 batch，随后 assess-evidence.py 指向新批次；所有历史失败继续保留。setup-001 后台安装进程未等待，空日志不算安装成功。
