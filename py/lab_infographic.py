"""信息图渲染：把 data-viz-gen 的 build_infographic.py 包装成 lab_runner 的一条命令。

build_infographic.py 是 vendor 进来的 MIT 脚本（见 THIRD_PARTY_NOTICES.md），
纯 Python 标准库、自包含 HTML 输出，支持四种类型：
- stats      统计卡片（KPI 大数字 + 趋势箭头 + 图标）
- comparison 分组柱状图（多系列对比）
- flow       流程图（步骤 + 图标 + 箭头）
- dashboard  混合仪表盘（卡片 + 柱状图 + 环形图 + 流程）

config 由 Agent 按四类的 data 格式装配后传入；这里只负责落盘渲染并返回产物。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_SCRIPT = Path(__file__).resolve().parent / "build_infographic.py"

_INFO_TYPES = {"stats", "comparison", "flow", "dashboard"}


def render_infographic(config: dict[str, Any], out_dir: str, stem: str) -> dict[str, Any]:
    out = Path(out_dir or ".")
    out.mkdir(parents=True, exist_ok=True)
    out_path = out / f"{stem}.html"
    cfg = dict(config or {})
    cfg["output"] = str(out_path)

    # 走临时文件把 config 交给 vendor 脚本，避免 shell 转义与 stdin 编码问题。
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False)
        cfg_path = fh.name
    try:
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), cfg_path],
            capture_output=True, text=True, timeout=120,
        )
    finally:
        os.unlink(cfg_path)

    try:
        parsed = json.loads(result.stdout.strip() or "{}")
    except json.JSONDecodeError:
        parsed = {}

    if parsed.get("status") != "success":
        errors = parsed.get("errors") or [parsed.get("message") or result.stderr.strip()]
        return {
            "ok": False,
            "error": {
                "code": "infographic",
                "message": "；".join(map(str, errors)) if errors else "信息图渲染失败",
                "hint": f"检查 config 的 type（{sorted(_INFO_TYPES)}）与 data 格式是否符合四类要求",
            },
        }

    return {
        "ok": True,
        "chart": cfg.get("type"),
        "type": parsed.get("type"),
        "title": parsed.get("title") or cfg.get("title"),
        "palette": parsed.get("palette"),
        "files": [{"format": "html", "path": str(out_path), "bytes": out_path.stat().st_size}],
        "caption": str(cfg.get("footer") or ""),
    }
