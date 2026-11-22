# 嘉立创 EDA 专业版：原理图到四层 MCU PCB 的接口与工作流研究

研究日期：2026-11-21。目标：Codex 调用的 PCB 工程技能，首个验证对象为嘉立创 EDA 专业版四层 MCU 控制板。以下是实际读取官方文档、GitHub 官方仓库和固定 npm 类型包后的结论；随后在嘉立创 EDA Pro 4.1.100 的独立空 headless 会话中验证了 CLI/doctor/session 与固定环境观察。没有操作用户原工程，未完成任何真实 PCB 的布局、布线、DRC 或打样。

## 1. 可复用的官方连接方案

嘉立创已经提供 **客户端内置 CLI/MCP**，也发布了 **Run API Gateway** 和配套 **easyeda-api Skill**。适配顺序应为：有客户端 V4.1.60+ 时优先原生 CLI/MCP；网页版或不支持 CLI 的旧客户端使用官方网关。PCB 项目应复用这些连接机制，把自己的工作集中在电气约束提取、四层板布局布线决策、工程知识检索和设计验证。

| 官方项目 | 本次核验的证据 | 适合本项目的用途 | 限制 |
| --- | --- | --- | --- |
| [客户端内置 CLI/MCP](https://prodocs.lceda.cn/cn/api/guide/cli.html) | 中文人类指南、官方 AI CLI 文本；本机嘉立创 EDA Pro 4.1.100 `doctor`/`session list`/固定环境 action 实测 | 原生管理工程会话、查询当前 API、执行固定 action，提供 MCP stdio/http | 仅客户端支持；本轮只验证空 headless 会话，未把用户工程导入或执行板级 DRC |
| [easyeda/eext-run-api-gateway](https://github.com/easyeda/eext-run-api-gateway) | README、extension.json、src/index.ts 已读取；版本 1.0.9；Apache-2.0 | 在 EDA 进程中执行 API，并把结果交给本地桥接服务 | manifest 声明 `engines.eda: ~3.2.0`，不能据此保证所有 4.x 新 API 可用；还需实际客户端测试 |
| [easyeda/easyeda-api-skill](https://github.com/easyeda/easyeda-api-skill) | README、package.json、scripts/bridge-server.mjs 已读取；package 版本 1.1.85 | 官方 API 文档、HTTP/WS Bridge、现有 AgentSkills 集成 | package 未声明 license，GitHub 元数据也未识别许可；暂仅引用，不内嵌重分发 |
| [easyeda/easyeda-api-sdk](https://github.com/easyeda/easyeda-api-sdk) | package.json 与 LICENSE 已读取；SDK 1.6.31，Apache-2.0，Node >=20.17.0 | 将来需要自有 `.eext` 时使用官方 SDK 构建 | 研究阶段没有运行 npm install 或生成可安装 `.eext` |
| [@jlceda/pro-api-types](https://www.npmjs.com/package/@jlceda/pro-api-types) | npm 元数据和 0.4.30 发布包内 index.d.ts 已读取 | 对接口签名和版本注释作交叉核验 | 类型存在不证明用户安装版本已经实现 |

来源记录：`eda-pro-cli`、`eda-ai-cli`、`eda-gateway-readme`、`eda-gateway-manifest`、`eda-gateway-source`、`eda-api-skill-readme`、`eda-api-skill-package`、`eda-api-skill-server`、`eda-sdk-package`、`eda-sdk-license`、`eda-types-npm`、`eda-types-package`，见 [来源清单](sources.json)。

### 1.1 新版客户端的推荐入口：CLI/MCP

中文版命令为 `lceda-pro`，Windows 常见安装位置为 `C:\Program Files\lceda-pro\lceda-pro.exe`。国际版命令为 `easyeda-pro`，官方 AI 指南给出 `C:\Program Files\EasyEDA-Pro\easyeda-pro.exe`。官方说明安装器通常会把目录加入 PATH；找不到命令时先确认实际安装位置，可使用完整路径，不需要为研究任务改变系统配置。

原生客户端支持 `doctor`、`session list`、`open --path <工程路径>`、`invoke --session <会话ID>`、`doc api`、`doc format`，以及 `--mcp stdio` / `--mcp http`。浏览器版不支持这套 CLI 会话机制。CLI 可查询运行版本中的方法和参数，因此比只依赖最新在线文档更适合做兼容性判断。

`doctor` 的成功输出封套为 `{ok: true, value: {...}, logs: [], durationMs: ...}`，value 里包含 endpoint、connected、bridgeVersion、versionMatch、resultChannel。**ok=true 且 connected=false 仍表示没有连接编辑器**。业务调用同理：外层 ok 只证明命令执行状态，value 返回 false、undefined、未完成作业或未落盘文件时，不能报设计成功。失败封套含 `{ok: false, error: {code, message}}`。

`session list` 列出 sessionId、renderId、origin、path、title 等。后续 invoke 必须显式固定目标 sessionId，并再次核对目标工程/PCB 身份；用户原有窗口与本流程创建的窗口要区分。只清理由本流程创建且已完成保存验证的会话，不能顺手关闭用户原有会话。`.eprj3` 文件夹工程可与编辑器双向同步，但 save 返回后仍应在磁盘核验产物及内容。

本轮实际运行了独立 headless 会话的 `doctor`、`session list` 和固定 `inspect_environment`。本地副本导入调用被在线客户端拒绝，未改变源工程；该失败不证明用户工程无法在其离线/可导入环境中打开。

### 1.2 网页版及旧客户端的备用入口：官方 Bridge

实际官方桥接链路为：AI 工具通过 HTTP 或 WebSocket 把请求发送到本机 Bridge；Gateway 通过 `eda.sys_WebSocket` 连接 Bridge，再在 EDA 环境里执行请求。源码确认服务仅监听 `127.0.0.1`，扫描端口范围 49620–49629，以 `service: easyeda-bridge` 标识服务。`GET /health` 可发现连接状态，`GET /eda-windows` 可枚举窗口，`POST /execute` 支持 `code` 和可选 `windowId`。**windowId 应显式选定并与目标工程核对**，不能依赖用户最后激活的窗口来修改 PCB。

上述握手的 service 字段是服务识别标识，不是对设计意图或板子质量的验证。PCB 层应只开放约束明确的操作，保留工程身份、输入与结果记录。网关本身可以执行任意传入代码；“网关已连通”不等于“板子已通过工程审查”。本次只读取源码，没有安装或启动服务。

## 2. 原理图到 PCB：先建立准确的工程关联

官方 [原理图转 PCB](https://prodocs.lceda.cn/cn/schematic/design-update-convert-schematic-to-pcb/) 和 [从原理图导入变更](https://prodocs.lceda.cn/cn/pcb/design-import-changes-from-schematic/) 文档说明，原理图与 PCB 正常关联在同一个 Board 下。导入会核验原理图和封装，不能仅凭封装显示名称来匹配器件。

进入布局前必须核对：

1. 元件位号唯一；符号库引脚编号、PCB 焊盘编号及数量匹配；封装通过封装管理器关联了实际唯一标识。
2. MCU 电源引脚、地引脚、复位、启动配置、晶振、调试口、USB 或其他接口的网络关系以结构化网表为准。截图可以帮助辨认分组，不能替代网络连接真值。
3. 明确目标工程 UUID、Board、原理图 UUID、PCB UUID 和当前文档身份。创建或打开工程不代表画布 API 已就绪。
4. 初次导入与后续 ECO 分开处理：已有 PCB 应导入差异，不另造一块与原设计失联的 PCB。

官方 `eda.pcb_Document.importChanges(uuid?: string): Promise<boolean>` 可从原理图导入变更。缺省 UUID 使用同 Board 关联原理图；失败或没有关联原理图的游离 PCB 返回 false。导入动作是否出现确认弹窗、具体版本是否可自动执行，仍需运行时测试。

**重要变更风险**：原理图网络变更后，原走线可能仍然保留；“同时更新导线的网络”也不保证增删器件后的旧线自动满足新连接。官方还说明部分导入变更无法撤销。因此导入前保存可恢复副本，导入后重新比较网络、焊盘归属和实际连接，不能只检查函数返回 true。来源：`eda-pro-schematic-to-pcb`、`eda-pro-import-changes`、`eda-pro-import-changes-api`。

## 3. 已核验的 API 清单与能力边界

此表记录文档能力，**不是本项目已经实现的适配器清单**。方法调用统一 await，并校验返回值、上下文及错误；BETA API 应先在测试工程核验。

| 工程需求 | 官方 API / 类型 | 本次确认的边界 |
| --- | --- | --- |
| 读取原理图网表 | `eda.sch_Netlist.getNetlist(type)` | 有正式类文档；类型和目标画布必须明确 |
| 导入原理图变更 | `eda.pcb_Document.importChanges(uuid?)` | Promise<boolean>；失败 false；force 参数存在文档矛盾，见后文 |
| 读取 PCB 网络 | `eda.pcb_Net.getAllNets()`、`getNetlist(type)`、`getAllPrimitivesByNet(net, primitiveTypes)` | 可查网络，不代表几何已连通；BETA/当前文档约束仍要核验 |
| 对比网络 | `eda.sys_Tool.netlistComparison(netlist1, netlist2)` | 有官方方法；不能替代 DRC 和器件数据手册审查 |
| 读取器件及其焊盘 | `eda.pcb_PrimitiveComponent.getAll()`、`getAllPinsByPrimitiveId(primitiveId)` | 用于位号、封装、焊盘和网络对应；不要按显示顺序匹配 |
| 放置/移动器件 | `eda.pcb_PrimitiveComponent.create(...)`、`modify(primitiveId, property)` | 有接口，不代表知道满足机械、电气和装配约束的位置 |
| 读取层与叠层 | `eda.pcb_Layer.getAllLayers()`、`getStackup()` | 铜层数、启用状态、层类型与物理叠层要分别处理 |
| 设置层数 | `eda.pcb_Layer.setTheNumberOfCopperLayers(numberOfLayers)` | 不能硬编码所有环境里内层 ID/类型都相同 |
| 网络化走线 | `eda.pcb_PrimitiveLine.create(net, layer, startX, startY, endX, endY, lineWidth, primitiveLock)` | 导线必须有真实网络和层归属，不是绘制任意装饰线 |
| 网络化过孔 | `eda.pcb_PrimitiveVia.create(net, x, y, holeDiameter, diameter, viaType, ...)` | 通孔/盲埋孔、孔径/盘径/连接层要服从所选工艺 |
| 原生自动布局/布线 | `eda.pcb_Document.autoLayout()`、`autoRouting(props?)` | 在 PCB_Document，不在 PCB_Tool；布线结果还需完整工程检查 |
| 长作业控制 | `startAutoRouting(props?)`、`getAutoJobStatus(jobId)`、`getAutoJobLog(jobId)`、`cancelAutoJob(jobId)` | 作业模型文档标注 since 4.1.79；不能假设旧稳定版支持 |
| 剩余飞线 | `eda.pcb_Document.getRatlines(options?)` | 分页只读，since 4.1.93；必须取完所有页，不能用第一页推断总数 |
| 网络类与差分对 | `eda.pcb_Drc.createNetClass(...)`、`createDifferentialPair(...)` | 分类和约束配置必须来自当前电路、器件和制造要求 |
| 新执行完整 DRC | `eda.pcb_Drc.checkDetailed(options?)` | Promise<IPCB_DrcResult>；BETA；since 4.1.93；不完整结果必须失败 |
| 读取最近 DRC | `eda.pcb_Drc.getDrcResult()` | 不会重新检查，可能是旧结果或 notChecked |
| 规则写入 | `overwriteCurrentRuleConfiguration(...)`、`overwriteNetRules(...)` 等 | 必须先读取规则形状并保存旧值，不能凭猜测构造对象 |
| 命令组 | `beginCommandGroup`、`commitCommandGroup`、`rollbackCommandGroup` | since 4.1.93；同一时间只允许一个打开组；不视为一切操作可撤销 |
| 导出制造数据 | `eda.pcb_ManufactureData.getGerberFile(...)`、`getBomFile(...)`、`getPickAndPlaceFile(...)` | 能导出文件不证明文件内容正确；另有快捷下单接口，本阶段不调用 |
| 与外部布线器互通 | `getDsnFile(...)`、`importAutoRouteSesFile(...)` | 有官方导出/导入入口；未实际验证外部路由器格式往返 |
| 源数据无画布 PCB | `eda.dmt_SourcePcb` | 官方明确当前所有方法返回 NOT_IMPLEMENTED，不可作为现成后台 PCB 引擎 |

对应 source IDs 以 `eda-pro-*-api` 为主，详见 [机器可读来源记录](sources.json)。所有名为 Source 的接口不能一概认定已实现，必须查看该类的具体状态。

自动布线的精确限制：`autoRouting(props?: IPCB_AutoRoutingProps): Promise<IPCB_AutoRoutingResult>`，文档标注 since **3.2.150 / 4.1.66**。它有固定 900 秒硬上限；超时/失败时中间几何不会提交，外层 CLI 延长 timeout 不能覆盖该上限；`props.layers` 中停用层会被忽略。`success` 描述布线流程结果，布通率来自 successNetsCount / totalNetsCount，不能当作 DRC 通过或功能正确的证据。较新 `startAutoRouting` 返回作业句柄，适合可查询、可取消的长作业，但仍须核对实际版本和结果提交状态。来源：`eda-pro-auto-routing-api`、`eda-pro-start-auto-routing-api`。

## 4. 四层板最容易误判的 EDA 语义

官方 [图层管理器](https://prodocs.lceda.cn/cn/pcb/tools-layer-manager/) 与 [设计规则](https://prodocs.lceda.cn/cn/pcb/design-design-rule/) 文档提供以下直接影响插件决策的细节：

- **四层是铜箔层数**。丝印、阻焊、锡膏、板框、文档、飞线和孔显示层不计入铜层。内层既可为信号层，也可配置为内电层，必须读取实际类型。
- **内电层编辑采用负片语义**，线条可能表示去铜；导出 Gerber 时转换成正片。不能把画布图元面积直接当作铜面积，也不能看到“线”就认定它连通。
- **内电层分割完成要重建**。文档明确专业版不自动重建内电层；需要手动重建或重建全部铺铜。在缺乏可验证重建结果的版本中应报告人工步骤，不能假定铺铜已经计算完成。
- **负片分割与正片导线不是同一图元语义**。内电层分割使用折线、闭合回路；不是在内层画普通网络导线。
- **EDA 中记录的物理叠层不决定制造叠层**。文档说明物理堆叠当前不参与阻抗计算、不影响 Gerber；下单时仍需重新选择实际叠层。由此不能把设置了 L1/L2/L3/L4 当作已经获得某阻抗。
- **规则可以按层、网络类、网络-网络、区域设置**，并涉及安全间距、导线、过孔、平面、阻焊和锡膏。插件不能只有一个全局线宽和一个全局间距。
- **内电层热焊盘连接方式**包含发散、直连和无连接；铺铜也有连接语义。视觉接触不等于网络实际连接，必须重建并检查连接性。
- **盲埋孔必须先建立对应规则和层对**，不能因为是四层板就默认可以用任意盲孔。第一阶段应先以制造商明确支持的通孔工艺验证闭环。
- **机械层默认不是制造板框**，真正外形来自边框层及 Gerber_BoardOutline.GKO。MCU 板的接口位置、孔位、板框闭合和禁布区域应先锁定，再进行布局。

**单位与坐标必须显式转换**。官方 CLI 指南的单位表规定：原理图以 **10mil** 为单位，原点在图纸左下角、Y 向上；PCB 以 **mil** 为单位。1mil=0.0254mm，因此工程层使用 mm 时，要在适配器边界转换，不能把 mm 值直接传入 PCB API，也不能把 SCH 坐标直接用于 PCB。API 角度逆时针为正；原理图源文件 COMPONENT.rotation 与 API 使用 `(360-angle)%360` 的转换，PCB COMPONENT.angle 则同向。移动画布原点还会带来画布坐标与数据坐标差异，应使用对应转换接口或始终保持一致数据坐标。来源：`eda-pro-cli`、`eda-ai-cli`、`eda-pro-document-api`。

导线创建接口的官方说明还指出：板框层须使用 Polyline；导线与已有图元相交时会由原生引擎分割，一定数量的创建调用可能产生不同数量的线段。因此几何验收应检查端点/连接/形状与网络，不能只比线段数量。过孔 API 的官方示例明确以 mil 解释孔径和盘径。来源：`eda-pro-line-create`、`eda-pro-via-create`。

这些只是软件语义；回流路径、PDN、去耦、晶振、热设计、USB 阻抗与制造裕量仍需结合器件和板厂资料形成工程约束。

## 5. 检查与制造文件验收

`checkDetailed` 的已核验返回字段为 `state`、`failedItems`、`totalCount`、`violations`，另有可选 `checkedAt` 和分组统计。state 可以是 notChecked、checking、passed、failed、incomplete。只有明确完成、结果完整且满足项目规则才可视为 DRC 通过。`INCOMPLETE_RESULT` 异常、failedItems > 0、不完整状态、尚未检查、仍在检查或旧时间戳都不能被解释成零错误。来源：`eda-pro-drc-detailed`、`eda-pro-drc-result`。

原生 DRC 依据已配置规则运行，无法自动替代规则本身的正确性。实时 DRC 也不能代替最终完整 DRC：官方用户指南写明实时模式存在不提示的对象类别，部分规则不支持实时检查。完成布线后重建铺铜/内电层，重新查网络一致性与剩余飞线，再运行最终 DRC。来源：`eda-pro-ui-drc`。

官方 [Gerber 导出指南](https://prodocs.lceda.cn/cn/pcb/export-pcb-fabrication-file-gerber/) 说明了四层板应关注的内容：

- 顶/底铜层、两张内层、板框、阻焊、丝印与所需钻孔文件分别核对；PTH、NPTH 和盲埋孔钻孔文件分开识别。
- 内电层在当前输出中为正片 G+数字，较老版本曾使用 GP+数字，不能只看扩展名猜测极性。
- 钻孔单位/坐标精度设置可能引起查看器错位；需要检查导出参数和 CAM 解析配置，不要直接移动钻孔几何“补偿”。
- Gerber 的孔数、板框、铜层顺序、孤岛、阻焊开窗及内层连接应在独立查看器或嘉立创 DFM 中检查。
- Gerber 自定义导出配置与“PCB 下单”按钮的默认一键导出行为不同。为保证交付与报价所用文件一致，应记录实际导出的压缩包和配置，而不是假定按钮用了刚才选择的自定义设置。
- EDA 的 Gerber、BOM、坐标等导出接口应只生成可审查产物；本次研究没有登录、上传私有电路或执行下单。

## 6. 文档冲突与需要保留的不确定性

| 问题 | 本次读取到的冲突/缺口 | 本项目应采用的处理 |
| --- | --- | --- |
| 连接方式与产品版本 | 新客户端内置 CLI/MCP，网页版和旧版文档主要使用扩展 Bridge | 客户端>=4.1.60优先原生 CLI/MCP，Bridge 备用；不要要求所有用户安装同一连接插件 |
| importChanges 的 force 参数 | 备注建议 force=true，但方法签名和固定 types 0.4.30 都只有 uuid? | 记录冲突，不凭备注发送未定义参数；测试工程按实际版本核验，保留交互确认通路 |
| Node 最低版本 | 人类开发指南写 >=20.5.0；AI 指南和 SDK 1.6.31 package 写 >=20.17.0 | 对此 SDK 以 package engines 为准；不改系统环境来满足研究任务 |
| 官方 Skill 服务脚本路径 | README 树中仍写 server/index.mjs；真实 package 的 npm run server 指向 scripts/bridge-server.mjs | 以 package 与实际源码为准，不复制陈旧命令 |
| 网关与较新 API 版本 | Gateway manifest 是 ~3.2.0，当前文档包含 4.1.93/4.1.103 之后接口 | 分别记录网关、EDA、类型版本；网关能连通不代表所有新方法存在 |
| PCB_Tool 页面无方法 | 该类页只有签名，容易误认为不存在自动布线 API | 自动布线应查 PCB_Document，不能从空类页推断整个产品能力 |
| DMT_SourcePcb 有类和类型 | 官方明确所有方法仍 NOT_IMPLEMENTED | 功能状态默认 unsupported；不把类型声明当作实现 |
| 文件格式协议 | Pro 官方同时发布 v2.2 和 v3 格式，含文档头、ticket 与删除记录等语义 | 每次导入先识别格式版本，保留对象 ID 和一致性语义，不套用标准版 JSON |
| 授权范围 | 多数网页公开可访问；官方 Skill repo 未给出已确认的统一开源许可证 | 保留链接与原创总结，完整快照仅本地；实际复用代码前核实 LICENSE/NOTICE |

## 7. 最小能力探测与第一块板的验收建议

适配器最先做只读探测，不要以改线来验证连接：发现客户端 CLI/MCP 或备用 Bridge → 识别会话/窗口 → 核对工程与文档 → 获取元件、网表、层、叠层与规则 → 记录版本和能力。`typeof method === 'function'` 只证明方法存在，不证明功能实现；需实际只读返回或测试工程验证。不要探测时启动自动布线、导入原理图变更或调用下单接口。

建议 capability 名称及证据：

| capability | 证据与降级方式 |
| --- | --- |
| read_project_identity | 当前工程、Board、PCB UUID 可确定，重连后仍核对 |
| read_schematic_connectivity | 已读取目标原理图的结构化网表，保留 pin/pad 对应 |
| read_pcb_geometry | 已读取元件、焊盘、导线、过孔和板框，单位与原点明确 |
| read_layers_and_stackup | 实际铜层数、启用状态、内层类型和物理记录可读 |
| inspect_rules | 当前规则及网络/区域分配可读；未知字段不能自动覆盖 |
| import_changes | 已在测试工程验证导入行为、关联与错误；未验证时保持人工原生导入 |
| native_auto_route | EDA 4.1.100 空会话确认方法存在，真实PCB路由结果尚未运行 |
| native_auto_route_job | 空会话实测 start/getStatus/getLog/cancel 方法存在，job/partial行为仍待真实副本实测 |
| count_unrouted | 固定action分页读取ratlines，mock多页回归通过，真实板结果未验证 |
| full_drc_details | checkDetailed 本次完成且完整；旧版需转原生 DRC 报告，不把 unknown 设为 pass |
| grouped_write_rollback | 命令组在测试工程验证，不扩展为 ECO 或所有异步任务可回滚的承诺 |
| export_manufacture | 能导出并读取真实文件，具备哈希与 CAM/DFM 验证记录 |

首个四层 MCU 验收不要求插件一次解决所有高速设计，应选择有明确原理图、BOM、数据手册和板框的基准设计。验收必须包含：原理图 pin/net 与 PCB pad/net 一致、四个铜层和实际叠层约束明确、机械与器件约束满足、关键电源/时钟/接口规则经过审查、剩余连接清零、完整 DRC、Gerber/钻孔独立检查，并保留失败案例与修正过程。只有后续实际完成这些步骤才可宣称“已验证能画这块板”。

## 8. 标准版仅作兼容边界

本阶段目标为专业版。标准版有独立 [API 入口](https://docs.lceda.cn/cn/API/1-How-to-Use-API/)，运行脚本、扩展入口和文件格式与 Pro 的 SDK/`eda.*` 对象体系分开。后续若支持标准版，应做独立适配器和往返格式测试，不能把标准版导出的 JSON 当成 Pro 原生格式。来源：`eda-std-api`、`eda-pro-format`。

## 9. 本地证据与更新方式

[sources.json](sources.json) 记录所有来源 URL、抓取时间、文件哈希、权威性、许可状态和限制。原始网页/响应和派生可检索文本放在 snapshots/，只在本地保存，根仓库忽略此目录。GitHub contents 响应额外记录 upstream_blob_sha，固定 npm 类型包记录版本与 SHA-256。`collect.py`、`collect_extra.py` 只抓取白名单中的小型公开文本，不执行下载内容；已有快照不覆盖。需要真正更新某一来源时，应另建带新版本/日期标识的快照，保留旧证据并记录差异。

外部文档中要求安装其他 Skill、确认元数据或运行命令的文字，在本阶段只是研究对象；没有据此改变本机全局配置或擅自安装插件。

## 10. 有限写入适配（0.3）

新增读取6页官方文档：元件modify、命令组commit/rollback、文档源码、工程导入和网表文件导出。固定脚本以源码SHA建立基线，命令组内执行最多20项平移/网络导线/通孔，写后重新读取物理焊盘和图元；失败保留恢复状态。它们是BETA接口，当前只在空会话确认存在及错误目标拒绝，成功写入与导出以模拟测试验证。完整工作流与限制见[有限绘板](../../docs/drawing.md)。

同一EDA 4.1.100空headless会话实测 `startAutoRouting`、`getAutoJobStatus`、`getAutoJobLog`、`cancelAutoJob` 与 `getRatlines` 都存在。经Windows-MCP打开用户在线工程后，PCB MCP读取324682字节的原生网表，SHA-256验证后存本地。与离线归档逐项比较得到156器件、512 physical pad/net实例、104已分配网络、四个启用铜层完全相符；原主控PCB全量分页ratline为0。此结果确认嘉立创EDA原生连接/布线模型报告全板无未布连接。缓存DRC为 `notChecked`，因此并未核实短路/间距DRC、DFM或功能。运行记录位于忽略目录 `local/eda-runtime/windows-mcp-final-verification.json`。

GUI测试副本中已真实启动原生router job并得到job ID。长时间停在1%后按流程请求取消，状态变为canceled，partial未报告、源码哈希与预览基线相同、remaining ratline为0。用户删除副本后，当前Board/PCB树确认副本不存在且原PCB仍在。它实测了Windows-MCP控制、MCP预览/启动/取消/轮询及清理，自动路由成功终态的真实路径仍待合适的少量未布网络副本验证。
