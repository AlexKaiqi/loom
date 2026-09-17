# V：本系统开发验收入口的准备合同 v1

来源：GOAL §4/§6、governance/evidence-guide §2—§8、USER要求独立证据、防止长任务走偏，以及 P13/P14/P15。V 位于 Runtime 产品之外，是本仓库的有限验收库/命令入口，不是 Runtime done/fail 协议，不是通用评测平台。当前只准备合同、先行用例和可运行验证环境；没有 V 生产实现。

## 责任与信任

受审查且由验收调用者指定的 baseline 定义原要求全集、必须检查、相应证据类型、必须执行批次/用例和当前受验源/数据/环境绑定。submission 是不可信完成声明，只能提供对应批次的证据目录；不能提供命令、Python入口、检查代码、改变标准或删去必须项。

验收调用者另给只读 observers/checkers 注册表。observer 来自独立运行器，按固定 run ID 打开原始执行轨迹或直接观察受控设施，提供实际开始/完成用例、退出、跳过和证据身份。checker 直接读取真实产物/原始设施记录并重算预定断言；不接受应用 success、模型文字、同源日志或 origin 标签本身作为证明。V 负责完整性、关联、版本与失败传播，不负责凭字段名判断某进程确已停止。每个实际 observer/checker 的物理独立性还须在对应组件/系统审查核对。

普通同 UID 可写工作区和摘要绑定不是防篡改隔离。冻结的合同/测试由独立角色审查，当前 V 不声称抵抗可同时重写代码、证据和基线的恶意宿主管理者。

## 窄 Python 接口

`audit(workspace, baseline_path, evidence_root, submission_path, observers, checkers) -> dict`

准备目标模块 `lore_validation.gate`。四个路径由受信调用者提供；base/submission 使用严格 UTF-8 JSON，不许重复 key/NaN/Infinity。输入分别最多 2 MiB；单个原始产物大小由对应固定 checker 限制。错误必须返回 status=FAIL 与非空 failures，或带 code 的 ValidationError（invalid/missing/conflict/version_mismatch/observation_failed/check_failed/path_invalid）；不能把异常变成 PASS。此库不执行 submission 中的任何命令/入口，不联网。

baseline 固定如下结构：schema=`lore-validation-baseline/v1`；requirements_source={path,sha256} 指向原要求数组；requirements={原ID:[checkID,...]} 精确覆盖该数组、不可为空或重复；bindings=[{path,sha256,kind}] 是当前实现/验证脚本/数据/环境的实际文件；runs=[{id,cases:[caseID,...],observer}]；checks=[{id,run_id,level,checker}]。level 为 ANALYZED/MODELED/COMPONENT/INTEGRATION/SYSTEM 之一，不自动继承。每个 check 有且仅有一个声明证据层级和适用批次，不能以 COMPONENT 替代 SYSTEM。纯分析也用明确的审查条目 run，不能用空 cases 绕过执行/阅读事实。

submission 固定 schema=`lore-validation-submission/v1`、baseline_sha256，以及 runs=[{id,evidence_dir}]。必须与 baseline runs 精确一致；每个目录位于 evidence_root 下，不能 abs/.. 或通过符号链接越界。所有 baseline bindings 都相对 workspace、必须是可打开普通文件且实际摘要相等；即使 submission 自报 PASS 也不能略过。源码文件内容保存在版本库或受验快照中，摘要仅核一致性。

`observers[name](run_spec, evidence_dir)` 必须实际调用，并返回 `{run_id,level,started,finished,skipped,exit_code,artifacts}`；started/finished 为用例 ID 数组，与固定 cases 各精确一次，skipped 为空，exit_code 为整数0而非bool，level 与此 run 各 check 的声明一致。artifacts={name:{path,sha256}}；所有文件由 V 直接核存在、ordinary file、受控 evidence_dir 边界及实际摘要。observer 异常/缺项/不可观测直接失败。

`checkers[name](check_spec, observed_run, evidence_dir)` 必须实际调用，返回 `{passed:bool,assertions:[{id,passed:bool}],facts:dict}`；必须有非空唯一断言且全部严格true，facts 数值有限且JSON可表达。V 自行计算check与总status，不信checker外带status。任一错误、unknown/missing case、重复、skip、空断言、非有限数或类型错误均FAIL，不给“有条件通过”。

结果固定包含 status、checks（完整唯一check列表，各项id/passed/assertions/facts）、requirements（与受审基线相同的完整原要求→check映射）、runs（完整run ID→实际observed run字典）、failures、baseline_sha256以及绑定检查；不能做了多个调用却只返回第一个结果。原要求/批次/check/每批case全集均不得为空或含重复身份。正式 G6 入口另以 process exit=0 当且仅当本返回status PASS；程序退出码本身不是产品验收。

## 层次边界与完整覆盖

V 单元用例使用小型固定原要求/独立原始文件 fixture，验证拒绝能力和调用事实，绝不算244原要求的系统PASS。正式 baseline 必须读取 design/requirements-index.json 的244条原文身份，并由独立角色审查 requirement→check 的语义覆盖，机械键集合相等不能替代这项审查。

M 真实任务 checker 使用独立输入核算产物并检查两域/Session/provider/事件事实；X 多策略与规模 checker 在对应先行协议下评价全部固定样本，不能运行后设置阈值或择优。V 不内置这些业务判断，注册函数位于 validation/system。G0/G1/G2资产可作为各自范围的 ANALYZED/MODELED证据，不能转为产品SYSTEM通过。

## 准备与进入实现

V01—V14 先行用例在 cases.json 与 test_gate.py。Python3.10 stdlib、真实 ext4 文件/符号链接、hash/JSON/独立回调可运行，无远程依赖。缺模块必须明确MISSING/exit2/执行0；坏声明与坏实际产物必须被拒。G3准入须独立复读合同和用例，再实施本有限V库。全组件共享契约与正式系统用例准备继续单列，不因V单元就绪自动完成G3。


## VR01—02 独立预审补件

旧合同/用例在Git ee3f85f及独立预审批保留。V01固定两个真实run、三个check与全部调用身份，V02/V05/V11/V12增加非首run产物错误、非首check异常/假断言，拒绝只处理首项的坏遍历。不是降低原门槛。

本V候选限Python标准库与选定Python包内部模块；run_contract在任何目标import前捕获整个包全部.py及摘要，复制至全新batch源码快照，从无pyc快照导入；所有相对helper按原包层次加载。原源码和实际执行快照各自前后核对，任一变化FAIL，保存可重建字节。没有宣称跟踪任意第三方依赖；以后引入包外项目依赖必须先增量绑定并复验。目标不得在代码里另从宿主绝对路径加载自有helper绕过已审包边界。
