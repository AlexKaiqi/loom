# M/X 实际产物的独立判据

状态：先行验证器合同。来源v5§6.5—6.6/P13及已写M01/X02；不是Runtime接口。数据/报告/notes是普通文件，不将此业务判断放入Runtime。

验收调用者提供从原输入和F历史版本解析后的三个真实普通文件，以及本次模型已知的报告可访问位置。输入是最多4096个JSON整数，绝对值≤1000000；禁止bool/float/NaN/重复key。报告是普通report.json对象，sum必须JSON整数且等于独立读取原输入的数学总和；其他字段不作为正确性证明。notes.md必须有实际Markdown链接，其目标精确是本次已授权报告位置；纯文字“完成”或错误同名文件不是引用。输入、报告、notes各64KiB上限。实际字节摘要与所有尺寸保存，不信报告自报PASS或自带输入hash。

历史版本/路径授权、notes出现的链接在当次环境能解析到该版本、真实两域工具、原Pi/provider、事件往返由组合driver另外直接检查。单独sum_files通过只证明所给真实文件的业务内容和链接相符，不能冒充整个M闭环。受信调用者不能把应用给的任意host路径直接交给此函数；先通过F和固定observer解析。

准备控制：原[2,3,5]→10，独立seed输入及负数/空输入；错误报告、假PASS、错误notes、整数类型错误、实际原输入变化、缺文件/超限/JSON不完整均必须拒绝。用例/正常期望先于对应产品实现保留。后续实际系统driver的所有样本与路径身份由冻结M/X协议提供，不由产物选择。

## SA01 实际链接修复

链接由固定markdown-it-py4.2.0/mdurl0.1.2的CommonMark token解析，检查实际inline link_open的href与获准位置严格相同。行内code、围栏/缩进code、转义文字、HTML注释及image alt内文字不充当链接；引用式与angle destination等合法CommonMark链接保持支持。不把regex文字匹配说成渲染链接，也不把结果推广为HTML浏览器/历史权限可达性验证。既有64KiB原件预算和数学判据不变。

依赖为现有WSL隔离Python3.10环境，版本/实际72个源码文件/3份MIT原许可（包括上游markdown-it与mdurl的Joyent/Node声明）见validation/system/dependencies/markdown-001/manifest.json；requirements.txt给出可重建固定依赖。它们只属于外部验收工具，不进入Runtime或V核心。原17控制与SA01新增7控制/修复前失败原样保留，最终修订由root独立核验，本修复作者不自批。
