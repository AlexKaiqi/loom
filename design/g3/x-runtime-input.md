# 普通 Runtime Shell 的单个授权只读输入

来源：v5 §5.1、§5.2、§6.2；system/artifact-oracle-contract.md 的当次环境可解析历史要求。只补现 schema1 Shell 没有 /input 的能力，不解释 report/history 名称，不改模型工具参数、Engine、ToolPlans 或 Surface/Workspace 原业务版本。

API：schema1 execute 可选 `readonly_mounts:[mount]`，唯一 role=input、target=/input、read_only=true。mount 完全沿现 Node F-view schema，来源为真实 F 固定版本物化目录、完整原 manifest/ref/tree 与 root dev/ino。只有 domain=runtime 且原 NodeProfile、完整已登记 grant、同 namespace/role 的 slot、readonly-view 登记成立时允许；所有 mount 内容进入原完整 request_digest，同 ID 不可换版本。无字段保持旧默认。带新字段的 prepare_restore 暂明确拒绝，不 silently drop mount，不声称新 restore 能力。

复用：NodeProfile 原注册范围/完整 F 树与 hash/metadata/符号链接不逃逸/控制目录不重叠检查；ExecutionStore 既有 checked.readonly_mounts→Docker readonly bind。/work 仍只导入完整原 writable base、只导出该 volume，不注入/剥离历史文件。可信宿主生成目录生命周期是假设；不把原 Node prepare 单次检查说成防任意宿主并发改写。

先行三组，不改变既有 Node/schema1 标准：
- RI01：真实 F 旧版 `report.json` 内容 `{"sum":10}`，源工作目录随后同名改为999；合法 runtime mount 在创建前保留精确旧 fullref/完整字节，物理 Shell 必须读10，写/input失败。旧无字段物理环境访问/input失败。NoEngine只验证准备与旧副本，不算物理读取通过。
- RI02：错 namespace、错 F fullversion/hash/根 inode或原件篡改、task域、无profile/grant/slot、改目标或RW均拒绝；每种异常必须明确 ExecutionError，不以普通代码错误为检出。真实创建边界/Engine调用必须0，完整合法正控存在。
- RI03：创建前原/archive完整成员仍是/work原base；真实工具新增notes后，checkpoint与F发布完整保留其原base+notes，/input不成为archive成员，源历史不改。同原ID改mount冲突，query不重复执行；真实stop/release照原X事实。NoEngine只覆盖archive与digest分离，其余保持待物理验证。

固定范围沿普通X预算与原Node readonly边界（最多8192成员、单文件最多256MiB及固定完整F manifest）；本fixture仅两个历史成员、小普通base。无网络/密钥/新FD/任意宿主路径。NoEngine实际F+X准备检查可运行；物理运行须独占Docker窗口，不能由NoEngine或测试拦截返回值自证。

入口：`python3 -B validation/runtime_input_mount/run.py --batch NAME`；缺方法/模块结果MISSING/exit4，错误候选FAIL/exit1，NoEngine通过仅NOENGINE_PASS。原源码与失败保留在before-source和evidence，不修改旧预期。
