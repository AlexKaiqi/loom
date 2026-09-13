# G1 验收器与运行入口独立审查

角色：long_task_drift；独立于验收器、runner和STR实现者。范围仅为冻结用例的发现、执行/观察分离、断言与错误对照完整性、证据版本归属；不据此宣称G1整体或真实Runtime性质通过。

## 初查裁定：REQUIRES_FIXES

审读源码为提交8ff0f6c保留的初版。发现OR-01—OR-04；前三项已用WSL Python只读/内存探针重现，其中输出截获在内存，不生成或覆盖模拟证据。模型作者已接收修复意见，当前还未审到修订，因此不得由本报告判为验收器通过。

| 文件 | 初查 SHA256 |
|---|---|
| simulations/observer.py | 1b4ed2cbefd0300cefbe9ea47b8d10cb4fbc91699365975c058dc11b4f180e15 |
| simulations/run_g1.py | 376718b2bf2728e6edb6d2a2de8e7c942d03bd8ff164bc976db20d572dc44666 |
| simulations/strategy.py | df403bbea111fab5f6de6a52bf7790c389e78ba837cd4d0d5a87296d7c9e1323 |

### OR-01：缺失观测误算为语义错误被检出（OPEN）

定位：observer.py:65—70，run_g1.py:54—58。evaluate把缺字段转成passed=false；run_one只按失败与相关断言ID判断killed，未区分证据无效与真实值违反契约。内存探针初态proof=1，变异仅删proof，断言E1要求proof=1；实际返回status=PASS、mutation_rejected=true，同时唯一check含missing_observation。故一个不提供必要证据的模型可冒充成功的错误对照。

修复判据：缺字段/缺检查点/缺轨迹必须成为无效证据，不能贡献semantic killed；真实值不符仍可作为因果错误对照。直接调用run_one的删除字段探针必须失败，不能只测比较函数。

### OR-02：冻结BND数字字符串索引被错误拒绝（OPEN）

定位：observer.py:33—36；例如冻结BND-014的records/history/"0"、BND-011的rejected_edits/"0"。冻结路径以字符串段数组表示数字下标，resolve只接受int，故对history=["accepted"]解析["history","0"]产生KeyError。正确模型也会因观察器路径不兼容被拒。

修复判据：按冻结路径定义安全解释列表数字段，保留越界/非法段错误；不得修改冻结expected，也不得把缺路径默认成空或null。

### OR-03：预期执行清单随实际枚举一起漏项（OPEN）

定位：run_g1.py:80、95—103。初始validate_inventory两参数来自同一cases；expected_runs在实际循环里同步追加，不能发现枚举器漏附加项。内存按同一控制流程省略018附轨迹与005额外机制后，21正/21负的两张同步清单仍通过validate_inventory；冻结BND应为22正/23负。正常trajectories/variants目前确实包含两项，缺陷是验收层不能发现这一类退化。

修复判据：从冻结原始输入独立建立完整案例、附轨迹、机制、断言清单，并对照实际发出、落盘、重读后观测；不可从实际循环回填“预期”。须以真实枚举器漏附轨迹/附机制的负控检出，不仅测试validate_inventory本身。BND主134与附2条断言均不可遗漏。

### OR-04：源码摘要晚于模型导入，不能严格对应实际执行版本（OPEN）

定位：run_g1.py:84、86—88及105—106。先导入模型再保存磁盘源码摘要；导入后、摘要前若发生修改，内存旧实现可被标为磁盘新版本，前后磁盘摘要仍一致。预加载sys.modules亦可能保留旧实现。本项为静态可达路径分析，未修改他人源码制造现场。

修复判据：在加载前确定本批所需实现/依赖的源码绑定，加载前后核验；实际加载须对应所绑源码，并处理预加载/字节码缓存导致的版本差距。无需声称抵御恶意同权限篡改，但不能把磁盘当前版本直接等同已加载实现。

## 已直接确认的边界

- freeze-001与freeze-002输入摘要均匹配；runner执行前与结束前会核验冻结输入，并禁止覆盖同名证据目录。报告追加与冻结报告副本已正确分离。
- execute只把初态、操作、参数与显式错误机制传给模型，不把expected或case ID传入。STR直接读取预声明外部决定/输出完整性/预算输入，源码没有读取预期或案例文件，没有按case ID返回答案。后续DUR/BND源码另行审查，不由此推导。
- 模型apply抛异常时run_one保留FAIL与异常信息，初版明确没有将崩溃本身算作killed；OR-01属于另一条缺观测路径。
- 初版比较器区分JSON类型并拒绝未知比较器，缺检查点抛协议错误。all检查点逐状态比较；但缺观测分类和端到端清单仍须上述修复。
- 有限模型的环境事实仍是显式fixture；当前审查不证明Linux实际隔离、真实撤权、持久存储或模型效果。

## 修订复核

待实现者保存修复、失败负控及新证据后追加；保留本节之前的原缺陷、定位与摘要。验收器通过仍不替代全部模型独立复跑及G1总门槛。

### OR-01表示边界补充：真实删除与缺观测

在本批冻结路径比较协议下，合法反例也可能删除被断言路径而被判INVALID；这不意味着现实记录删除不是语义错误。允许把同一错误机制实现为实际状态的tombstone：例如把原history[0]内容写为None后追加回退记录，或把raw[R1]实际写为None/裁剪后内容。它们仍丢失已确认历史或原始日志，符合rollback_erases_history/trim_deletes_raw的核心错误语义；不是修正或放宽expected。

必要条件：tombstone须由变异转移写入被模拟的事实状态，snapshot直接复制该状态；不得在观察层按expected补槽、补键或将任意缺字段自动转为None。首次清空列表/删除键所产生的INVALID结果仍须保留，并记录机制表示修订。严格缺路径拒绝作为本批协议保留；真正值为None与无法提供该路径的证据不可混为一类。本补充仅裁定表示是否符合原错误机制，未审运行通过。

## 修订复核裁定：OR-01—OR-04 CLOSED（G1验收入口范围）

已从源代码、冻结原始案例、固定执行清单与原始落盘轨迹独立复核，不以实现者的绿色摘要代替。原初查与失败保留；修复前四项回归失败位于`simulations/evidence/review-regressions-001`，对应历史提交e7e4829。当前正式复跑版本记录于`simulations/evidence/g1-independent-001/summary.json`，不会覆盖g1-001。

- OR-01：observer.py:68—69对缺字段抛ProtocolError；run_g1.py:65—68保留FAIL与可得部分轨迹；audit.py:41—42拒绝模型/观测错误。独立复跑删除观测字段与模型崩溃控制均被拒，不能成为semantic killed。
- OR-02：observer.py:33—34支持冻结路径中的数字字符串列表索引，缺字段/越界仍拒绝。历史数组索引回归及全部BND轨迹通过，无冻结预期改动。
- OR-03：execution-inventory.json由原始冻结案例固定投影，并由freeze-003绑定；运行时不再从当前枚举循环创建验收清单。audit.py:30—58核对运行身份、原始文件摘要、检查点、每次断言、重算结果与因果失败。独立逐字段重建107项清单，包含BND附轨迹与额外机制，完全一致；实际猴补枚举器漏两类附加项都被拒。缺文件/检查点/断言、改变原始观测且同步改报告摘要亦被拒。
- OR-04：run_g1.py:92—101先确定源码摘要，frozen_loader.py:12—37捕获源码字节并由这些字节编译，包含延迟导入依赖；拒绝已加载模型与未捕获的新模型依赖，加载后/运行后核对版本。独立复跑意外预加载、捕获后源码变化、同mtime/size旧pyc控制，均得到正确拒绝或执行捕获源码结果。

独立验证记录：`simulations/evidence/g1-independent-observer-001`含14项回归日志、独立inventory-projection.json与fact-audit.json；`simulations/evidence/g1-independent-audit-001`含9项端到端拒绝控制日志及新建失败探针目录索引。23项全部通过其预声明判据；失败探针是应被拒的负控，不是正式模型失败。

BND机制表示修订已直接读代码与development/boundaries-001..005诊断：parent_exit错误只改变控制推断，实际子写能力保留；人工冲突错误绕过提交保护但记录真实提议；历史擦除实际写入None槽位；裁剪错误实际用裁剪内容覆盖raw。snapshot仅deepcopy真实状态，没有按expected补槽或生成假观察。历史INVALID/漏检诊断仍在；未放宽冻结oracle。

| 当前审查文件 | SHA256 |
|---|---|
| simulations/observer.py | d7db14702bb72383a22eac4f430f393239cfcb713717f93b68e1acf04ba9bec0 |
| simulations/run_g1.py | 4e0082f74c8810dd796bdf27f535a756baa6b36ff2258ab9965c9662bc7e3ad5 |
| simulations/audit.py | 6c1ab0b41a79d7ca960c98f85704ab74a3769a5c059bef151f01d175f862f50b |
| simulations/frozen_loader.py | 90ae04d4db3e06857fe8f18541d69caca9464a126895def9616905b4abfba32c |
| design/g1/execution-inventory.json | 104cf2204ad73ae8e18405001986d50a942af81b3ee3aa87a0759593ed3e70ac |
| simulations/evidence/g1-independent-001/summary.json | 056dbc3f34b04e723a879b70d83243311a49e7349090883cf0f2ad6b4d26549e |

此处CLOSED只覆盖登记反例与当前验收入口：同用户可写目录不构成恶意防篡改隔离，未检查的任意状态也不由有限案例自动获得证明。完整G1裁定见independent-model-review.md。

## 补充family后的入口回归

补充决定关联案例由独立freeze-004和execution-inventory-supplement绑定。新增family保留自己的case/run身份和oracle文件，实际模型字节复用durability；audit将补充固定清单合并核对，没有从执行循环缩小预期。此次runner/audit源码发生变化后，审查者重新运行全部111项及23项拒绝控制，均满足预定判据；OR-01—04继续CLOSED。最新证据为g1-independent-002与g1-independent-controls-002，完整hash见independent-model-review.md末节及运行summary。旧107项通过与四项初始缺陷、BND表示修订和决定关联修复前失败仍保留。
