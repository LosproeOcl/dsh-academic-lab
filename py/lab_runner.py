"""CLI 入口：宿主进程只负责传 JSON，分析和出图全部在这里发生。

调用约定（宿主 dsh/index.js 与我自己的测试都走这一条路）：
    python3 lab_runner.py <payload.json>
    # 或者从 stdin 读
    echo '{...}' | python3 lab_runner.py -

payload: {"command": "profile" | "stats" | "figure" | "gallery" | "recommend" | "infographic", "path": "...", "spec": {...}, "outDir": "...", "stem": "..."}
gallery / recommend / infographic 不需要 path。
stdout: 单个 JSON 对象；非零退出码表示失败，错误同样是 JSON。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab_common import LabError, emit, jsonable, run_guarded  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        emit({"ok": False, "error": {"code": "usage", "message": "用法：lab_runner.py <payload.json|->", "hint": ""}})
        sys.exit(1)

    source = sys.argv[1]
    try:
        if source == "-":
            payload = json.load(sys.stdin)
        else:
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001
        emit({"ok": False, "error": {"code": "bad-payload", "message": f"payload 不是合法 JSON：{error}", "hint": ""}})
        sys.exit(1)

    command = str(payload.get("command") or "").lower()

    # 图库与判读不需要读数据文件，放在 path 守卫之前处理。
    if command == "gallery":
        from lab_gallery import build_gallery

        run_guarded(command, build_gallery)
        return
    if command == "recommend":
        from lab_gallery import recommend

        profile = payload.get("profile") or {}
        question = str(payload.get("question") or "")
        run_guarded(command, lambda: recommend(profile, question))
        return
    if command == "infographic":
        from lab_infographic import render_infographic

        spec = payload.get("spec") or {}
        out_dir = payload.get("outDir") or "."
        stem = payload.get("stem") or "infographic"
        run_guarded(command, lambda: render_infographic(spec, out_dir, stem))
        return

    path = payload.get("path")
    if not path:
        emit({"ok": False, "error": {"code": "missing-path", "message": "payload 缺 path", "hint": "传数据文件的绝对路径"}})
        sys.exit(1)

    if command == "profile":
        from lab_profile import build_profile

        run_guarded(command, lambda: build_profile(path))
    elif command == "stats":
        from lab_stats import analyze

        spec = payload.get("spec") or {}
        run_guarded(command, lambda: analyze(path, spec))
    elif command == "figure":
        from lab_figure import make_figure

        spec = payload.get("spec") or {}
        out_dir = payload.get("outDir") or str(Path(path).resolve().parent / "figures")
        stem = payload.get("stem") or "figure"
        run_guarded(command, lambda: make_figure(path, spec, out_dir, stem))
    else:
        emit(
            {
                "ok": False,
                "error": {
                    "code": "unknown-command",
                    "message": f"不认识的命令：{command or '（空）'}",
                    "hint": "可用：profile / stats / figure / gallery / recommend / infographic",
                },
            }
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
