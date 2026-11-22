"""Capture small official repository/API records; never execute fetched code."""
import base64
import concurrent.futures
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ITEMS = [
    ("eda-sdk-package", "https://api.github.com/repos/easyeda/easyeda-api-sdk/contents/package.json", "SDK package 1.6.31 / Node >=20.17.0 / Apache-2.0 / types ^0.4.29", "Apache-2.0"),
    ("eda-sdk-license", "https://api.github.com/repos/easyeda/easyeda-api-sdk/contents/LICENSE", "SDK 授权原文", "Apache-2.0"),
    ("eda-gateway-readme", "https://api.github.com/repos/easyeda/eext-run-api-gateway/contents/README.md", "官方网关真实存在，说明扩展安装与自动连接流程", "Apache-2.0（仓库声明）"),
    ("eda-gateway-manifest", "https://api.github.com/repos/easyeda/eext-run-api-gateway/contents/extension.json", "网关 1.0.9 / eda ~3.2.0 / Run API Gateway", "Apache-2.0"),
    ("eda-gateway-source", "https://api.github.com/repos/easyeda/eext-run-api-gateway/contents/src/index.ts", "网关真实协议实现，用于研究待调用边界", "Apache-2.0（仓库声明）"),
    ("eda-api-skill-readme", "https://api.github.com/repos/easyeda/easyeda-api-skill/contents/README.md", "官方 Skill 的桥接 HTTP API、端口和文档结构", "未确认，GitHub 仓库元数据 license=null；不再分发其源码"),
    ("eda-api-skill-package", "https://api.github.com/repos/easyeda/easyeda-api-skill/contents/package.json", "官方 Skill 的软件包声明、Node 版本及依赖", "按 package.json 原文核实；不将声明扩展为每个文档授权"),
    ("eda-api-skill-server", "https://api.github.com/repos/easyeda/easyeda-api-skill/contents/scripts/bridge-server.mjs", "真实桥接服务实现，用于研究连接与错误边界", "未核实独立授权；快照仅本地研究"),
    ("eda-types-npm", "https://registry.npmjs.org/@jlceda/pro-api-types/latest", "npm latest 类型包版本0.4.30及完整性元数据", "Apache-2.0（package license 声明）"),
    ("eda-ai-init", "https://prodocs.lceda.cn/storage/texts/api/guide/how-to-start-for-ai.md", "官方 AI 向导以 SDK engines 为最低 Node 版本依据", "官方公开文档，未见开放再分发许可；仅本地研究"),
    ("eda-ai-cli", "https://prodocs.lceda.cn/storage/texts/api/guide/cli-for-ai.md", "官方面向 AI 的客户端 CLI 详细工作流", "官方公开文档，未见开放再分发许可；仅本地研究"),
]


def collect(item):
    identifier, url, claim, terms = item
    file = HERE / "snapshots" / (identifier + (".md" if identifier in {"eda-ai-init", "eda-ai-cli"} else ".json"))
    if not file.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "PCB-research/0.1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read(1_000_001)
        if len(data) > 1_000_000:
            raise ValueError("Response exceeds local research limit")
        file.write_bytes(data)
    data = file.read_bytes()
    obj = json.loads(data) if file.suffix == ".json" else {}
    record = {
        "id": identifier, "title": claim, "url": url,
        "local_path": file.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "retrieved_at": datetime.fromtimestamp(file.stat().st_mtime, timezone.utc).isoformat(),
        "authority": "官方 easyeda GitHub 仓库 / 官方文档 / npm 官方命名空间公开数据",
        "license_or_terms": terms,
        "claims": [claim],
        "limitations": ["已核实公开文本和版本声明；未安装官方网关、未运行桥接、未验证用户客户端兼容。"],
    }
    if isinstance(obj, dict) and "content" in obj:
        decoded_file = file.with_suffix(".decoded.txt")
        if not decoded_file.exists():
            decoded_file.write_bytes(base64.b64decode(obj["content"]))
        record["text_path"] = decoded_file.relative_to(ROOT).as_posix()
        record["upstream_blob_sha"] = obj.get("sha")
        record["upstream_html_url"] = obj.get("html_url")
    return record


if __name__ == "__main__":
    target = HERE / "sources.json"
    records = {record["id"]: record for record in json.loads(target.read_text(encoding="utf-8"))}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(collect, item): item for item in ITEMS}
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
                records[result["id"]] = {**records.get(result["id"], {}), **result}
                print(result["id"], flush=True)
            except Exception as error:
                print("ERROR", item[0], repr(error), flush=True)
    target.write_text(json.dumps(sorted(records.values(), key=lambda row: row["id"]), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
