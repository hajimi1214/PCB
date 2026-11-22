# Index

The catalog of pages in this wiki, organized by category. Updated by `scripts/update_index.py` on every ingest.

> Read this first when answering queries — it's the navigation aid for the whole wiki.
> One entry per page. `★` marks a cluster hub — read it before drilling into cluster pages.

## Sources
- [嘉立创专业版接口与工作流](sources/eda-research.md) — CLI/MCP 优先、网关备用、API 版本与单位、原理图更新和 DRC 边界
- [多层板与制造规则来源](sources/rules-research.md) — JLCPCB、TI、ADI 原文证据，叠层/回流/PDN/DFM 条件
- [硬件案例与工具来源](sources/cases-research.md) — 实际 MCU 原理图和 PCB、层数/焊盘事实、工具与许可边界

## Entities
<!-- People, organizations, products, places. Format: -->

## Concepts
- [原理图到 PCB](concepts/schematic-to-pcb.md) — 引脚/焊盘/网络映射、增量更新、封装核对与连接验证
- [多层叠层与回流](concepts/stackup-and-return.md) — 四层候选、连续参考面、换层回流和叠层边界
- [MCU 与电源布局](concepts/power-and-placement.md) — 去耦完整回路、供电载流、敏感器件、封装与热
- [阻抗与接口布线](concepts/routing-and-interfaces.md) — 网络类别、阻抗输入、时序预算、串扰与路由器边界
- [验证与制造](concepts/verification.md) — ERC/DRC/网络/DFM/实测分别取证，完整结果与制造交付
- [单位与几何契约](concepts/units-and-geometry.md) — SCH/PCB 单位、坐标/角度、层、同号多焊盘与器件面
- [USB 与 ESD 条件化规则](concepts/usb-and-esd.md) — 角色/PHY、供电去耦、保护位置、掉电输入和电气合规分别取证
- [有限PCB写入与案例迁移](concepts/bounded-drawing.md) — 源码基线、小批量几何编辑、原生路由作业、结果核对、恢复和工程规则迁移

## Notes
- [第一块四层 MCU 验证板](notes/first-board-plan.md) — 输入、能力探测、有限写入、真实验收与故障用例
- [从工程积累可执行知识](notes/learning-workflow.md) — 来源模型、私有案例、通用方法和MCP查询顺序；结构事实与验证证据分开
- [EDA 运行时接入与证据边界](notes/eda-runtime.md) — 十个MCP工具、固定action、Windows捕获、在线导入限制与真实验证范围

## Reports
