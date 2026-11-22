# 多层板与制造规则来源

本批次已实际读取的记录见 [来源清单](../../research/rules/sources.json)，综合结论见 [研究正文](../../research/rules/findings.md)。完整快照本地保存，公开仓库保留元数据、短证据和原创总结。每条事实仍需按其条件使用，来源数量不代表目标板已验收。

## 逐条来源

### rules-jlc-capabilities

[PCB Manufacturing Capabilities - JLCPCB](https://jlcpcb.com/capabilities/pcb-capabilities)

权威性：JLCPCB 官方制造能力页。读取时间：2026-11-21T08:09:03.048961+00:00。

具体主张：
- Circuit / Min. track width and spacing (1 oz): Multilayer: 0.09 / 0.09 mm (3.5 / 3.5 mil). 3 mil is acceptable in BGA fan-outs.
- Circuit / PTH annular ring: Multilayer: 1 oz: Recommended 0.20 mm or above; absolute minimum 0.15 mm
- Drilling / Min. Via hole size/diameter: Preferred Min. Via hole size: 0.2mm

适用限制：
- 能力随层数、铜厚、板厚、工艺选项变化，订板时必须重新确认。
- PTH 插件孔焊环要求不能无差别替代过孔直径规则；页面表格与描述必须一起读。
- 能力最小值只是可制造边界，不作为推荐布线宽度/电流承载值。

本地证据：`research/rules/snapshots/jlc-capabilities.html`；SHA-256：`c202f6dec766bb6f889e22f42d0cecda0a4920a5157405f6a8f3c0c0d70d6a0c`。许可/条款：原发布者保留版权；未确认允许再分发全文。完整快照与提取文本仅本地研究，公共仓库只发布 URL、哈希、短证据和原创综合。。

### rules-jlc-impedance

[Controlled Impedance PCB Layer Stackup - JLCPCB](https://jlcpcb.com/impedance)

权威性：JLCPCB 官方叠层和阻抗计算入口。读取时间：2026-11-21T08:07:31.698553+00:00。

具体主张：
- Controlled Impedance PCB Parameters and Stackup: according to JLCPCB’s laminated structure and related parameters
- 4-Layer Impedance Control Stackup / JLC04161H-3313: Prepreg 3313*1 0.09940mm
- 4-Layer Impedance Control Stackup: JLC04161H-1080 Stackup

适用限制：
- 页面列出多种叠层，抓取时网页默认状态不是用户选定订单。
- 厚度、铜厚、介电常数、阻焊参数会影响阻抗；不能把某一线宽通用于所有 1.6 mm 四层板。
- 这里只核验材料/几何输入来源，尚未执行阻抗计算或生产确认。

本地证据：`research/rules/snapshots/jlc-impedance.html`；SHA-256：`342cf8e98d411aee0e41f3e7abdd1a59561ab8aa3d3059683e5a9fd86b0efdda`。许可/条款：原发布者保留版权；未确认允许再分发全文。完整快照与提取文本仅本地研究，公共仓库只发布 URL、哈希、短证据和原创综合。。

### rules-jlc-assembly

[PCB Manufacturing & Assembly Capabilities - JLCPCB](https://jlcpcb.com/capabilities/pcb-assembly-capabilities)

权威性：JLCPCB 官方装配能力页。读取时间：2026-11-21T08:07:32.089075+00:00。

具体主张：
- PCB Assembly Technical Capabilities / PCB Layer: 2,4,6-layers
- PCB Assembly Technical Capabilities / Fiducials: Fiducials
- FAQ / BOM and CPL: please include both part A and part B in the BOM and CPL

适用限制：
- Economic 与 Standard PCBA 是不同服务列，封装、单双面、板框、工艺边等要求不能混用。
- BOM/CPL 还需实际校验参考编号、器件面、角度与库封装方向。
- 本文没有给出具体用户板子的贴装可行性结论。

本地证据：`research/rules/snapshots/jlc-assembly.html`；SHA-256：`96a3ca33d0460dbc2564a87c5da02c8e6b9593b8d2ecae1b44f92a3cf8e1d9ca`。许可/条款：原发布者保留版权；未确认允许再分发全文。完整快照与提取文本仅本地研究，公共仓库只发布 URL、哈希、短证据和原创综合。。

### rules-adi-ground

[Staying Well Grounded (Hank Zumbahlen, Analog Dialogue, June 2012)](https://www.analog.com/en/resources/analog-dialogue/articles/staying-well-grounded.html)

权威性：Analog Devices 官方工程文章。读取时间：2026-11-21T08:07:28.904944+00:00。

具体主张：
- Introduction: there is no “cookbook” approach that will guarantee good results
- Ground planes and digital current return: In practice, the current returns must consist of large area ground planes to obtain low impedance to high-frequency currents.
- Decoupling recommendations: Power supply pins should be decoupled directly to the ground plane using low-inductance, ceramic surface-mount capacitors.

适用限制：
- 不同数字电流规模、ADC 架构与系统地结构有条件差异，不可仅按 AGND/DGND 网络名切平面。
- 作者讨论星形地、分区和完整平面，需结合原理图与器件资料评估。

本地证据：`research/rules/snapshots/adi-ground.html`；SHA-256：`87049bfcf9a52616b51f4aebbe3be731ad9e30a0d65a72f993b28da2063989e6`。许可/条款：原发布者保留版权；未确认允许再分发全文。完整快照与提取文本仅本地研究，公共仓库只发布 URL、哈希、短证据和原创综合。。

### rules-adi-ground-bounce

[Reducing Ground Bounce in DC-to-DC Converters—Some Grounding Essentials (Jeff Barrow, June 2007)](https://www.analog.com/en/resources/analog-dialogue/articles/reducing-ground-bounce-in-dc-to-dc-converters.html)

权威性：Analog Devices 官方工程文章。读取时间：2026-11-21T08:09:01.595124+00:00。

具体主张：
- Figure 16 / Ground plane interruption: interruptions to the ground plane under conductors carrying current can increase loop area by diverting the return current
- Figure 16: Return current takes the path of least impedance.
- Figure 17: Component orientation does matter

适用限制：
- 电源布局还需具体稳压器数据手册和评估板，本文不能提供任意器件的 SW 铜面积/热设计参数。
- 文章提供机理，不等于本项目已经做过 EMI 实测。

本地证据：`research/rules/snapshots/adi-ground-bounce.html`；SHA-256：`f341ebed1f16bdb2cc0efebc2a021e365f481688d6e5449ce05cceede2d4a310`。许可/条款：原发布者保留版权；未确认允许再分发全文。完整快照与提取文本仅本地研究，公共仓库只发布 URL、哈希、短证据和原创综合。。

### rules-adi-mt101

[MT-101: Decoupling Techniques (Rev. 0, March 2009)](https://www.analog.com/media/en/training-seminars/tutorials/MT-101.pdf)

权威性：Analog Devices 官方培训教程。读取时间：2026-11-21T08:08:59.846101+00:00。

具体主张：
- PDF p. 6 / Localized high frequency decoupling recommendations: the high frequency decoupling capacitor must be as close to the chip as possible
- PDF p. 7 / Resonant circuits formed by LC decoupling networks: The overall impedance of the decoupling network may exhibit peaking at the resonant frequency.
- PDF p. 7 / Figure 6 discussion: extra inductance and resistance in the PCB trace

适用限制：
- 频段、MLCC 有效电容、器件选型和去耦数量按目标芯片/实际器件模型复核。
- 旧教程举例值不作为现代 MCU 或 PDN 的一刀切配置。
- 本次只提取文本，不据图中距离/比例导出几何规则。

本地证据：`research/rules/snapshots/adi-mt101.pdf`；SHA-256：`d7d7ab776638cd79a2934521adc37df1a9229e2538ee45255df32635d6a9d507`。许可/条款：原发布者保留版权；未确认允许再分发全文。完整快照与提取文本仅本地研究，公共仓库只发布 URL、哈希、短证据和原创综合。。

### rules-adi-mt031

[MT-031: Grounding Data Converters and Solving the Mystery of AGND and DGND (Rev. A, October 2008)](https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf)

权威性：Analog Devices 官方培训教程。读取时间：2026-11-21T08:09:46.110930+00:00。

具体主张：
- PDF p. 2 / Ground and power planes: The importance of maintaining a low impedance large area ground plane is critical
- PDF p. 8 / Meaning of DGND: The name "DGND" on an IC tells us that this pin connects to the digital ground of the IC.
- PDF p. 12 / Evaluation board grounding limitations: it is not usually optimum for multicard mixed-signal systems

适用限制：
- 教程明确分低数字电流、高数字电流、单板及多板情况；不可仅截取评估板星形连接图。
- 目标 MCU ADC/参考电源以具体数据手册要求为先。

本地证据：`research/rules/snapshots/adi-mt031.pdf`；SHA-256：`9dd21b95f00a6d3b31648774e0fef4f456644dcf4a5f4bceccf821d4730f4128`。许可/条款：原发布者保留版权；未确认允许再分发全文。完整快照与提取文本仅本地研究，公共仓库只发布 URL、哈希、短证据和原创综合。。

### rules-ti-cn-highspeed

[SCAA082A: High-Speed Layout Guidelines (revised August 2017)](https://www.ti.com.cn/cn/lit/an/scaa082a/scaa082a.pdf)

权威性：Texas Instruments 官方中国域名应用报告。读取时间：2026-11-21T08:09:46.474022+00:00。

具体主张：
- PDF p. 9 / Return current and loop areas: The best solution is to avoid any slots in the ground reference plane.
- PDF pp. 9–10 / Section 2.2 Board Stackup: There is no fundamental information about how many layers should be used and how the board stackup should look.
- PDF p. 12 / Section 2.3: If possible, use a continuous ground plane; do not split them.

适用限制：
- 文档 2006/2017 的四层表格、2W/3W 规则是特定上下文经验，不是现代总线 SI 仿真的替代。
- 差分等长依据协议时序/偏斜预算，不能无限蛇形；差分对仍须参考结构及回流连续。
- 仅提取了文本证据，没有把图形尺寸当成经验证的规则。

本地证据：`research/rules/snapshots/ti-cn-highspeed.pdf`；SHA-256：`24681796ac36e50f9c6ef5e0b98945b6236ddb9fa620da97597ba62a85990206`。许可/条款：原发布者保留版权；未确认允许再分发全文。完整快照与提取文本仅本地研究，公共仓库只发布 URL、哈希、短证据和原创综合。。

### rules-st-an4879

[AN4879: Introduction to USB hardware and PCB guidelines using STM32 MCUs](https://www.st.com/resource/en/application_note/dm00296349-usb-hardware-and-pcb-guidelines-using-stm32-mcus-stmicroelectronics.pdf)，Rev 13，October 2026。

来自 ST 官方原始应用笔记。已读 pp.8–11（ESD、USB 供电/去耦、VBUS sensing）、pp.14–19（角色/PHY 电路）、p.22 FAQ 和 pp.25–26 修订表。它支持先确认准确 STM32 型号/封装与 USB profile，再生成规则。

- p.10 §2.3 短摘："as close as possible to the receptacle"。保护器件靠近接口是放置偏好；没有通用距离或系统 ESD 通过证明。
- p.11 §2.5 的 `VDDUSB` 去耦和独立供电顺序限定于适用器件/封装，不能推广到所有 MCU。
- p.22 FAQ 的 PHY matching 不等于 PCB 差分阻抗；外部串阻/上拉按准确实现选择。器件 HBM、整机 IEC 测试和 USB 功能/合规分别取证。
- p.25 显示 Rev 3 已删除旧 PCB 阻抗/布线章节，不能把旧转载的走线数值归为当前 Rev 13 结论。时钟术语和器件条件需对照 reference manual。

完整限制、逐页证据和权利信息见 [来源清单](../../research/rules/sources.json)。本地 PDF：`research/rules/snapshots/rules-st-an4879-2026-11-21.pdf`；SHA-256：`a5fd13b823bcc1d60c118f5320aef16bc332fccdd9b8bc3f898c6096d2251959`。读取时间：2026-11-21T11:54:33.760962+00:00。完整 PDF/文本仅本地保存，未确认开放全文再分发许可。关联 [USB 与 ESD](../concepts/usb-and-esd.md)。

### rules-adi-mt094

[MT-094: Microstrip and Stripline Design](https://www.analog.com/media/en/training-seminars/tutorials/MT-094.pdf)，Rev 0，January 2009。

来自 ADI 官方教程。已读 pp.1–2（边沿与传输线、参考模型与公式限制）、pp.3–5（微带/对称带状线）、p.6（外层/内嵌的四层取舍）。

- p.2 短摘："All of the existing equations are approximations"。计算须保留几何、单位、模型/版本与适用范围，进一步分析/测试验证；示例宽度或比例不是生产目标。
- p.2 的参考平面模型要求大面积、低阻抗及交流零电位；地/电源的名字不能证明回流合格。
- p.5 对称带状线的等距参考面假设不能套给任意内层轨迹；p.6 四层示例权衡屏蔽、调试和去耦，不规定通用最佳层序。
- p.1 边沿/延时启发和 p.6 频率图注不成为所有 MCU 的硬阈值；没有目标板 SI、PI、EMI 或板厂阻抗验收证据。字体/公式的文字提取存在限制，本轮不从图形生成几何或求解代码。

完整限制和逐页证据见 [来源清单](../../research/rules/sources.json)。本地 PDF：`research/rules/snapshots/rules-adi-mt094-2026-11-21.pdf`；SHA-256：`bc91bcd6abb465122cb3c68d1051385697c998b025128cd57f119660bae6b646`。读取时间：2026-11-21T11:55:52.286647+00:00。完整 PDF/文本仅本地保存，版权归 ADI，未确认开放全文再分发许可。关联 [回流模型](../concepts/stackup-and-return.md) 与 [阻抗计算](../concepts/routing-and-interfaces.md)。

## 关联知识

- [原理图到 PCB](../concepts/schematic-to-pcb.md)
- [多层参考与回流](../concepts/stackup-and-return.md)
- [单位与几何](../concepts/units-and-geometry.md)
- [验证与制造](../concepts/verification.md)

- [USB 与 ESD](../concepts/usb-and-esd.md)

### rules-adi-mt100

[ADI MT-100 Rev0: Breadboarding and Prototyping Techniques](https://www.analog.com/media/en/training-seminars/tutorials/MT-100.pdf)

已读PDF pp.1、6、10–14：多层原型差异、最终封装、去耦与参考地、原厂评估板。AD8001示例参数不能外推为MCU默认；p.6铣板几何不是现代板厂能力。详细推导见[有限写入与案例迁移](../concepts/bounded-drawing.md)。

完整PDF 1086799字节、15页；SHA-256 `b2081d6d31029cd79fb2f8415f9d7bd8730f723cc32ff81429fe546a78ef4983`。首个截断版本不计有效来源，完整快照仅本地保留，版权归ADI。
