---
name: pcb
description: 根据原理图研究、规划和审查嘉立创 EDA 专业版 PCB，在登记的本地工程副本中预览并执行元件平移、网络导线和通孔操作。优先处理4层MCU板的连接、叠层、布局布线约束与验收。
---

# PCB

本技能随 PCB 仓库使用；从本文件所在目录向上三级得到仓库根目录，所有路径以该根目录解析。先读 [当前状态](../../../wiki/hot.md)，再按 [知识索引](../../../wiki/index.md) 按需检索。不要一次读取所有研究快照。

## 根据任务进入

- 学习/查询：优先用 MCP `pcb_search`，再用 `pcb_sources` 取得原始依据；只有 MCP 不可用时运行 `python tools/pcb.py search "关键词"`。需要当前用户上传板卡的本地案例启发时可用 `pcb_case_search`，把该案例观察限定为此板，不能外推。任何文件分析前用 `pcb_inspect_local_project` 做归档摘要；指定一个仓库内 `.epro2` 路径即可，不指定时只有一份候选文件才自动选择。MCP 结果包含出处，但不含板级验证结论。
- 局部电路学习：用 `pcb_query_board`，传摘要中的 PCB 文档 UUID（不是父级 Board UUID），再按精确位号或网络名查询器件、物理焊盘网络和该板声明网络的线宽/层/过孔统计。先用 `next_pad_offset` 取完当前器件页的焊盘，再按 `next_component_offset` 换下一批器件（重置 `pad_offset=0`），不能把第一页当全部；同号焊盘保留多个物理实例。它没有原理图网表对比或几何连通验证，不能凭这些记录宣称线路布通。
- 新板设计：使用 [输入表](../../../templates/board-intake.md)，先获得专业版工程、原理图连接、MCU/封装、供电、机械和工艺条件。用户已选专业版与 4 层，不重复询问这两个偏好。
- 接入或运行时观察：先读 [适配方案](../../../docs/architecture.md)，使用 `pcb_eda_status`/`pcb_eda_sessions`，再给固定 action 传明确 session、工程、焦点文档和 PCB UUID。只用当前编辑器真实提供且经过能力探测的官方接口；研究网页里的函数名不证明运行环境支持。没有 raw JS/eval，也不调用未审查代码。
- 布局规划：参考[通用案例指南](../../../docs/field-guide.md)建立条件化功能块和约束计划；当前板的具体观察使用 `pcb_case_search`，不要复制其布局或线宽作为新板默认。
- 绘板：按[绘板流程](../../../docs/drawing.md)使用 `pcb_eda_copy`复制本地原生工程；有限编辑用 `pcb_draw_preview/apply/export`。原生自动路由先 `pcb_route_preview` 显式选择网络与 SIGNAL 层，再 `pcb_route_start`，持续 `pcb_route_status`，完成后检查飞线和partial，最后 `pcb_route_export`。对登记的非源板4层副本，`pcb_draw_export_manufacturing` 会先重跑DRC并检查零飞线，再导出并结构校验Gerber/钻孔、BOM及贴片坐标。工程归档`.epro2`需先用EDA导入保存成原生工程，不能改扩展名。
- 审查：按 [原理图到 PCB](../../../wiki/concepts/schematic-to-pcb.md) 和 [验收](../../../wiki/concepts/verification.md) 逐项记录证据；不把资料检索或静态文档检查称为板级验收。

原生自动布线只在用户选定的本地副本上运行。先 `pcb_route_preview` 选准确网络和启用SIGNAL层，再 `pcb_route_start`，重复查询 `pcb_route_status`，核对终态、partial和未布飞线，最后才导出。路由器完成或飞线为零不能称为DRC/电气通过。取消也要继续查询终态。

## 设计判断

先核对位号/引脚/焊盘/网络对应，再确认板框、层叠、网络类别和工艺。去耦、晶振、开关电源、模拟输入、外部接口分别提取器件厂商规则；不从器件外形推断连接。4 层方案须说明信号参考层、回流与换层策略，阻抗/线宽须由实际工厂叠层确定。

MCP已实现副本中的有限写入、原生路由作业和有DRC/飞线门槛的制造导出；制造导出经过模拟API与文件格式回归，真实UI仅验证过4层副本141项DRC零问题和Gerber界面成功提示，文件落盘、CAM检查及真实MCP写入→布线→导出→重开尚未验收。超时/未知启动结果禁止直接重试；持续查询作业终态，检查partial和完整分页飞线。有限编辑的区域检查不等于板框/keepout/器件包络/间距引擎。`pcb_eda_connectivity`不比较原理图/PCB或证明几何连通；`pcb_eda_drc`默认只读最近结果，明确`run=true`才运行详细检查，缓存、陈旧、不完整或含糊时间戳不能通过。

每阶段报告实际改变、证据、剩余问题。布局完成、布线完成、DRC 通过、制造可交付、功能已实测分别陈述。未接入 EDA 时，仅交付设计计划、约束和研究结论。

## 维护知识

来源冲突保留版本和条件；新增资料按 [资料库规则](../../../CLAUDE.md) 建来源记录、更新相关页/索引/日志。运行 `python tools/pcb.py verify-sources` 与 `python tools/check_repo.py` 验证存档和链接。

