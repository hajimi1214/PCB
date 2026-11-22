# PCB

**让 Codex 根据原理图，在嘉立创 EDA 专业版中设计和检查 PCB。** 首个验证目标是 **4 层 MCU 控制板**。

当前版本 **0.4.0**：资料库有92条公开来源，PCB MCP提供24个工具，另有项目隔离的 Windows-MCP 界面控制。插件能读取 JLCEDA 原生网表和全部 ratline，并提供有限绘板、原生自动布线和有 DRC/飞线门槛的 Gerber、BOM、贴片坐标导出。测试副本在 JLCEDA Pro 网页版4.1.105完成141项DRC、0个问题；Gerber对话框报告生成成功，但浏览器保存位置尚未完成，ZIP层与钻孔检查未验收。此前原生自动布线 job 停在1%后取消。当前仍无已验收、可下单的4层MCU成品。

2026-11-22 完成 RP2040 Minimal、Adafruit Feather STM32F405 和 HackRF One 三份开源案例的外观指标提取与独立布局任务书。真实 EDA 试验只将 RP2040 空白目标板推进到程序化圆角板框，两个目标都因未导入原理图器件而有 1 条 Netlist Error；Feather 与 HackRF 的工程导入未获 EDA 确认。尚无一块完整 PCB 通过布线、DRC 和制造验收。逐板任务与失败证据保存在测试环境的 local/board-challenges/analysis/test-run-2026-11-22.json。

已有用户`.epro2`归档用于离线结构学习，原文件保留。实际绘板工具需要EDA保存的本地`.eprj2`或完整`.eprj3`工程；插件会复制工程并只在副本操作。资料库是持久可检索的参考，未进行模型权重训练。

## 从这里开始

- [知识索引](wiki/index.md)：专业版工作流、连接映射、多层叠层/回流、供电/去耦、布线与制造验证。
- [EDA 接口研究](research/eda/findings.md)：官方原生 CLI/MCP、网关备用方案、版本/单位差异和 API 边界。
- [多层板与制造研究](research/rules/findings.md)：JLCPCB、TI、ADI 一手资料及条件化设计规则。
- [开源硬件与工具案例](research/cases/findings.md)：实际读取 PCB/原理图，比较适用范围和许可。
- [设计案例指南](docs/field-guide.md) · [接入架构](docs/architecture.md) · [实现路线](docs/roadmap.md) · [首板输入表](templates/board-intake.md)。

## Codex 技能

项目根目录就是插件包，主要文件是 [.codex-plugin/plugin.json](.codex-plugin/plugin.json)、[本地 MCP 声明](.mcp.json) 和 [插件目录清单](.agents/plugins/marketplace.json)。Codex 技能入口为 [.agents/skills/pcb/SKILL.md](.agents/skills/pcb/SKILL.md)。

首次使用需在 Codex 中信任此项目，并重新启动 Codex 或开始新会话，使桌面客户端读取项目插件。PCB分析需要本机 `python`，Windows-MCP界面控制需本机Windows与项目隔离的Python 3.14环境，真实EDA读写需已运行的嘉立创EDA专业版。当前会话工具清单不会热加载。STDIO MCP启动本机进程，只对你信任的本地项目启用。项目配置没有修改用户全局设置。

在本项目中可提出例如：

> 使用 PCB 技能，依据资料库检查这份原理图做四层 MCU 板需要哪些约束，列出证据和缺项。

知识与归档工具：`pcb_search`、`pcb_sources`、`pcb_case_search`、`pcb_inspect_local_project`、`pcb_query_board`。运行时观察：`pcb_eda_status`、`pcb_eda_sessions`、`pcb_eda_inspect`、`pcb_eda_open_pcb`、`pcb_eda_connectivity`、`pcb_eda_ratlines`、`pcb_eda_drc`。有限编辑使用 `pcb_eda_copy` → `pcb_draw_preview` → `pcb_draw_apply` → `pcb_draw_export`。登记的4层非源板副本可用 `pcb_draw_export_manufacturing` 在新鲜DRC和零飞线通过后导出并校验Gerber/钻孔、BOM与贴片坐标。原生自动布线使用 `pcb_route_preview` → `pcb_route_start` → `pcb_route_status`，必要时 `pcb_route_cancel`，完成后 `pcb_route_export`。GUI 测试板副本由 `pcb_eda_test_copy` 创建，再用 `pcb_eda_test_copy_cleanup` 删除并核验。

有限编辑计划使用mil单位、目标PCB和有来源的几何约束，每批最多20项。原生布线计划选定已有网络与启用SIGNAL层，并保留已有走线。作业必须轮询终态并读取剩余飞线。主控板实时全板ratline计数为0，且在线/离线网表的156器件、512 pad/net映射、104已分配网络完全一致，嘉立创EDA原生连通引擎确认当前全板布线完成。板级DRC缓存为`notChecked`，短路/间距和制造规则尚未验证。

## 离线查询与检查

辅助工具只依赖 Python 3.10+ 标准库：

```text
python tools/pcb.py search "四层 回流"
python tools/pcb.py search "CLI MCP 单位"
python tools/pcb.py sources rules-jlc-impedance
python tools/pcb.py verify-sources
python tools/epro2.py "项目.epro2" --summary
python tools/check_repo.py
python -m unittest discover -s tests -v
node --test --test-concurrency=1 tests/test_eda_actions.js tests/test_drawing_actions.js
```

普通 Python 命令行下，结构解析可使用 `python tools/epro2.py "项目.epro2" --summary`。MCP/归档解析都不是电气设计审核、DRC 或制造验收。

已保存本地原文时，使用 `python tools/pcb.py verify-sources --require-snapshots` 做严格哈希检查。全文快照和提取文本默认不提交 Git；新克隆的普通检查会明确报告快照缺失，仅验证来源清单结构，不会把缺失原文标成“已验证”。这些检查也不等于 PCB 的 ERC/DRC、仿真或实测。Codex 已信任且加载插件后，也可以直接调用 MCP 工具；EDA观察、有限绘板和DRC各自报告证据与限制，不能互相替代。

## 资料结构

```text
.agents/skills/pcb/   项目内技能入口
.agents/plugins/     项目级本地插件目录清单
.codex-plugin/       Codex 插件清单
.mcp.json            本地知识、EDA观察与副本绘板MCP配置
research/eda/        嘉立创官方 CLI、API、工作流和证据清单
research/rules/      板厂、TI、ADI 规则和证据清单
research/cases/      真实硬件与工具案例、许可和证据清单
wiki/               来源页、综合知识、索引、日志与检查报告
docs/               产品范围、架构、阶段验收
templates/          第一块板子的输入清单
tools/              离线解析、MCP、固定EDA动作与有限绘板
raw/                用户提供的原始资料（只读保留）
local/              不提交的私人工程及私有案例指导
```

各主题 `sources.json` 记录来源 URL、读取时间、哈希、权威性、具体主张和限制。快照在各主题 `snapshots/` 中本地保存。公开发布仅包含来源元数据、短证据和原创总结；第三方权利见 [THIRD_PARTY.md](THIRD_PARTY.md)。

项目在独立子目录中维护；工作纪律见 [AGENTS.md](AGENTS.md)，资料维护规则见 [CLAUDE.md](CLAUDE.md)。下一阶段用真实原理图与专业版环境验证，而不是以资料数量作为“会画板”的证据。
