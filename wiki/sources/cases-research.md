# 硬件案例与工具来源

本批次已实际读取的记录见 [来源清单](../../research/cases/sources.json)，综合结论见 [研究正文](../../research/cases/findings.md)。完整快照本地保存，公开仓库保留元数据、短证据和原创总结。案例用来建立解析回归和规则适用边界，并不表示嘉立创可直接导入。

## case-esp32-s3-layout

[Espressif ESP32-S3 Hardware Design Guidelines — PCB Layout Design](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html)

读取时间：2026-11-21T08:07:16.136856+00:00。

具体主张：
- 官方推荐四层：顶层信号/元件，第二层完整地，第三层电源/少量信号并保证 RF/晶振下方地，底层少量信号。
- USB 差分阻抗 90 Ω±10%，尽量少换层，必要换层处配置一对地回流过孔，保持连续参考面。
- RF 走线目标 50 Ω，模组天线位置、净空和外壳影响需要独立考虑。

适用限制：
- 芯片/模组适用条件不可混同，不能把 ESP32-S3 个别线宽、净空和等长数值推广给任意 MCU。
- 未在本项目进行 SI/PI 仿真或射频实测。

本地证据：`research/cases/snapshots/esp32-s3-guide.html`；SHA-256：`92318f21920eb2fc7d2ea0dc158c27edaa735e467a45b0f4e648759feaccc7a6`。权利信息：Espressif 文档版权；仅本地研究快照，未确认可整体再分发许可证。。

## case-kicad-cli-9

[KiCad 9.0 Reference Manual — Command-Line Interface](https://docs.kicad.org/9.0/en/cli/cli.html)

读取时间：2026-11-21T08:09:15.101664+00:00。

具体主张：
- pcb drc 支持 JSON 报告、--schematic-parity 和 --exit-code-violations。
- 使用 --exit-code-violations 时发现违规返回 5，零违规返回 0。
- sch erc、PCB Gerber、Excellon 钻孔等导出可由 CLI 执行。

适用限制：
- 仅适用于 KiCad 格式和匹配的版本；不是嘉立创专业版 DRC 接口。
- 本次只读取文档，没有安装或运行 KiCad；不能声称已对下载工程执行 DRC。

本地证据：`research/cases/snapshots/kicad-cli.html`；SHA-256：`80aff1768f5a9eb7194c534b542e19260fe7132ccf82aa575b2ac2480bf6d408`。权利信息：GNU GPL v3+ 或 CC BY 3.0+，文档版权 The KiCad Documentation Contributors。。

## case-freerouting-readme

[Freerouting — README](https://api.github.com/repos/freerouting/freerouting/readme)

读取时间：2026-11-21T08:09:11.905083+00:00。

具体主张：
- 核心导入 Specctra/Electra DSN、导出 SES，支持 CLI/GUI/API。
- README 提供 MCP 路径及本地执行模式。
- CLI 的 -de / -do 分别指定输入设计与输出会话。

适用限制：
- 未验证嘉立创专业版能无损 DSN→SES 往返。
- 自动布线不会代替器件布局、层叠设计、阻抗、回流和最终 DRC。
- 远程 API beta、申请密钥及成本条件不能当成本地必备。

本地证据：`research/cases/snapshots/freerouting-readme.txt`；SHA-256：`f31de0dec1e4dee27e4f46ad8befa289697789a55c2cbdc9617d3cd236add17e`。权利信息：GPL-3.0，另见同仓库 LICENSE；API 服务条款独立。。

## case-freerouting-license

[Freerouting — GNU GPL v3 license](https://api.github.com/repos/freerouting/freerouting/license)

读取时间：2026-11-21T08:09:13.065121+00:00。

具体主张：
- 仓库 LICENSE 文本为 GPL Version 3。

适用限制：
- 开源工具许可证不等同于公开在线服务免费或无条件可用。

本地证据：`research/cases/snapshots/freerouting-license.txt`；SHA-256：`e1c0ad728983d8a57335e52cf1064f1affd1d454173d8cebd3ed8b4a72b48704`。权利信息：GNU GPL Version 3，需按具体集成与分发方式评估义务。。

## case-tscircuit-readme

[tscircuit — React for Circuits README](https://api.github.com/repos/tscircuit/tscircuit/readme)

读取时间：2026-11-21T08:09:14.200990+00:00。

具体主张：
- TypeScript/React 描述元件和网络，支持电路与 PCB 预览及制造文件导出。
- README 的电阻分压示例明确以 pin 与 net 表达连接，并给出 Gerber、BOM、坐标导出能力。

适用限制：
- 未核验嘉立创专业版原生工程双向编辑接口。
- 生成 Gerber 不能证明可编辑工程、器件映射、网络规则及布线在嘉立创内一致。

本地证据：`research/cases/snapshots/tscircuit-readme.txt`；SHA-256：`816864ac4c228f53abb7363a6f1dbf814d0c222eca32007f2c11680a4676a937`。权利信息：MIT，另见同仓库 LICENSE。。

## case-tscircuit-license

[tscircuit — MIT License](https://api.github.com/repos/tscircuit/tscircuit/license)

读取时间：2026-11-21T08:10:22.644679+00:00。

具体主张：
- 许可证授予使用、复制、修改和分发权限并要求保留版权与许可声明。

适用限制：
- 下游元件库、数据服务与其他依赖需各自核对。

本地证据：`research/cases/snapshots/tscircuit-license.txt`；SHA-256：`a5f5fb24026081322e48c6de970de4300dbc516fcddf02468d74b3978909f156`。权利信息：MIT，Copyright (c) 2024 tscircuit Inc.。

## case-olimex-readme

[OLIMEX ESP32-PoE — README](https://api.github.com/repos/OLIMEX/ESP32-POE/git/blobs/da9d68bc2eff66a164cebf9859826f8ae5cee5b4)

读取时间：2026-11-21T08:10:20.966644+00:00。

具体主张：
- 项目是带 Wi-Fi/BLE/Ethernet 和 PoE 的 ESP32 开发板。
- README 对硬件、软件、文档分别声明许可证，不能用根 LICENSE 覆盖全部资料。

适用限制：
- 包含 PoE 电源等复杂功能，不推荐完整照搬为第一块四层 MCU 验证板。

本地证据：`research/cases/snapshots/olimex-readme.md`；SHA-256：`420a6bcdddc0b7ef5fcb0f3bd6b60e15e184175c49d92e1c2dbc76ed3bdfee6c`。权利信息：硬件 Apache 2.0；软件 GPL3；文档 CC BY-SA 3.0。。

## case-olimex-license

[OLIMEX ESP32-PoE — Apache License 2.0](https://api.github.com/repos/OLIMEX/ESP32-POE/git/blobs/261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64)

读取时间：2026-11-21T08:10:20.938119+00:00。

具体主张：
- 根 LICENSE 为 Apache 2.0，与 README 的硬件许可声明对应。

适用限制：
- 软件和文档分别按 README 所列许可证处理。

本地证据：`research/cases/snapshots/olimex-license.txt`；SHA-256：`c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`。权利信息：Apache License Version 2.0。。

## case-olimex-b1-pcb

[OLIMEX ESP32-PoE B1 — KiCad PCB](https://api.github.com/repos/OLIMEX/ESP32-POE/git/blobs/943faf085f3b16eef4afc14ccbc1350e22915ffd)

读取时间：2026-11-21T08:10:21.441327+00:00。

具体主张：
- 实际解析两铜层 F.Cu/B.Cu，板厚 1.6 mm，123 个 module，133 条 net 声明包含空网。
- 实际解析 2429 个 segment、176 个 via。
- U4 的重复焊盘号 33 同接 GND；USB-UART1 有同号外壳焊盘与无编号 NPTH。

适用限制：
- 此工程是两层，不能当作已验证的四层案例。
- 未执行电气仿真、KiCad DRC 或嘉立创导入。

本地证据：`research/cases/snapshots/olimex-b1-pcb.kicad_pcb`；SHA-256：`b2b32abbbee77ef0e9eb36abd5a0e10534105dc51c111eb88f670143e7b33720`。权利信息：硬件 Apache-2.0；本项目仅研究，不直接作为新设计。。

## case-olimex-b1-sch

[OLIMEX ESP32-PoE B1 — Legacy KiCad schematic](https://api.github.com/repos/OLIMEX/ESP32-POE/git/blobs/ba9896b137fcd393b6b64bcb084aab49983887d1)

读取时间：2026-11-21T08:10:21.395722+00:00。

具体主张：
- 取得对应 B1 原理图文本，可与 PCB 中器件位号/网络核对。

适用限制：
- 尚未编写完整旧版原理图连通性解析器，未证明全板原理图与 PCB 电气一致。

本地证据：`research/cases/snapshots/olimex-b1-sch.sch`；SHA-256：`55461697848c71c2ed39e85998577b0a36c5d946e5a7013ac4d1531b32a102c6`。权利信息：硬件 Apache-2.0。。

## case-rp2040-pcb

[Raspberry Pi RP2040 Minimal Design Example R3 — PCB](https://datasheets.raspberrypi.com/rp2040/Minimal-KiCAD.zip)

读取时间：2026-11-21T08:15:18.891440+00:00。

具体主张：
- 实际 PCB 为 KiCad 10.0 / version 20260206，日期 2026-07-03，板厚 1 mm，两铜层 F.Cu/B.Cu。
- 实际解析 34 个 footprint、313 个 segment、28 个 via。
- U3 RP2040 的 46/47 焊盘分别为 USB_DM/USB_DP；U2 W25Q128JVSIQ 的 1/2/3/5/6/7 对应 QSPI_SS/SD1/SD2/SD0/SCLK/SD3。

适用限制：
- 官方当前示例是两层；本项目目标四层重布局需独立验证。
- KiCad 9 文档不足以保证兼容这个 KiCad 10 源文件。

本地证据：`research/cases/snapshots/rp2040-RPI-RP2040-MINIMAL_R3-S1.kicad_pcb`；SHA-256：`f6c8e633a567ca884b269dc7ec934bebbce28534d0fdb84623a007840a01a471`。权利信息：MIT，包内 LICENSE.txt 明确，Copyright (c) 2026 Raspberry Pi Ltd。。

## case-rp2040-schematic

[Raspberry Pi RP2040 Minimal Design Example R3 — schematic](https://datasheets.raspberrypi.com/rp2040/Minimal-KiCAD.zip)

读取时间：2026-11-21T08:15:18.893440+00:00。

具体主张：
- 取得同包对应 MCU、USB、QSPI 外部 Flash 和调试原理图文本。

适用限制：
- 仅查看文本关键内容，未运行 ERC 或完整网络提取。

本地证据：`research/cases/snapshots/rp2040-RPI-RP2040-MINIMAL_R3-S1.kicad_sch`；SHA-256：`b72204fe19d41573968c9c9178403c5ad20262923d339846dd24dffdd6306c25`。权利信息：MIT，包内 LICENSE.txt 明确，Copyright (c) 2026 Raspberry Pi Ltd。。

## case-rp2040-project

[Raspberry Pi RP2040 Minimal Design Example R3 — project settings](https://datasheets.raspberrypi.com/rp2040/Minimal-KiCAD.zip)

读取时间：2026-11-21T08:15:18.891440+00:00。

具体主张：
- 取得与 PCB/原理图同包的 kicad_pro 工程设置，可用于版本/规则来源研究。

适用限制：
- 不能把该示例的规则值直接映射成当前嘉立创订单能力。

本地证据：`research/cases/snapshots/rp2040-RPI-RP2040-MINIMAL_R3-S1.kicad_pro`；SHA-256：`0d871e3c2f2c76fd2141c46c03371d295adff3d63da2477bc3840ed9aedfe6d6`。权利信息：MIT，包内 LICENSE.txt 明确，Copyright (c) 2026 Raspberry Pi Ltd。。

## case-rp2040-license

[Raspberry Pi RP2040 Minimal Design Example — MIT License](https://datasheets.raspberrypi.com/rp2040/Minimal-KiCAD.zip)

读取时间：2026-11-21T08:15:18.884899+00:00。

具体主张：
- 包内 LICENSE.txt 载明 MIT、Copyright (c) 2026 Raspberry Pi Ltd，并说明实物尺寸需要自行测量核验。

适用限制：
- 不是所有 Raspberry Pi 文档均自动适用此包许可证。

本地证据：`research/cases/snapshots/rp2040-LICENSE.txt`；SHA-256：`b01f852b57e955edeb4001c02fb3a204bd7309a19d8185a6312598f977d656cc`。权利信息：MIT，包内 LICENSE.txt 明确，Copyright (c) 2026 Raspberry Pi Ltd。。

## case-hackrf-one-readme

[Great Scott Gadgets HackRF One hardware README — four-layer stackup](https://api.github.com/repos/greatscottgadgets/hackrf/git/blobs/2e7acfbf8435ccdd9a1fdf5713ff20ef2271b5ac)

读取时间：2026-11-21T08:24:42.327457+00:00。

具体主张：
- README 明确写 4 层 1.6 mm，次序 C1F/C2/C3/C4B。
- 说明外层铜 0.035 mm、内层铜 0.0152 mm；介质 0.2104/1.065/0.2104 mm，7628 介质 Er=4.6±0.1。
- README 记载 50 Ω±5% 与 11.55 mil microstrip；此值只适配所述具体堆叠，不能转抄为嘉立创叠层规则。

适用限制：
- 这是宽带软件无线电，不是常规 MCU 控制器；包含敏感 RF/USB，案例只用于层序/约束结构和原始工程解析。
- 这是仓库 READM​​E 中的制造备注，与当前 PCB 文件所有参数未独立做生产/阻抗实测验证。
- 未在嘉立创专业版导入，也未跑阻抗场求解器/制造 DFM。

本地证据：`research/cases/snapshots/hackrf-one-readme.txt`；SHA-256：`28db488a377158cc39954d2bf18bbf788fac03467462e1cb686faca2990048ae`。权利信息：该仓库声明 CERN-OHL-P v2 Permissive；实际复用需遵守该许可并保留声明。。

## case-hackrf-one-pcb

[Great Scott Gadgets HackRF One — KiCad PCB source](https://github.com/greatscottgadgets/hackrf/blob/master/hardware/hackrf-one/hackrf-one.kicad_pcb)

读取时间：2026-11-21T08:31:52.968505+00:00。

具体主张：
- KiCad 文件 version 20211014。
- 实际解析四层：F.Cu=C1F、In1.Cu=C2、In2.Cu=C3、B.Cu=C4B；板厚记录 1.6116 mm。
- 顶层解析出 437 footprints、3817 track segments、498 vias、380 net 定义、9 zones。

适用限制：
- 不是普通 MCU 控制板的简化模板；不能把 RF/电源分割示例未经判断照搬。
- 结构解析仅统计树顶层对象；未运行 KiCad DRC，也未验证原理图-板全网一致性。
- 不能依据通用 KiCad 可解析推断嘉立创原生可往返。

本地证据：`research/cases/snapshots/hackrf-one-pcb.kicad_pcb`；SHA-256：`558d73553c7c2b2ae77dad541c87e671f3b2e982306f25e6fabed8d1e879e438`。权利信息：CERN-OHL-P v2 Permissive，以仓库 LICENSE 为准。。

## case-hackrf-one-mcu-sch

[Great Scott Gadgets HackRF One — MCU schematic sheet](https://api.github.com/repos/greatscottgadgets/hackrf/git/blobs/087ea542647b7faed4cab376cb07fd8ca0586ea9)

读取时间：2026-11-21T08:25:08.182290+00:00。

具体主张：
- 仓库列为 PCB 对应 MCU 原理图页（mcu.kicad_sch），可作为工程关系追溯来源。

适用限制：
- 未解析整张多文件层次原理图，也未完成 PCB 对应所有层次页的整体连通性检查。

本地证据：`research/cases/snapshots/hackrf-one-mcu-sch.kicad_sch`；SHA-256：`de07470d47e1ab10fc6d69788aaff081043870711618897e0d83a8f0437666fa`。权利信息：CERN-OHL-P v2 Permissive。。

## case-hackrf-one-license

[Great Scott Gadgets HackRF One — CERN-OHL-P license](https://api.github.com/repos/greatscottgadgets/hackrf/git/blobs/47cbf15e5fd99625f79546a3261b9f3f3e0d9111)

读取时间：2026-11-21T08:24:42.153759+00:00。

具体主张：
- LICENSE 明确为 CERN-OHL-P v2。

适用限制：
- 条款对 covered source、署名和再分发要求需在采用源设计前逐条复核。

本地证据：`research/cases/snapshots/hackrf-one-license.txt`；SHA-256：`2ee68e63fd7f724c9d6a42a517bec9d451dca2234c9024882cc4faeaed95e499`。权利信息：CERN Open Hardware Licence v2 - Permissive。。

## case-adafruit-f405-pcb

[Adafruit Feather STM32F405 Express — Eagle board (two-layer identification negative case)](https://api.github.com/repos/adafruit/Adafruit-Feather-STM32F405-Express-PCB/git/blobs/0e9032b73f3c8115bd2fc594a8071e7838fc931c)

读取时间：2026-11-21T08:38:07.085033+00:00。

具体主张：
- Actual Eagle XML contains designrules layerSetup=(1*16), 588 signal wires on layer 1, and 227 on layer 16; each layer has one polygon. Thus the file demonstrates a two-layer board, not 16 copper layers.
- Actual board includes an STM32F405R component and USB D+/D− signals.

适用限制：
- Used only to test actual-layer parsing, not as a design to copy.
- Did not run Adafruit Eagle DRC or re-manufacture the board.

本地证据：`research/cases/snapshots/adafruit-f405-pcb.brd`；SHA-256：`9357dc1dddde01fd5e93a1eebd5ae37742d1e55f0dd7190d0b39456d39b1df5b`。权利信息：CC BY-SA 3.0; README requires attribution and ShareAlike.。

## case-adafruit-f405-license

[Adafruit Feather STM32F405 Express — license](https://api.github.com/repos/adafruit/Adafruit-Feather-STM32F405-Express-PCB/git/blobs/1d1e1d6e88579dd32086b23e95723a0f4864c22a)

读取时间：2026-11-21T08:38:07.085743+00:00。

具体主张：
- Repo license text states Creative Commons Attribution-ShareAlike 3.0 Unported.

适用限制：
- Review full ShareAlike and attribution requirements before reusing or adapting board content.

本地证据：`research/cases/snapshots/adafruit-f405-license.txt`；SHA-256：`075dad5e5fc96c27014fabc269f4f5732909cffd178a486f546d982b6cf86b74`。权利信息：CC BY-SA 3.0.。

## case-adafruit-f405-readme

[Adafruit Feather STM32F405 Express — README](https://api.github.com/repos/adafruit/Adafruit-Feather-STM32F405-Express-PCB/git/blobs/db5bace27c3022cf7753bcf9f98078bb491331cf)

读取时间：2026-11-21T08:38:07.086748+00:00。

具体主张：
- README identifies the project as Eagle schematic and board-layout design files, and describes STM32F405 Cortex-M4, USB-C and SDIO.

适用限制：
- General product prose is not fabrication/DRC evidence.

本地证据：`research/cases/snapshots/adafruit-f405-readme.md`；SHA-256：`0ad7e1e2641e58a8aa9e8bb7e4d280b1096ef7eff49a05d0abfb09af98bf1778`。权利信息：CC BY-SA 3.0; README demands attribution and includes conditions on redistribution.。

## 关联知识

- [原理图到 PCB](../concepts/schematic-to-pcb.md)
- [多层参考与回流](../concepts/stackup-and-return.md)
- [单位与几何](../concepts/units-and-geometry.md)
- [验证与制造](../concepts/verification.md)
