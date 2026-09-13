普通工具完整反馈有限增量（先行；不含 Docker/模型调用）

来源：m01-real-001/M01-v5-1 三个真实已确认工具的 X exit_code=1，stdout/stderr原件由 originals.json 固定。旧receipt保持原JSON，不追写字段；ToolService.query从已核原record投影exit_code（整数0..255）和stderr_ref(path/bytes/sha256)，与原result_ref/stdout_ref/publication_ref同行。ToolFacts._result_ref还须核original stopped response的exit_code与X原record一致。

SessionService在工具完整回执中按成对的exit_code+stderr_ref验证原bytes/hash，传原stderr b64/bytes/sha给Node；缺一/未知exit/坏hash或bytes不能成为完整工具反馈。Node验证同一对字段，把原stdout文本保持为第一块；非空stderr原UTF8文本与可见exit code进模型可见content，同时details保存exit_code、stderr(bytes/sha256)及原result_ref/publication_ref。exit0空stderr保留原stdout内容。退出码0同样在末尾显示 `Command exited with code 0`；首stdout块逐字保持，空stderr不加stderr块。这澄清可见退出码义务，并不限制为单一stdout块。显式没有两个字段的旧stdout-only有限fixture可继续，但不得伪造exit0/完整exit证明。

真实外部minimal Harness用Pi公开after_tool event.details.exit_code映射isError=(code!=0)，保留details/content并terminate原一步；不能只给tool.execute result增加isError（Pi原execute会置false）。原Pi hooks和finalization源码引用见root任务指定三文件。探针直接运行实际Node adapter+派生Pi+minimal策略，fixed native provider/tool是纯进程内端口，无HTTP/Engine/真实凭据。

唯一入口 python3 -B validation/tool_feedback/run.py --batch NAME。固定10组：TF01三真实失败query投影与只读；TF02原X stopped错exit拒；TF03实际S callback完整反馈；TF04 exit0/空stderr；TF05 Node/Pi真实错误反馈；TF06 Node/Pi成功与legacy；TF07坏stderr SHA；TF08坏stderr bytes；TF09未知exit；TF10成对字段缺失。旧实现先跑并保存FAIL，判据不随修复放宽。查询端口以只读原Rrow/ref作为明确fixture，不重验真实R/F授权；S callback复用真实旧S018 pending和明确NoEngineX，不冒充该新feedback曾被旧Pi原件保存。实际新Pi反馈在Node入口独立落原JSONL核验。
