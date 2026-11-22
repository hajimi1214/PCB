# PCB 当前状态

## State

独立项目PCB，目标Codex + 嘉立创EDA专业版，首阶段4层MCU控制板。版本0.4.0，有92条公开来源、24个PCB MCP工具和项目隔离的Windows-MCP。主控板原生网表与离线归档器件/焊盘网络映射相符，实时原生ratline为0，EDA报告全板无未布连接。测试副本在Pro 4.1.105网页实测141项DRC、0个问题；Gerber导出界面报告成功，但本地文件未验包，MCP导出action未完成真实运行时验证。测试副本route job停在1%后取消，当前副本尚待清理。原主控板缓存DRC仍为notChecked，因此没有制造交付验收结论。

## Last ingest

2026-11-22：安装Windows-MCP 0.8.9到本地Python3.14环境，关闭遥测并白名单9个UI工具。经UI打开在线工程，主控板网表与离线epro2的156器件/512焊盘网络映射相符，原板ratline为0。测试副本router job启动后停在1%，请求取消并确认canceled后清理。

2026-11-22 开源参考挑战：RP2040 空白 PCB3 成功写入并读回独立生成的 150 mil 圆角板框。PCB2 与 PCB3 fresh DRC 各有 1 条 Netlist Error，原理图器件未能导入。Footprint create 失败且已回滚。Feather 与 HackRF 项目导入未获确认。本轮未产出完整挑战板，逐板任务提示和测试证据见本机忽略记录 local/board-challenges/analysis/test-run-2026-11-22.json。

## Active themes

- [有限绘板流程](../docs/drawing.md)：有限几何编辑及原生router job预览/启动/状态/取消/导出；mil几何约束的来源必填。
- [原理图到PCB](concepts/schematic-to-pcb.md)与[单位/几何](concepts/units-and-geometry.md)：物理焊盘、网络与坐标。
- [叠层/回流](concepts/stackup-and-return.md)、[电源布局](concepts/power-and-placement.md)、[USB/ESD](concepts/usb-and-esd.md)。
- [运行时](notes/eda-runtime.md)、[验收](concepts/verification.md)：传输、几何写入、DRC、制造与实测各自取证。

## Open items

- 用户工程仍是epro2归档，已离线解析；实际绘板需EDA保存的本地eprj2或独立目录中的eprj3索引/支持文件。在线模式不能调用离线路径导入，不得改名或默认上传云端。
- 在真实本地副本运行有限修改、导出、重新打开，再核对原理图/PCB网络、物理焊盘与完整DRC。代码成功路径当前是模拟API验证。
- 原板缓存DRC为notChecked；要评价可制造交付，需运行DRC和相应制造检查。原板没有写入几何。
- 测试副本原生路由作业停在1%后取消，成功完成路径仍待小规模有未布网络的副本验证。智能布局、铺铜和完整制造验收未实现。

## Conventions

仅操作PCB子目录，不读同级项目。用户原始归档只读；原生副本、计划、attempt/result、源码与导出在local/drawing。结果未知不得自动重试。公开来源只提交元数据/短证据/原创总结；全文快照仅本地。维护见[规则](../CLAUDE.md)，知识摄入不等于模型权重训练。
