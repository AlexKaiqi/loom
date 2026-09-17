# F Python验证接口 v1 草案

本页把contract.md的窄库语义固定为可执行入口；不是模型工具DSL。模块`lore_files`提供`FileStore(control_dir, authorization_checker, reference_checker, checkpoint=None, limits=None)`。当前模块尚未实现。所有request是有限、规范可比较的数据；ID重复完整相同返回原关系，任一绑定差异报CONFLICT。异常`code`是合同大写错误枚举，不把TypeError等程序异常当拒绝。

- `capture(request_id, binding, coordination, base_ref=None)`：从binding真实普通root捕获并root持久版本，返回`{version_ref, archive_path, manifest_path}`。这是不可变版本可查的确认，不是R当前目录已发布。coordination来自可信调用，reference_checker(ref,"coordination")核验；不凭它省略实际FD/监测。capture不编辑源目录。
- `import_archive(request_id, binding, archive_path, source_ref, base_ref, profile)`：验证完整受限archive并封存为同格式结果。source_ref固定X原exec/generation/frozen来源，由reference_checker核验；冻结不是stop。
- `materialize(request_id, version_ref, target_path, authorization, profile="host-v1")`：仅新受控目录；返回`{path,root:{dev,ino},version_ref}`。写前独立验证归档，不跟随symlink；实际集合满足profile，不能降元数据。
- `read_reference(reference, authorization)`：reference含完整version_ref、path原字符串(以os.fsencode可逆)、kind和可选sha256。返回普通文件bytes；symlink不作为普通内容读取。授权错`UNAUTHORIZED`，类型错误`REFERENCE_TYPE`。实际内容损坏`VERSION_CORRUPT`。
- `retain(pin_id, version_ref)` / `release(pin_id, authorization)` / `gc()`：活跃pin保护实际Git root；无权释放拒绝。gc不可删除仍有pin的对象。
- `install(request_id, intent, stopped_ref)`：intent是R已接受原安装意图，至少resource/domain/old binding/staged路径与devino/prepared version/base_ref/execution_id/generation/R intent_ref；reference_checker核验intent与stop。先持久本地原意图，再真实全集合base和观察核对，再单次exchange。返回installation_ref供R查询核对，不更新R库、不释放writer。
- `query_install(request_id)`：返回status、original_intent、current_root、retired_root、version_ref、stopped_ref；枚举`not_installed/installed_pending_confirmation/confirmed/conflicting/unknown`。根据真实布局重建，不把重开等于重装。

binding={resource_id,domain,path,root:{dev,ino},revision,authorization}；profile="host-v1"，version_ref至少={resource_id,domain,git_ref,archive_sha256,manifest_sha256,profile}；git_ref位于control_dir/versions.git内实际commit/ref，读取:archive.tar获得完整归档。manifest是独立可读的实际成员描述，F不能把测试expected作为输入。checker由宿主提供，普通任务无权重建；验证器用有限受信fixturechecker，只证明调用/关联检查。

checkpoint(label,record)仅受信验收注入：`capture_leases_acquired`（含已建立monitor的opaque句柄以及实际lease FDs，只给验收使用）、`before_exchange`、`after_exchange_before_record`、`after_record_before_reply`。可在真实阶段阻断/杀进程，不提前制造成功或合成故障。关闭monitor以测观察丢失仅证明fault传播；真实创建/rename/SIGIO与SIGKILL另有独立用例。

limits含max_entries/max_logical_bytes/max_archive_bytes/window_seconds（默认64/1MiB/2MiB/10s为正式小fixture验证profile，不是产品SLA）。执行时校验内核lease-break-time，无法满足窗口时拒绝。不传工具凭据，不使用网络。

FR05补件：Git commit和返回普通artifact文件须同时含archive.tar与manifest.json；轻量清单固定结构、路径范围/字节/hash/完整成员定义见manifest-contract.md。任何返回路径缺失或双源不一致不得交付；read_reference/materialize必须核两blob摘要与清单声明，不能忽略损坏manifest直接从tar返回成功。


## FG01/FG02 authority-context v1 authoritative local revision

The historical two-argument callback examples above are superseded by [mandatory authority context](authority-context.md) and its exact [schema](authority-context.json). Both authorization_checker and reference_checker require actual operation context as their third argument; no legacy success fallback. Original F01-F19 obligations remain. New independent FS01-FS12 scope cases are required before this local preparation gate is revalidated. Old source/fixture/gate snapshots remain under history/authority-context-001.
