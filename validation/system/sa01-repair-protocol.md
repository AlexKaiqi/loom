# SA01 修复先行协议

原regex误将inline code/fenced code/escaped bracket当实际Markdown链接，独立原失败见design/g3/reviews/system-artifact-oracle-independent-001。先保留原oracle/原17控制，新增这3反例，以及同类缩进代码/HTML注释拒绝；新增reference-style和angle destination两个真实链接正例，防止以收窄合法链接换绿。合计24控制，先在旧oracle实际运行并保存失败，再改解析。

复用现有WSL mini-swe-agent Python3.10环境中markdown-it-py4.2.0与mdurl0.1.2，CommonMark preset真实tokens；只认link_open的href，code/fence/html/image标签不是该链接。所有MIT原件和实际源码闭包见dependencies/markdown-001/manifest.json。可安装requirements.txt重建独立验收环境，不要求mini或其他项目作为产品运行依赖；本轮没有安装/升级包。

原17不删改；新反例与正例先于修复代码。修复后同24控制新批，不自批SA01：本作者从初审转为修复角色，root重新独立复核。输出只证明文件内容与实际Markdown链接，不证明历史授权/可达版本/两域或M闭环。
