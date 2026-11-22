# Log

Chronological record of operations on this wiki. Append-only.

Each entry starts with `## [YYYY-MM-DD] action | title` so the log is greppable:

```bash
grep "^## \[" wiki/log.md | tail -20
```

Maintained by `scripts/append_log.py`.

---

## [2026-11-21] bootstrap | Wiki initialized
Topic: 面向 Codex 与嘉立创 EDA 的可追溯 PCB 设计知识库，优先研究多层板和原理图到 PCB 的约束流程

## [2026-11-21] bootstrap | PCB 项目和资料库建立
建立项目范围、可追溯知识页和 Codex 技能，研究专业版接口、多层板规则及 MCU 案例。

## [2026-11-21] ingest | 嘉立创 EDA 官方接口与 CLI/MCP
核实 CLI/MCP、网关、原理图更新、自动布线、DRC、单位与版本限制；原文快照仅本地。

## [2026-11-21] ingest | 四层 MCU 与 PCB 制造规则
摄入 JLCPCB、TI、ADI 与器件厂商规则，区分制造能力与工程目标并保留适用条件。

## [2026-11-21] ingest | 开源硬件、四层板与工具案例
实际解析 RP2040、ESP32-PoE 与 HackRF KiCad 工程以及 Adafruit Eagle 层配置；记录许可证和工具边界。

## [2026-11-21] ingest | 只读检查专业版工程结构
解析本地未加密工程归档的文档、板层和器件身份映射；没有运行 EDA 或修改源工程。具体设计细节仅保存在 Git 忽略目录。

## [2026-11-21] ingest | 私有多层板案例与只读插件
建立本地 epro2 结构解析器和私有案例检索入口，完善通用布局方法；MCP 仅只读，未连接 EDA 或更改板文件。

## [2026-11-21] update | 案例摄入流程与Codex技能
文档/Board隔离、局部封装覆盖、符号内PART/PIN、物理焊盘保留以及条件化布局知识；增加MCP工作流，原生EDA写入尚未实现。

## [2026-11-21] ingest | 器件级规则与案例证据
在本地私有案例中保存六份工程关联器件资料、50条已核页码引文和资料冲突。MCP可按器件/网络查结构证据并检索条件化规则；没有原生EDA写入或DRC执行。

## [2026-11-21] update | 固定 EDA 观察适配器
在嘉立创 EDA Pro 4.1.100 独立空 headless 会话中验证 doctor/session/环境 action；加入 UUID 绑定的工程、网表、物理焊盘、层和 DRC 观察。未写用户工程。

## [2026-11-21] ingest | USB/ESD 与传输线条件化规则
摄入 ST AN4879 Rev13 与 ADI MT-094，17条短证据逐页核对，补充USB/ESD、PHY供电和微带/带状线模型边界；公开来源合计77条。

## [2026-11-21] note | 在线模式无法导入离线本地副本
空headless会话在线模式拒绝Offline Client Local Path；未上传私有工程，源归档哈希未变，测试会话已关闭。原生板级网表和DRC待可导入副本。

## [2026-11-21] ingest | 有限绘板API与原型方法
单并发下载并读取6页嘉立创官方API及完整15页ADI MT-100；10条短引文定位核对。资料库84条；截断PDF与失败下载不计有效来源。

## [2026-11-21] update | PCB 0.3 副本绘板流程
新增本地原生副本、预览、有限平移/导线/通孔、源码哈希与物理焊盘核对、命令组恢复和原生导出。14个MCP工具。成功路径经模拟测试，真实空会话仅验证方法存在和错误目标拒绝；未修改用户原板，待原生工程实测。

## [2026-11-21] update | 原生自动布线作业接入
接入EDA startAutoRouting/getAutoJobStatus/getAutoJobLog/cancelAutoJob/getRatlines，显式选网与启用SIGNAL层，保留现有布线，查询终态和全部飞线并导出副本。4.1.100空会话确认方法存在，未对真实PCB启动作业。

## [2026-11-22] update | Windows-MCP实测与路由完成证据同步
Windows-MCP 0.8.9经项目stdio白名单控制嘉立创EDA；原板156组件/512 pad-net/104已分配网络映射与离线归档一致，原生ratline=0，MCP标记EDA布线完成。PCB测试副本自动路由停在1%后取消、确认canceled后删除。DRC缓存notChecked，原板无几何修改。

## [2026-11-22] test | 三块开源板视觉挑战
从 RP2040、Feather STM32F405 和 HackRF One 工程生成独立视觉任务。RP2040 空白测试板完成一条程序化圆角板框写入与读回，但没有导入器件/网络，PCB2 与 PCB3 fresh DRC 各报 1 条 Netlist Error。原理图 importChanges 与两种 footprint-only create 均失败并回滚。Feather 和 HackRF 的 EDA 项目导入未获确认。完整逐板提示和失败记录在 Git 忽略文件 local/board-challenges/analysis/test-run-2026-11-22.json。目前三块完整 PCB 均未通过验收。
