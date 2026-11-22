"""Capture the publicly accessible official EDA documents used by this study.

Existing snapshots are immutable; reruns reuse them. This is research tooling,
not an installed EDA plugin and it does not connect to a user's editor.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = "https://prodocs.lceda.cn/cn/"
PAGES = [
    ("eda-pro-start", "api/guide/how-to-start.html", "扩展运行范围、SDK、导入位置与开发环境"),
    ("eda-pro-types", "api/guide/ancillary-projects/pro-api-types.html", "官方 TypeScript 类型包与 Apache-2.0 许可"),
    ("eda-pro-cli", "api/guide/cli.html", "客户端 V4.1.60+ 内置 CLI 与 MCP，区别于网页版扩展桥接"),
    ("eda-pro-invoke", "api/guide/invoke-apis.html", "eda 命名空间及扩展 API 的调用规则"),
    ("eda-pro-schematic-to-pcb", "schematic/design-update-convert-schematic-to-pcb/", "原理图更新及转换 PCB 的原生操作"),
    ("eda-pro-import-changes", "pcb/design-import-changes-from-schematic/", "从原理图导入更改与匹配"),
    ("eda-pro-layer-manager", "pcb/tools-layer-manager/", "图层管理与内层配置"),
    ("eda-pro-design-rule", "pcb/design-design-rule/", "PCB 规则配置与规则优先级"),
    ("eda-pro-ui-drc", "pcb/design-check-drc/", "原生 DRC 检查流程"),
    ("eda-pro-gerber", "pcb/export-pcb-fabrication-file-gerber/", "制板 Gerber 导出与检查"),
    ("eda-pro-format", "format/index/", "Pro 文件格式版本与最终一致性语义"),
    ("eda-pro-layer-api", "api/reference/pro-api.pcb_layer.html", "层数、图层和物理叠层 API"),
    ("eda-pro-net-api", "api/reference/pro-api.pcb_net.html", "网络和 PCB 网表 API"),
    ("eda-pro-component-api", "api/reference/pro-api.pcb_primitivecomponent.html", "元件与其焊盘的图元查询及修改"),
    ("eda-pro-line-api", "api/reference/pro-api.pcb_primitiveline.html", "具备网络和层标识的导线图元"),
    ("eda-pro-via-api", "api/reference/pro-api.pcb_primitivevia.html", "具备网络、孔径、盘径和类型的过孔"),
    ("eda-pro-line-create", "api/reference/pro-api.pcb_primitiveline.create.html", "导线创建详细签名、mil 示例及原生分割语义"),
    ("eda-pro-via-create", "api/reference/pro-api.pcb_primitivevia.create.html", "过孔创建详细签名及 mil 尺寸示例"),
    ("eda-pro-drc-api", "api/reference/pro-api.pcb_drc.html", "规则组、差分对和 DRC API"),
    ("eda-pro-drc-detailed", "api/reference/pro-api.pcb_drc.checkdetailed.html", "checkDetailed 的真实返回签名"),
    ("eda-pro-drc-result", "api/reference/pro-api.ipcb_drcresult.html", "DRC 返回状态、时间和明细"),
    ("eda-pro-manufacture-api", "api/reference/pro-api.pcb_manufacturedata.html", "Gerber、BOM、坐标及 DSN 导出"),
    ("eda-pro-sch-netlist-api", "api/reference/pro-api.sch_netlist.html", "原理图网表读取与修改"),
    ("eda-pro-comparison-api", "api/reference/pro-api.sys_tool.html", "网表、PCB 和原理图对比"),
    ("eda-pro-websocket-api", "api/reference/pro-api.sys_websocket.html", "扩展通过 WebSocket 与外部服务交互"),
    ("eda-pro-source-pcb", "api/reference/pro-api.dmt_sourcepcb.html", "源数据 PCB API 当前明确为 NOT_IMPLEMENTED"),
    ("eda-pro-tool-api", "api/reference/pro-api.pcb_tool.html", "PCB_Tool 页面目前没有已公开方法列表"),
    ("eda-pro-document-api", "api/reference/pro-api.pcb_document.html", "PCB_Document 包含自动布局布线、导入变更、飞线及命令组"),
    ("eda-pro-import-changes-api", "api/reference/pro-api.pcb_document.importchanges.html", "从原理图导入变更的真实签名"),
    ("eda-pro-auto-routing-api", "api/reference/pro-api.pcb_document.autorouting.html", "原生自动布线方法及其返回值"),
    ("eda-pro-start-auto-routing-api", "api/reference/pro-api.pcb_document.startautorouting.html", "自动布线作业模型及版本要求"),
    ("eda-pro-ratlines-api", "api/reference/pro-api.pcb_document.getratlines.html", "分页读取未完成连接的飞线"),
    ("eda-pro-command-group-api", "api/reference/pro-api.pcb_document.begincommandgroup.html", "命令组的版本与回滚边界"),
    ("eda-std-api", "https://docs.lceda.cn/cn/API/1-How-to-Use-API/", "标准版 API 入口，与 Pro 并非同一 API"),
]


def main_text(source: str) -> str:
    source = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", source, flags=re.S | re.I)
    match = re.search(r"<main\b[^>]*>(.*?)</main>", source, re.S)
    source = match.group(1) if match else source
    source = re.sub(r"</(?:p|h\d|tr|li|pre|div|section)\s*>", "\n", source)
    source = html.unescape(re.sub(r"<[^>]+>", " ", source))
    return "\n".join(re.sub(r"\s+", " ", line).strip() for line in source.splitlines() if line.strip()) + "\n"


def collect(item: tuple[str, str, str]) -> dict:
    identifier, suffix, claim = item
    url = suffix if suffix.startswith("https://") else BASE + suffix
    dest = HERE / "snapshots" / (identifier + ".html")
    if not dest.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "PCB-research/0.1 (public documentation research)"})
        with urllib.request.urlopen(req, timeout=20) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError(f"snapshot too large: {identifier}")
        dest.write_bytes(data)
    data = dest.read_bytes()
    decoded = data.decode("utf-8")
    title_match = re.search(r"<title>(.*?)</title>", decoded, re.S)
    title = html.unescape(title_match.group(1)) if title_match else identifier
    extracted = dest.with_suffix(".txt")
    if not extracted.exists():
        extracted.write_text(main_text(decoded), encoding="utf-8")
    return {
        "id": identifier,
        "title": title,
        "url": url,
        "local_path": dest.relative_to(ROOT).as_posix(),
        "text_path": extracted.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "retrieved_at": datetime.fromtimestamp(dest.stat().st_mtime, timezone.utc).isoformat(),
        "authority": "嘉立创 EDA 官方文档（产品行为与 API 的一手资料）",
        "license_or_terms": "公开访问不等于开放许可；文档版权归原作者，仅作本项目研究证据，未据此授予再分发许可。",
        "claims": [claim],
        "limitations": ["已读取官方网页，未在用户安装的 EDA 中运行验证；BETA 接口应以运行时能力探测和当前类型版本为准。"],
    }


if __name__ == "__main__":
    (HERE / "snapshots").mkdir(parents=True, exist_ok=True)
    manifest = HERE / "sources.json"
    records = {record["id"]: record for record in json.loads(manifest.read_text(encoding="utf-8"))} if manifest.exists() else {}
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(collect, item): item for item in PAGES}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                records[result["id"]] = {**records.get(result["id"], {}), **result}
                print(result["id"], flush=True)
            except Exception as error:
                errors.append({"id": futures[future][0], "error": str(error)})
    records = sorted(records.values(), key=lambda record: record["id"])
    manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        (HERE / "collection-errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"captured": len(records), "errors": errors}, ensure_ascii=False))
