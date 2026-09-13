# R G3 验收准备独立预审

状态：PRE_REVIEW_FINDINGS_AWAITING_FIXED_REVISION，不批准 G3/G4。审查者负责 S 验收准备，未写 R 合同/代码/用例。根仍在修订，本报告按实质问题提供固定前反馈；没有运行不存在的产品组件。

## 必须关闭的发现

R-D-01：最初读取的 process_cases.py R18-lock 路径只要求子进程非零退出并检查旧表无新行。TypeError、ImportError 或任意崩溃也满足它，构成“代码错误被当预期拒绝”。修复要求是子进程对接受失败输出严格 storage_error 及动作/request_id，父端验证真实独立锁仍持有、该契约错误与持久状态；不接受任意非零。根已告知同轮修复 error_code/error_type，待固定后直接复核，不据口头关闭。

R-D-02：合同§可执行验证补充要求“错 execution/base 但真实存在的 ref”；初始 test_R16 只有合法释放和旧 holder stale，不能拒绝把另一真实执行者停止记录或另一版本当本次释放依据的实现。需独立初态，各有合法正对照，再只改 execution/base；旧 holder 仍存在，控制库不能产生新 writer。reference_checker 需以真实 fixture 文件/hash 判有效，再依据当前预期关联核验，不是一律拒绝。

R-D-03：初始 test_R14 只有同 condition_ref、同 event、同 successor 的重复正路径，没有改 condition code/version、同匹配身份不同 successor/ref 的独立反例。忽略这些关联的实现也会绿。需已登记旧等待和原条件/参数保持，再分别改变已存在条件 ref 或同匹配身份内容，拒绝冲突、不重复后继；实际正常重交仍应成功。不要用第一次 conflict 状态掩盖第二路径。

## 固定前建议与范围提醒

- R06 标称“新调用用新策略”，初始代码只验证旧调用 h1 不变，随后移动/注销，缺 h2 新调用正例及调用自由填写未登记 h1/h2 版本的错误对照。建议在 rebind 后实际受理新 ID，核原库关联。
- R03 的过深判断使用 40 层 fixture，但合同未给明确 configurable depth/默认阈值及恰好边界。既然它是控制记录资源限制，应像字节上限明确编码层数定义和边界，避免实现者猜测。
- R12 当前 before/after handoff commit 两切点验证原 DB，能检验两端持久结果；它单独不能检出错误实现中“旧责任先在事务一结清、事务二才建后继”的中间空档。冻结实现的事务边界必须独立源审；若已注册 known-bad 非原子变异，确保实际切点能命中该空档而非只观察两端，避免仅测试 responsibility 函数拒绝人工空对象。
- reference authority 是有原 fixture 文件/hash 的窄依赖替身，只说明 R 是否问对 purpose/关联，不认证真实 X 停止/F发布/S回答。G5 真实桥证据仍必须。
- 当前 exact error helper 不把 TypeError 当业务拒绝，missing module 测试不会 skip；独立 SQLite 原表和真实目录对象观察方向符合用户的独立证据要求。现阶段不对未实现的 R 运行时性质裁定。

## 关闭记录

等待根提供固定 R 草案后直接检查 diff、实际准备负控/异常输出和新增关联用例。旧发现保留；关闭只说明用例/契约可验，不能自称真实组件已通过。

当前复核输入摘要（工作草案可能继续更新）：
- design/g3/r/contract.md SHA256 b4156c20d5a7afe0f1af488137d7c9e1a7474995095af4763888d44194b02b8a
- design/g3/r/cases.json SHA256 fc7acfd00c3ce9435fdcc01311ecd8d63dfc7e31edd6da73832ba701749463e6
- validation/components/r/test_control.py SHA256 8a208173e2a23b34d9d426f8039a86d07b93b09a5b829065c17d210ec12afb72
- validation/components/r/process_cases.py SHA256 f760f47f38e472c5e9b8d31b44476e8c27aad25291e0107930118703c8c1fb0f
- validation/components/r/process_worker.py SHA256 335ce93d56e144a12c9225011de1e36f76f700f4df7bde69ef57d2c55d3ab2f0
- validation/components/r/oracle.py SHA256 e14c00b076f6a7b63c829895d2ac0239a2b96500de38717c702a3bce18f0deae
