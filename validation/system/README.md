# 外部业务产物验收准备

现有WSL入口：`research/.venvs/mini-swe-agent/bin/python -B validation/system/prepare_artifact_oracles.py <fresh-batch>`。本目录只用于系统的独立验收，不是Runtime或Harness。全新Linux验证环境可按requirements.txt安装固定markdown-it-py/mdurl；不需安装mini-swe-agent业务包，当前仅复用已存在的Python3.10依赖环境。

原件/数学结果/实际CommonMark链接24控制。每批直接核固定解析包72源码文件的版本/hash并保存观察；本轮调用设置全新PYTHONPYCACHEPREFIX且-B，避免读取既有陈旧pyc。SHA/源码快照/所有MIT原声明见dependencies/markdown-001。缺依赖或版本不同须失败，不能回落regex。

输出不证明历史位置授权、物理双域/Pi/provider/事件往返或M通过；那些仍由真实组合driver独立核实。修复前7错误保留artifact-sa01-before-fix-001。
