# V 独立准备入口

WSL Linux repo根运行 `python3 -B validation/components/v/run_contract.py --batch NAME --module lore_validation.gate`。批次目录不可复用。缺组件退出2，正式固定14例执行为0且不能PASS。先行用例的callback是独立验收端角色 fixture，仅验证V是否调用原观察者并传播真实文件错误；不是运行中的Runtime替身通过。

实际系统observer/checker需分别经过对应G3/G5/G6审查，不会因V单元绿色自动可信。应用提交内容不能选择observer/checker或给执行代码。所有源/证据仅在WSL的原生工作副本。
