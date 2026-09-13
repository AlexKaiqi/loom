# S 上下文补件004：主动检索与有用裁剪

状态：READY_FOR_INDEPENDENT_REVIEW，非G3/G4通过。根与244覆盖预审指出V5-B060缺明确大目录/长diff场景，以及S020只核裁剪标签但没有有用片段/范围断言。旧稳定26例/109断言和当时27份直接源/索引完整保存在history/before-retrieval-004/manifest.json；旧准备证据未删改。

先写context-supplement-004.json及新预期，后写fixture、共享driver与oracle。当前27例/150断言；新增S027的33条断言和S020的8条断言全部UNVERIFIED。

S027素材有64目录×8普通文件和4096行diff正文，真实素材总文件513（含diff）、578子对象。初始规范provider payload不超过32768字节，必要目标/笔记/事件/反馈/真实workspace路径必须有；未选树名、未选文件正文、未选diff正文及尚未取得的目标片段不得预展开。固定provider发出一个普通Python glob/read/hash命令，它实际查找/读取文件与diff，不把片段写死在命令里。原stdout的完整片段及input_ref/path/bytes/sha256来源描述必须保留到Pi native toolResult和下一provider，借原input_ref定位全文件和全diff。Runtime不得硬编码忽略目录；这些是有限默认外部Harness策略。系统实物/真实授权仍由G5验证。

S020原log改为有意义首尾加有界中部；前78字节与后44字节、73850总字节、精确UTF8半开范围先行固定。参考外部Harness用普通JSON文本context块标明实际fragments/ranges/clipped/owner/read_path/source_ref/hash/bytes；oracle从真实provider payload读取这些字段，与完整原始bytes及真实F源引用比较。其他Harness无需同算法/格式。F仅提供原引用和可读位置，不计算裁剪或预塞检索答案；F负责人已确认符合原F read_reference/version_ref接口，无新增F产品API。UNKNOWN_EXEC17仍只是S上下文输入，不能冒充R真实未决责任或不重复效果。

## 准备证据与边界

- validation/components/s/evidence/context-preparation-001：真实Linux临时普通文件和普通Python命令成功取得唯一目标文件、指定diff行及原hash/bytes/input_ref；保存所有513文件、material-manifest、原脚本/命令/stdout/stderr。这个命令没有运行S/X/F，不证明隔离或组合能力。
- 同批显式oracle校准：紧凑必要输入、完整原生tool反馈、精确有用clip正控制；大树全展开、全diff、全文文件、隐藏目标、丢来源、空片段、错范围、错hash均得到预期FAIL。缺source ref与缺原件为INVALID，不称负控被杀。14项包含1项真实普通fixture命令及13项明确校准，均成立。校准provider记录是人工测试样本，不贴成实际S产物。
- oracle-context-001：原9项校准回归成立，包括真实旧Pi accepted字节、坏原assistant、缺/坏源和空跑。
- live-driver-context-001：全部27例动作发现及实际driver入口已运行，collector因真实S/X/F配置缺失MISSING exit2；runner INVALID exit2，未产生真实S通过。语法及动作词表/27例150断言数量已核对。

新增共享实现仅为context_fixtures.py、context-selftest.py及collector/action/oracle的小型准备分支。正式driver不接收断言；原来源与实际输出独立读取，S只见普通调用。当前case/default JSON context格式、工具输出保留规则及F测试包装需独立审查后冻结，不能在G4为迎合产品改变预期。
