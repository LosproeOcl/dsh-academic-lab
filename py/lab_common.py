"""学术数据科学工作台 · 公共层。

职责：读表、算指纹、做 JSON 安全的类型转换、统一错误输出。

设计约束（都是被真实数据坑出来的）：
- 表头脏、编码乱、科学计数法是常态，读入必须能失败得清楚，而不是静默丢行；
- 所有 numpy / pandas 标量在输出前必须转成原生类型，否则 JSON 序列化会在
  某些后端上悄悄变成字符串；
- 错误必须是结构化的：Agent 要能读懂 code 并决定重试还是换参数。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SUPPORTED_EXT = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".json", ".jsonl", ".ndjson", ".parquet"}
MAX_ROWS = 5_000_000


class LabError(Exception):
    """带错误码的业务异常，CLI 层统一转成 JSON。"""

    def __init__(self, code: str, message: str, hint: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


# --------------------------------------------------------------- 文件与指纹 --


def sha256_file(path: str | os.PathLike) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_extension(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXT:
        raise LabError(
            "unsupported-format",
            f"不支持的文件类型：{suffix or '无扩展名'}",
            f"支持：{', '.join(sorted(SUPPORTED_EXT))}。Excel 请先另存为 .xlsx，"
            "数据库导出请先落成 CSV。",
        )
    return suffix


# ------------------------------------------------------------------- 读表 --


def _read_delimited(path: Path, suffix: str) -> pd.DataFrame:
    """CSV/TSV/TXT：分隔符自动嗅探，编码逐级回退，失败给出可操作提示。

    先试 utf-8-sig（Excel 导出常带 BOM），再试 GB18030（中文 Windows 导出常见），
    最后 latin-1 兜底——latin-1 不会抛错，所以放在最后一档并显式标记补丁。
    """

    if suffix == ".tsv":
        candidates = [("\t", "utf-8-sig"), ("\t", "gb18030")]
    else:
        candidates = [(None, "utf-8-sig"), (None, "gb18030"), (",", "utf-8-sig"), ("\t", "utf-8-sig")]

    errors: list[str] = []
    for sep, encoding in candidates:
        try:
            frame = pd.read_csv(
                path,
                sep=sep,
                engine="python",
                encoding=encoding,
                skip_blank_lines=True,
                on_bad_lines="warn",
            )
            if frame.shape[1] == 1 and sep is None:
                # 嗅探失败：整行被当成一列，换下一个候选。
                errors.append(f"sep={sep!r} encoding={encoding} 只解析出 1 列")
                continue
            return _normalize_headers(frame)
        except UnicodeDecodeError as error:
            errors.append(f"{encoding}: {error}")
        except pd.errors.EmptyDataError:
            raise LabError("empty-file", "文件没有任何数据行", "确认文件不是空文件，且表头行存在。")
        except Exception as error:  # noqa: BLE001 —— 统一转成结构化错误
            errors.append(f"{encoding}: {error}")

    raise LabError(
        "parse-failed",
        "所有分隔符/编码组合都没能解析出多列表格",
        "常见原因：文件是 Excel 但扩展名写成 .csv；表头行上方有说明文字（可用 skiprows）；"
        "或者分隔符是分号。错误明细：" + "；".join(errors[:3]),
    )


def _normalize_headers(frame: pd.DataFrame) -> pd.DataFrame:
    """表头去空白、重名去重、空名补名。脏表头是数据科学里最高频的失败点。"""

    columns = []
    seen: dict[str, int] = {}
    for index, raw in enumerate(frame.columns):
        name = str(raw).strip().replace("\n", " ")
        if not name or name.lower().startswith("unnamed:"):
            name = f"列{index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        columns.append(name)
    frame.columns = columns
    return frame


def load_table(path: str | os.PathLike) -> tuple[pd.DataFrame, dict]:
    """读入数据表，返回 (DataFrame, 读入信息)。读入信息会进 provenance。"""

    target = Path(path).expanduser()
    if not target.exists():
        raise LabError("file-not-found", f"文件不存在：{target}", "路径要对；相对路径相对于工作区根目录。")
    if not target.is_file():
        raise LabError("not-a-file", f"不是文件：{target}")
    if target.stat().st_size == 0:
        raise LabError("empty-file", f"文件是空的：{target}")

    suffix = ensure_extension(target)
    if suffix in {".csv", ".tsv", ".txt"}:
        frame = _read_delimited(target, suffix)
    elif suffix in {".xlsx", ".xlsm", ".xls"}:
        try:
            frame = pd.read_excel(target, sheet_name=0)
        except ImportError as error:  # 缺 openpyxl / xlrd
            raise LabError("missing-dependency", f"读 Excel 缺依赖：{error}", "pip install openpyxl（.xls 还需要 xlrd）")
        frame = _normalize_headers(frame)
    elif suffix in {".json", ".jsonl", ".ndjson"}:
        frame = _read_json(target, suffix)
    elif suffix == ".parquet":
        try:
            frame = pd.read_parquet(target)
        except ImportError as error:
            raise LabError("missing-dependency", f"读 Parquet 缺 pyarrow：{error}", "pip install pyarrow")
    else:  # pragma: no cover —— ensure_extension 已拦截
        raise LabError("unsupported-format", f"不支持：{suffix}")

    if frame.empty:
        raise LabError("empty-file", "表里没有数据行（只有表头）", "确认导出时没有筛选到空结果。")
    if len(frame) > MAX_ROWS:
        raise LabError(
            "too-large",
            f"数据行数 {len(frame):,} 超过上限 {MAX_ROWS:,}",
            "先做聚合/抽样再分析；或者用 SQL 在库侧汇总后导出结果表。",
        )

    frame = frame.dropna(axis=0, how="all")
    info = {
        "path": str(target.resolve()),
        "bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
    }
    return frame, info


def _read_json(path: Path, suffix: str) -> pd.DataFrame:
    if suffix in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise LabError("parse-failed", f"JSON 解析失败：{error}", "确认是对象数组 [{...}] 或记录式 JSON。")
    if isinstance(payload, dict):
        # 常见包装：{"data": [...]} / {"records": [...]}
        for key in ("data", "records", "rows", "items", "results"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list) or not payload:
        raise LabError("parse-failed", "JSON 不是非空的对象数组", "试 [{...}, {...}] 这种记录数组。")
    return _normalize_headers(pd.DataFrame(payload))


# ------------------------------------------------------------------ 类型 --


def numeric_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """只保留可安全转成数值的列。整列转不动就丢弃，不猜。"""

    keep = {}
    for column in frame.columns:
        series = frame[column]
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            keep[column] = series.astype("float64")
            continue
        if pd.api.types.is_string_dtype(series) or series.dtype == object:
            converted = pd.to_numeric(series.astype("string").str.strip(), errors="coerce")
            # 至少八成能转成数字才当数值列，避免把「站点编号 A1/A2」当连续变量。
            if converted.notna().sum() >= max(3, int(0.8 * series.notna().sum())):
                keep[column] = converted.astype("float64")
    return pd.DataFrame(keep, index=frame.index)


def is_categorical(series: pd.Series) -> bool:
    if pd.api.types.is_bool_dtype(series):
        return True
    if pd.api.types.is_numeric_dtype(series):
        return False
    unique = series.nunique(dropna=True)
    return 0 < unique <= max(50, int(len(series) * 0.2))


# ---------------------------------------------------------------- JSON --


def jsonable(value):
    """把 numpy / pandas 标量递归转成原生 JSON 类型；NaN/Inf 变 null。

    浮点 nan 在 json.dumps 里会输出 NaN（非法 JSON），前端 JSON.parse 直接炸。
    所以这里统一成 None，并让调用方在阅读层显式说明「含缺失」。
    """

    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return None if (math.isnan(number) or math.isinf(number)) else number
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.ndarray,)):
        return [jsonable(item) for item in value.tolist()]
    if isinstance(value, (pd.Series,)):
        return [jsonable(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def round_sig(value, digits: int = 4):
    """统计数字统一保留 4 位有效数字，但整数和极小 p 值保持人类可读。"""

    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(number) or math.isinf(number):
        return None
    if number == 0:
        return 0.0
    if abs(number) >= 1e5 or abs(number) < 1e-4:
        return float(f"{number:.{digits - 1}e}")
    return float(f"{number:.{digits}g}")


def emit(payload: dict) -> None:
    json.dump(jsonable(payload), sys.stdout, ensure_ascii=False, allow_nan=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def run_guarded(command: str, handler) -> None:
    """统一入口：任何异常都变成结构化 JSON，绝不让 traceback 直接进对话。"""

    try:
        emit(handler())
    except LabError as error:
        emit({"ok": False, "error": {"code": error.code, "message": error.message, "hint": error.hint}})
        sys.exit(2)
    except Exception as error:  # noqa: BLE001
        import traceback

        traceback.print_exc(file=sys.stderr)
        emit(
            {
                "ok": False,
                "error": {
                    "code": "internal-error",
                    "message": f"{type(error).__name__}: {error}",
                    "hint": "把 stderr 的 traceback 给开发者；同时确认数据列名没有拼错。",
                },
            }
        )
        sys.exit(3)
