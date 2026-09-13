# G1 顶层设计与有限模拟独立验收

审查人：long_task_drift。日期：2026-09-13。当前裁定：**G1总门槛PASS，可进入G2定向调研。** 同一决定身份完整关联缺口已按新增预注册/冻结、保留旧模型失败、修复和独立复验闭合；最新全批55正/56负通过。此前原107轨迹证据、撤回拟通过的过程和新增发现保留于下文。全部既定调研、组件独立验证、组合与最终验收继续保留；生产Runtime和完整目标X尚未通过。

## 验收依据与独立性

直接读取原v5及G0原始要求基线、top-level-contracts.md、alternatives-review.md、causal-arguments.md、mechanism-decisions.md、unknowns.md、research-questions.md与冻结三族用例。预注册审查、freeze-001/002及其报告副本先于相应模型实现；freeze-003只固定原案例的完整执行投影，没有修改判据。

已逐文件读取三个模型及全部辅助转移源码、observer.py、run_g1.py、audit.py和frozen_loader.py。模型只接收初态、op+args与显式错误机制；源码没有运行时读取案例、expected、执行清单或按case ID生成答案。普通代码中存在注册的有限策略/场景语义，不把它们宣称为生产通用Loop或完整Session适配。

验收角色与实现角色分离；审查者重新检查来源、源码、原始记录并独立执行。共享同一用户目录不构成恶意防篡改隔离。报告以文件摘要和可复跑证据绑定版本，不以角色名称或作者自述代替证据。

## 独立复跑结果

运行位置：WSL Ubuntu `/path/to/loom`；Python 3.10.12，Linux 5.15.167.4-microsoft-standard-WSL2。运行命令：

```text
python3 -B -m simulations.run_g1 --suites strategy durability boundaries --batch g1-independent-001
python3 -B -m unittest -v simulations.test_observer simulations.test_review_regressions
python3 -B -m unittest -v simulations.test_evidence_audit
```

| 族 | 正向轨迹 | 因果错误对照 | 静态断言 |
|---|---:|---:|---:|
| DUR | 28 | 28 | 121 |
| STR | 3 | 3 | 13 |
| BND（含018附轨迹） | 22 | 23 | 136 |
| 合计 | 53 | 54 | 270 |

全部通过。包含all检查点展开后，正向执行346次断言比较，错误对照354次；每项错误机制至少触发一条其预先登记的相关断言失败，无崩溃或缺观测冒充有效错误对照。14项观察器回归与9项完整入口/证据/源码拒绝控制均通过；预期失败探针保存于新目录，未覆盖先前批次。

独立从三个原始JSON遍历每条主/附轨迹和变异，逐字段比较run ID、检查点、断言ID/时点、因果关联及静态计数，107项与固定execution-inventory完全一致，没有借用runner的trajectories/variants结果作为预期。107份原始记录摘要均核验，且独立复跑记录与g1-001逐字节一致。对DUR的268个检查点，另从环境/接收方/责任记录重推计数、资源实体、确认身份和待处理身份，无报告与记录不符。

证据位置均相对仓库根：

- `simulations/evidence/g1-independent-001/summary.json`及其107份原始轨迹；摘要`056dbc3f34b04e723a879b70d83243311a49e7349090883cf0f2ad6b4d26549e`。其中inputs_sha256与implementation_sha256列出全部本批输入/实现，审查结束时仍一致。
- `simulations/evidence/g1-independent-observer-001/`：14项日志、inventory-projection.json、fact-audit.json及新负控批次索引。
- `simulations/evidence/g1-independent-audit-001/`：9项入口拒绝控制日志与新负控批次索引。
- `design/g1/observer-review.md`：OR-01—04首次缺陷、只读复现、修复与独立闭合裁定。初查/开发不利结果和BND机制表示修订均保留。

## B01—B05逐项裁定

| 检查项 | 裁定 | 直接依据与适用边界 |
|---|---|---|
| B01 职责与权威归属 | PASS | 顶层契约§1—3区分Runtime通用运行责任、Harness投影/反馈/继续、Surface与Workspace文件、既有Session局部原始记录、事件权威与外部实际效果。DUR以接收方、内容、环境和责任记录分别生成观察；BND保留owner与实际写者、应用事件与受控确认的分离。尚未选择生产记录设施。 |
| B02 分层、权限和恢复范围 | PASS | 契约§1/4/6/7给出依赖方向、受控执行、稳定决定及版本恢复范围；MD01—06与alternatives-review记录备选、反例和推翻条件。模型文件按职责拆分，没有以有限Python实现反向冻结生产语言、服务数或产品。 |
| B03 先判据后模拟 | PASS（补充闭合见末节） | 分批冻结对应预注册报告先于实现；本次53正/54负覆盖正常继续/停止、确认与交接切点、事件前中后/通知丢失、执行未知、资源释放、权限/写者/版本/视图边界。完整性清单独立绑定，嵌套附加项实际执行。 |
| B04 核心假设支持与延期安排 | PASS（G1范围） | 条件性因果论证明确持久依据先建立后移交、查询不等重做、真实撤权才接管、完整版本集合才恢复；有限正例说明这些假设下存在一致执行解释，错误解释被拒。直接读取Linux可行性原始观察，确认后续实验入口可用；不把它当隔离证明。Q01—Q08/Q15真实能力、Q09—Q14具体环境/效果/容量/候选要求保留阶段责任；延期不影响本阶段检验抽象自洽和安排G2，却会阻止相关组件通过。 |
| B05 反例与现实差距 | PASS | DF01/DF02、AR-01与OR-01—04均留有问题和修订记录；固定错误机制不是直接改expected。有限模型与真实能力边界明确，见下列证据债务；未以文档完备或单一绿色摘要裁定。 |

## 关键机制与观察来源复核

DUR-007/027分别检验工具结果之后继续与终结，排除结果存在即调用完成；DUR-028在外部候选改变后仍复用已接受d1=A/op2，并拒绝改为B/op3。DUR-009/020要求承诺范围内已确认内容真实可取回，不能以暂停替代恢复；未知执行011/012则保留原身份与责任，禁止盲目重做。等待前/中/后和丢通知由持久事件关系驱动，任务资源计数来自独立实体集合。

BND的原始状态和操作结果保持可审阅：控制owner/错误停止推断不能擦掉真实旧写者；执行写入改变实际对象；版本读取来自绑定集合，恢复引用包含未跟踪依赖。BND-018缺H0分支仅检验不静默换H1的安全反应，已承诺版本丢失仍是总体恢复失败。裁剪原始内容的错误机制改变真实raw值，历史擦除改变真实history槽位，snapshot没有按断言补形状。其先前漏检/INVALID仍保存，不因修复表示而删除。

OR-01—04已在当前入口闭合：缺观测/崩溃不能计为语义错误被检出；数字字符串索引正确；固定清单检出真实漏附轨迹/附机制；落盘轨迹与断言重算检出缺失/篡改；源码按捕获字节编译并核对，预加载与旧pyc无法偷偷改变绑定实现。

## 不被本次通过消除的证据债务

1. G2/G3须实测持久确认的真实故障范围、结果/决定完整身份和内容冲突、跨设施查询与责任交接、回调副作用记录、无旧进程的重建及既有Session适配；不得把模型中的字典持久性和符号内容引用当组件保证。
2. 真实Linux身份、挂载/链接竞态、父子进程与开放FD撤权、网络/资源约束和凭据边界须逐项正反实验。当前可访问Docker报告seccomp unconfined及cgroup v1，只证明实验入口存在；默认配置不能继承为隔离通过。
3. 一致快照、人工/共享写协调、未跟踪依赖、实际跨环境授权取回、保留与引用生命周期须实际验证。文件恢复、事实回放、重做和外部补偿继续分开。
4. 本模型运行预声明的有限确定轨迹，没有穷举任意并发交错或证明无限活性。公平驱动和8轮边界是模拟条件，非延迟SLA；条件缺失或界限耗尽不能计为通过。G2真实机制失败须回到最早受影响契约，不能只修改模型使其好看。
5. 真实多Harness效果比较、固定任务/模型/预算、可写资源和副作用隔离，以及P15容量与成本阈值仍须对应实施前冻结独立契约，正式验证另批进行。本次不选定任何开源产品，不减少12主项目、NATS、Daytona相关实验或身份未定候选的既定责任。

阶段历史：原107轨迹复跑完成后，曾因以下新增发现暂缓G1总体通过；补充闭合记录见末节。系统完整目标与最终独立验收仍未完成。

## 新发现记录：同一决定身份的完整关联冲突（当时OPEN）

报告初稿按当时原冻结范围拟裁G1通过；同时进行的DUR源码复核补出了关键覆盖缺口，故本报告立即撤回总体通过，保留上述已完成证据。定位：simulations/durability_requests.py:92—102；accept_decision重交只比较payload与execution_id，而同一d1改source_result或harness_version不会标记冲突。虽然原已接受记录未被覆盖，这仍不满足top-level-contracts.md draft3 §3/4对稳定身份、内容与输入/策略版本关联的完整冲突边界。原DUR-028只改变分支/执行身份，未能拒绝此路径。

下一步：独立角色先新增cases-durability-supplement.json与单独预注册/清单冻结，保持旧冻结oracle与所有证据不变；再修复模型和补充运行入口，独立复跑补充及受影响原套件。新的完整关联反例未关闭前，不得把本报告作为G1总体PASS。该发现亦作为当前有限案例不能证明任意未覆盖输入的具体证据保留。

## 补充闭合与最新总门槛裁定

**完整关联缺口CLOSED，B01—B05在G1范围均PASS。** 新原始案例DUR-S001/S002及独立补充预注册报告、固定清单由freeze-004先行绑定；旧cases及freeze-001—003不变。修复前正式证据`simulations/evidence/g1-supplement-before-repair-001`已直接读取：两个正例的E3在a3为false而要求true，两个新机制因旧模型不支持保持INVALID，未将它们计为错误对照成功。历史提交e77c162及原始失败保留。

直接复核simulations/durability_requests.py:92—110：既有身份按payload、execution_id、source_result、harness_version完整比较，任一不同显式冲突且返回原记录；一致重交不新增责任。注册的错误机制仅退回原来的两字段比较，未修改expected或按case ID分支。runner/audit的补充family仍使用独立case与run ID，只复用durability模型和相同观察规则；补充清单与原清单一起独立核对。

独立执行：

```text
python3 -B -m simulations.run_g1 --suites strategy durability boundaries durability-supplement --batch g1-independent-002
python3 -B -m unittest -v simulations.test_observer simulations.test_review_regressions simulations.test_evidence_audit
```

最新完整批次为55正/56负、共111份正式运行记录，298条静态断言，正向410次与错误对照418次检查点比较，全部通过。补充2正/2负均已直接读取原始check与trace：同完整元组重交无冲突；两个不同关联各自显式冲突；原R1/h1v1/op2保持且op2只启动一次。两个错误机制都仅因预登记E3(a3) false!=true被检出，未由崩溃或缺字段代替。最新23项入口拒绝控制全部独立复跑通过，记录在`simulations/evidence/g1-independent-controls-002`，新建负控失败目录由summary索引。

全部冻结输入和实现摘要在独立复跑后再次直接核对一致；没有修改冻结oracle或覆盖旧证据。当前证据绑定：

| 文件 | SHA256 |
|---|---|
| simulations/durability.py | 3dedaac84f54484781e199b18992fad550ed9221fec5d9336b74cf8434694843 |
| simulations/durability_requests.py | 41162b8afa709107f9a2a85bbc584ea324787fea7d9644a25c7f2bd529385a71 |
| simulations/run_g1.py | 570c8e57657fd453e78f384ecc42983f596e9b282dffaebd131e5d371841bb73 |
| simulations/audit.py | 1e1d75758a5bd590e283f2c65d6616c14dbc0e507541db26775533cc4bf8704c |
| design/g1/freeze-004.json | 938f8fa0ce0fd0ab7e736f23f884ec30c83344ee47ad5b5bde546793192b9954 |
| simulations/evidence/g1-independent-002/summary.json | dd75dbe698caeb5756e670d3ceaa4ff0d3d58d5b211597335baa6e7d3645b344 |

其余输入/实现的完整摘要在最新summary中。原文列出的真实持久性、完整身份序列化、查询/回调、Linux强制边界、实际版本/保留、Session适配、效果及容量证据债务均保留。G1通过只允许推进既定G2，不能把有限关联比较或本轮完成冒充完整系统目标完成。
