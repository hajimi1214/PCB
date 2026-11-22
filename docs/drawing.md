# 在嘉立创专业版副本中进行有限布局和布线

PCB 0.4 提供元件平移/旋转、网络导线、通孔、板框几何和嘉立创原生异步自动布线作业。视觉测试还可在专用参考项目空白板上放置不绑定原理图的 footprint-only 原型。Codex从原理图、器件手册、机械条件和资料库提出计划，由插件在受登记的工程副本或隔离测试板中运行、读取结果并导出。原生router依据EDA当前规则执行；MCP本身不运行独立避障算法。

## 可执行流程

| 工具 | 输入与结果 |
|---|---|
| `pcb_eda_copy` | 输入本仓库内保存好的 `.eprj2` 或 `.eprj3` 索引路径。复制原生工程及必要文件到 `local/drawing/copies/`，新建隐藏 CLI 会话，返回 `copy_id`、session 和副本路径。 |
| `pcb_draw_preview` | 输入 `copy_id`、准确 PCB UUID、1–20 项操作和有来源的 mil 约束。只在副本中聚焦 PCB，保存源码基线、SHA-256、物理焊盘/网络/层声明，返回计划 ID 与待检查项。 |
| `pcb_draw_apply` | 输入计划 ID，核实会话路径、工程/PCB身份及源码哈希，执行命令组，重新读取每个物理焊盘与新建图元，核对网络与层，返回结果和恢复状态。 |
| `pcb_draw_export` | 对成功应用且未继续变化的计划导出本地 `.epro2`。核对磁盘文件SHA-256、字节数和受限ZIP CRC，返回可导入的原生归档路径；尚不代表已重新导入验证。 |
| `pcb_draw_export_manufacturing` | 对登记的非源板4层副本重新运行完整DRC并读取全板飞线。仅在DRC新鲜通过且零飞线时导出嘉立创一键Gerber/钻孔、BOM和坐标文件，验证磁盘哈希、ZIP CRC、四个铜层、板框/钻孔项及BOM/CPL结构。文件供人工CAM复核，不等于嘉立创下单/DFM验收。 |
| `pcb_route_preview` | 输入 `copy_id`、PCB UUID、1–64个已有网络和1–8个启用的SIGNAL铜层，保存当前源码基线与路由参数。预览不启动布线器。 |
| `pcb_route_start` | 启动嘉立创 EDA 专业版 `startAutoRouting`，固定保留已有导线/过孔、45度拐角、优先布通率。返回原生 job ID；启动结果未知时不重复运行同一计划。 |
| `pcb_route_status` | 查询原生作业状态和进度。到达完成/取消/失败终态后，分页读取全板剩余飞线并记录源码摘要。 |
| `pcb_route_cancel` | 请求取消一个记录为 queued/running 的原生作业；必须再查状态确认终态和 partial 标志。 |
| `pcb_route_export` | 仅导出已完成且无 partial 结果的路由作业；核对来源摘要、磁盘哈希、大小和 ZIP CRC。 |

只读项目树工具 `pcb_eda_inspect` 会同时列出Board树和项目PCB文档，可用于核实临时GUI测试PCB是否仍存在，以及它是否关联原Board。
`.epro2` 是导入归档，不可改扩展名冒充 `.eprj2/.eprj3`。已有用户归档可继续用于离线分析；要运行有限写入，先由 EDA 导入并保存为本仓库内的原生工程。`.eprj3` 索引必须位于独立目录，支持文件一起复制；数据库存在 WAL/SHM/journal 时拒绝复制。在线账户新建/上传不是这些工具的隐含动作。

## 计划契约

所有数值以 **mil** 为单位，1 mil = 0.0254 mm。输入单位为 mm 时由 Codex 明确换算，保留原始依据。支持操作为：

- `move`：精确 `component_id`、目标 `x/y`。保持层、旋转、位号和网络，拒绝锁定器件。同号多个焊盘按物理 ID 分别读取，验证每个焊盘跟随同一平移。
- `line`：已存在的精确网络名、启用且未锁定的 SIGNAL 铜层 ID、两端坐标和线宽。拒绝零长度线；PLANE负片内电层不作为普通导线层。原生引擎若拆分线段导致本批精确端点读取不同，本版本停止并尝试回滚，不假装支持所有相交拓扑。
- `via`：已存在网络、位置、孔径和盘径，仅通孔。孔径和单侧焊环 `(diameter-hole)/2` 必须达到本次声明约束。不隐式引入盲埋孔、缝合孔、换层或新增网络。

`constraints` 必须提供 `units="mil"`、非空 `source`、`region=[min_x,min_y,max_x,max_y]`、`min_trace_width`、`min_hole`、`min_annular_ring`，没有工厂默认值。region只约束本批位置/线宽外沿/过孔外沿和元件焊盘中心，**不是实际板框、器件包络、keepout或间距引擎**。来源字符串是人工提供的依据引用；插件校验数值，不能自动证明所引文档适用于该工艺。

- outline 仅能在已验证无现有板框的登记测试板上创建一条 layer 11 闭合多边形。
- replace_outline 只能使用快照中唯一现有的 primitive_id，保持图元身份并在命令组中替换几何。若运行时没有 pcb_PrimitivePolyline.modify，预览会因能力缺失而停止，不尝试删除后重建。
- footprint 是视觉原型，要求准确的 library UUID、footprint UUID 和物理焊盘号。它不创建 Device 或网络绑定，不是可布线器件或制造证明。真实板的正常器件布局应来自成功导入的原理图器件对象。

EDA 可能重排闭合多边形的起点或方向；板框读回按闭合顶点环比较循环起点和正反向，而不是要求序列编码逐字节相同。顶点、层、宽度或图元身份不一致仍会回滚。

## 嘉立创原生自动布线

`startAutoRouting` 是 EDA 4.1.79 起文档化的 Beta 长作业接口。每次预览显式选择要参与的网络和 SIGNAL 铜层；空网络列表在 EDA 会解释成整板未布网络，本插件拒绝空列表。固定使用45度拐角、`keep`已有导线/过孔、`COMPLETION`优先布通率。未传给插件的制造能力、网络优先级/阻抗和特殊拓扑不会由自动路由器自动获知。

作业模型返回 `jobId` 后应轮询状态到 `completed/canceled/failed`。启动回执只表示任务接收；作业 completed 也不表示所有网络布通。插件读取所有分页 ratlines，但零飞线仍不构成 DRC/电气等价证明。长作业如果被取消或失败，核对 `partial` 及工作副本的源摘要；partial 为 true 的工程不能导出成“完成路由”结果。直接函数 `autoRouting()` 有900秒硬上限，本插件使用作业API并且不会以MCP超时猜测作业终态。

`pcb_eda_ratlines` 会独立读取目标PCB的全板原生飞线。主控板实测 `unrouted_total=0`，MCP以 `routing_complete=true`明确表示“嘉立创EDA原生连通引擎报告没有剩余未布连接”。这是全板路由完成证据，DRC缓存仍为 `notChecked`，两项不能混为一谈。

布局时先固定连接器与机械约束，再处理电源/去耦/时钟和敏感接口，参见[设计指南](field-guide.md)。已布线器件移动后可能产生失联或旧线，需要重新审查连接与DRC。原生router使用EDA当前规则，MCP不计算阻抗、载流、回流完整性或制造裕量，也不提供智能布局和铺铜。

## 基线与恢复

源码在快照开始和结束各读取一次，不一致则拒绝；应用前再核对 SHA-256。因此读取后同一 PCB UUID 下发生的修改也会使旧计划失效。运行中仍可能存在外部编辑竞争；应避免同时手动编辑测试副本。与原生 EDA API 之间没有全局跨进程写锁，不能声称原子事务。

保存的计划与基线位于 `local/drawing/plans/`。每个计划写入前用独占创建保存 attempt 记录，明确结果写入 receipt；同一计划重复调用返回已有结果，超时/断线/进程异常后保留未知状态，不能直接重试。失败时只在仍是原 PCB 焦点且命令组未提交时尝试回滚；恢复后的源码摘要一致才标记 `source_verified`。失败、焦点变化或摘要不同需要恢复副本，不能对另一个窗口执行撤销。

成功应用表示内存中的有限几何读取符合计划；原生编辑器可能另有自动保存，不把 API 返回值当作磁盘保存证据。原生归档仍需在 EDA 中重开并读取。制板文件导出前强制重算 DRC 并检查零飞线；导出后仍需在 CAM 中核对层、板框、钻孔、阻焊/丝印和坐标方向，检查原理图网络与样板功能。

## 本轮证据

在 EDA Pro 4.1.100 中经Windows-MCP UI打开已加载的工程。PCB MCP读取主控板原生网表324682字节并验证本地保存的SHA-256，实时网表与离线归档的156器件、512个pad/net实例、104个已分配网络和四个启用铜层相符。主控板原生ratline为0。DRC缓存仍为notChecked，本轮未触发。

测试PCB副本的原生router job确实启动并返回job ID，但约三分钟停在1%后按流程取消；终态canceled，partial未报告，源码摘要回到预览基线，剩余ratline为0。随后 JLCEDA Pro 网页版 4.1.105 对该副本完成新鲜原生DRC，141项检查、0个问题、6秒；Gerber一键导出对话框报告4层，点击导出后出现“文件已生成”提示。浏览器配置了下载位置提示，文件未出现在配置目录，故未检查 ZIP 成员、钻孔和 CAM 对位。本地 MCP 导出最初因 Gerber API 重排 JSON 对象键被原文 SHA-256 拦截；已改为规范化 JSON 键序，并只对记录为没有任何导出文件的明确失败开放新目录重试。当前插件 GUI CLI session 已关闭，MCP制造文件动作仍未在真实运行时完成；测试副本仍在账户工程中，需完成导出并清理后才能关闭该阶段。原主板未做几何修改。

2026-11-22 的开源参考挑战详见 Git 忽略目录 local/board-challenges/analysis/test-run-2026-11-22.json。三份来源外观指标和独立任务提示已建立。RP2040 原生 PCB 导入项目成功，但新板 importChanges 对明确 schematic UUID 与无参调用均返回 false，故目标板没有器件或网络。PCB MCP 在一个空白目标上提交并读回了程序化生成的 150 mil 圆角板框；该几何单独不构成可制造板。PCB2 与 PCB3 新鲜 DRC 均报告 1 条 Netlist Error。Footprint-only 的 MCU 和简单电容 create 测试都在 EDA pcb_PrimitiveComponent.create 阶段失败，命令组回滚且源摘要恢复。Adafruit Feather 与 HackRF 的新项目导入未获 EDA 确认，因此没有布局试验。插件已实现按图元 ID 替换板框，但当前 4.1.100 运行时没有 pcb_PrimitivePolyline.modify，该能力尚未实测。三块完整 PCB、布线、电气一致性与制造验收均未通过。

官方依据见[有限写入与案例迁移知识](../wiki/concepts/bounded-drawing.md)、[EDA来源登记](../research/eda/sources.json)。仅把成功取得的文件登记为资料；截断或失败下载不计为已学习证据。
