# 第三方资料与权利

`research/` 保存公开文档/仓库的研究快照与元数据；原始内容的版权、商标和许可证归各自权利人。具体链接、获取时间和许可核查见各主题 `sources.json` 及 `findings.md`。

**完整快照与提取文本仅保留本地，默认不提交 GitHub**。公开仓库发布来源清单、少量定位证据和原创总结。公开访问不构成额外复制许可；后续引入具体代码/工程时，核查对应文件和目录的许可证并保留归属。

项目自己的知识总结区分引用、转述、推导和尚未验证的建议。没有明确复制许可的工程只研究，不自动挪用设计文件、封装、商标、参考原理图或商业发布素材。

本仓库尚未为自有代码选择开源许可证；选定后应明确排除第三方存档，保留其既有许可和归属。GitHub 上公开可见不等于授予他人额外复用权。

新增的 STMicroelectronics AN4879（Rev 13，October 2026）和 Analog Devices MT-094（Rev 0，January 2009）直接来自厂商官方域名，记录于 `research/rules/sources.json`。它们仍保留厂商版权；本项目未确认全文再分发许可。完整 PDF、提取文本和证据页只保存在忽略的 `research/rules/snapshots/`，公开知识页仅包含原创综合和带定位的短摘录。下载到的文档若身份与标题不符，不纳入技术来源清单。


新增嘉立创有限写入API的6页公开文档和ADI MT-100教程，全文仅存Git忽略的快照目录。公开文件只包含来源元数据、10条短摘录与原创总结；未据此推定CAD/正文有开放再分发许可。

本机安装了 MIT 许可的 CursorTouch Windows-MCP 0.8.9，用于当前桌面UI自动化测试。Python 3.14虚拟环境、发行wheel及校验过的依赖都位于Git忽略的 local/windows-mcp*，仓库只含固定allowlist启动器和禁遥测配置，不复制第三方源码。许可证与项目说明来自PyPI元数据和 [CursorTouch/Windows-MCP](https://github.com/CursorTouch/Windows-MCP)。
