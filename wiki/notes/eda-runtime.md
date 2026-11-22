# EDA 运行时接入与证据边界

本页记录观察/DRC接口和运行时证据；0.3有限写入与自动路由见[绘板流程](../../docs/drawing.md)。接口依据为[官方CLI文档](https://prodocs.lceda.cn/cn/api/guide/cli.html)、固定 `@jlceda/pro-api-types` 0.4.30、官方Bridge源码和自动布线API，可在[接口来源页](../sources/eda-research.md)查到快照与定位。实现见[接入架构](../../docs/architecture.md)。

## 使用顺序

1. 先用 `pcb_eda_status`、`pcb_eda_sessions` 读取连接与现有会话。状态 `available` 只表示传输已连接；会话仍可能为 `closed`，不能选它作画布目标。
2. 用 `pcb_eda_inspect(session_id)` 读取版本、方法存在性、当前文档和 Board 树，再固定 `expected_project_uuid`、`expected_document_uuid`。SDK 的 Board item 没有独立 UUID；通过 `board.pcb.uuid` 关联，不虚构 Board UUID 字段。
3. `pcb_eda_connectivity` 额外要求 `pcb_uuid`。当前焦点必须是该 PCB，或其关联原理图的一张图页；工具不自动切换焦点、不导入或保存。PCB 单位 mil，原理图单位 10mil。返回物理焊盘分页，重复编号保留物理 ID；先取完 `next_pad_offset`，再换 `next_component_offset` 并重置 pad offset。
4. 原生 JLCEDA 网表上限 256 KiB，在忽略目录 `local/eda-snapshots/` 内容寻址保存，MCP 返回哈希与大小。原文不注入全部上下文；该观测未实现原理图/PCB等价比较或铜几何连通检查。
5. `pcb_eda_drc` 要求焦点就是目标 PCB。默认 `run=false` 只读缓存，永不通过门槛；明确 `run=true` 才调用 `checkDetailed`。运行会更新检查状态，不编辑设计或保存。只有完整、零失败规则、零违规且时间严格晚于触发的结果才可能通过窄范围 native gate。

CLI 退出码 0、外层 `ok:true`、HTTP 200、方法存在或一个空数组都不足以证明设计成功。Bridge 必须核实 `service=easyeda-bridge`、已连编辑器与 window ID，拒绝非 loopback、代理和重定向。MCP 只接受固定 action 参数，不接受用户 JavaScript。

原生路由先用 `pcb_route_preview` 选择准确PCB、已有网络和启用SIGNAL层。`pcb_route_start`固定45度、保留已有导线/过孔并优先布通率。用`pcb_route_status`查询job终态和全部分页剩余ratlines；`pcb_route_cancel`只发取消请求，仍需轮询终态。未知启动结果不可重试同一计划。

## Windows CLI 捕获

已安装客户端的帮助明确注明：Windows GUI 程序在 PowerShell 普通赋值或重定向时可能不返回 stdout，需要管道捕获。只读示例：

```powershell
& lceda-pro doctor | Out-String
& lceda-pro session list | Out-String
```

适配器使用 `subprocess.Popen` 的独立 stdout/stderr 管道、`shell=False`，实际验证可获得 JSON。空 stdout 仍按 unsupported 处理。缓存网页写 CLI 起始版本 4.1.60，本机安装包说明写 4.1.70；以安装版本的实际 help/doctor/action 结果判断能力，不把最低版本声明当兼容保证。

## 已执行和未执行

2026-11-21 在嘉立创 EDA Pro 4.1.100 新建独立空 headless 会话，实际验证 doctor、会话枚举、固定环境 action、MCP stdio 和错误目标拒绝，结束后关闭该测试会话。原始 CAD 哈希未变，没有修改用户设计。追加检查确认自动路由 start/status/log/cancel/ratline，以及 `crypto.subtle.digest`、`File.arrayBuffer` 在运行时存在。空会话没有 PCB，未启动布线作业。

该空会话处于在线模式；官方 `Offline Client Local Path` 导入明确报“非离线客户端环境无法调用”，没有生成本地副本。未据此上传用户工程到在线账户。需要后续选择可导入的离线测试副本，或由用户明确授权在线新建副本。

工程树、网表/物理焊盘/层和详细 DRC 的成功路径目前以 mock 验证，尚未在目标板上实测。时间戳单位/分辨率没有板级实测，含糊时不通过；SDK 未提供本轮可核实的内容修订号，同一文档在异步读取期间被编辑也无法证明原子快照。首次真实 PCB 验证时必须补齐这些证据，再进入[有限写入与首板验收](first-board-plan.md)。
