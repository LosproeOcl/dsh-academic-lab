"""数据审计：在任何统计之前，先把这张表的问题说清楚。

学术场景里比「算出一个 p 值」更重要的是：样本量够不够、缺失怎么处理、
变量是什么尺度、有没有重复行、有没有不可能的值。这一步的输出会直接进
provenance 和论文的方法段，所以每条结论都要给出支撑数字。
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from lab_common import LabError, jsonable, load_table, numeric_frame, round_sig

MAX_TOP_VALUES = 8


def profile_column(series: pd.Series) -> dict[str, Any]:
    total = len(series)
    missing = int(series.isna().sum())
    non_null = total - missing
    non_null_series = series.dropna()
    unique = int(non_null_series.nunique())

    entry: dict[str, Any] = {
        "name": str(series.name),
        "missing": missing,
        "missing_rate": round_sig(missing / total, 3) if total else None,
        "unique": unique,
        "constant": unique <= 1,
    }

    numeric = pd.to_numeric(non_null_series, errors="coerce") if not pd.api.types.is_numeric_dtype(non_null_series) else non_null_series
    numeric_share = float(numeric.notna().sum()) / max(1, len(non_null_series))

    if pd.api.types.is_numeric_dtype(series) or numeric_share >= 0.95:
        values = numeric.dropna().astype("float64")
        if values.empty:
            entry["kind"] = "numeric"
            entry["note"] = "全部缺失，无法给出分布"
            return entry
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1
        low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = values[(values < low) | (values > high)]
        mad = np.median(np.abs(values - np.median(values)))
        entry.update(
            {
                "kind": "numeric",
                "n": int(len(values)),
                "min": round_sig(values.min()),
                "q1": round_sig(q1),
                "median": round_sig(values.median()),
                "q3": round_sig(q3),
                "max": round_sig(values.max()),
                "mean": round_sig(values.mean()),
                "sd": round_sig(values.std(ddof=1)) if len(values) > 1 else None,
                "skew": round_sig(values.skew()) if len(values) > 2 else None,
                "zeros": int((values == 0).sum()),
                "negatives": int((values < 0).sum()),
                "outliers_iqr": int(len(outliers)),
                "outlier_rate": round_sig(len(outliers) / len(values), 3),
                "note": None,
            }
        )
        if numeric_share < 1.0:
            entry["note"] = f"整列 {round_sig(100 * (1 - numeric_share), 3)}% 的值不是数字，已按缺失处理"
        if mad == 0 and len(values) > 10:
            entry["note"] = (entry["note"] or "") + "；超过一半取值相同（MAD=0），方差检验会不稳定"
        return entry

    # 类别 / 文本
    entry["kind"] = "categorical" if unique <= max(50, int(0.2 * total)) else "text"
    if unique <= 60:
        counts = non_null_series.astype(str).value_counts().head(MAX_TOP_VALUES)
        entry["top_values"] = [
            {"value": str(value)[:80], "count": int(count), "share": round_sig(count / max(1, non_null), 3)}
            for value, count in counts.items()
        ]
        if unique == 2:
            entry["binary"] = True
            entry["levels"] = [str(value) for value in counts.index[:2]]
    else:
        lengths = non_null_series.astype(str).str.len()
        entry["text_length"] = {
            "min": int(lengths.min()),
            "median": int(lengths.median()),
            "max": int(lengths.max()),
        }

    # 日期识别（只作提示，不改类型）
    sample = non_null_series.astype(str).head(200)
    import warnings as _warnings

    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        parsed = pd.to_datetime(sample, errors="coerce")
    if parsed.notna().mean() >= 0.9:
        entry["looks_like_date"] = True
        valid = parsed.dropna()
        if len(valid):
            entry["date_range"] = [valid.min().date().isoformat(), valid.max().date().isoformat()]

    spaces = non_null_series.astype(str)
    if (spaces != spaces.str.strip()).mean() > 0.1:
        entry["note"] = "超过一成的值首尾有空白，分组时会被当成不同类别"

    return entry


def build_profile(path: str) -> dict[str, Any]:
    frame, info = load_table(path)
    total = len(frame)
    columns = [profile_column(frame[column]) for column in frame.columns]

    numeric = numeric_frame(frame)
    categorical = [c["name"] for c in columns if c["kind"] == "categorical"]

    warnings: list[str] = []
    duplicate_rows = int(frame.duplicated().sum())
    if duplicate_rows:
        warnings.append(
            f"有 {duplicate_rows} 行完全重复（占 {duplicate_rows / total:.1%}）。重复行会让 n 虚高、p 值偏小——"
            "确认是重复录入还是合法的重复测量，再决定 drop_duplicates 还是按被试聚合。"
        )

    small_n = [c["name"] for c in columns if c["kind"] == "categorical" and c.get("top_values") and min(v["count"] for v in c["top_values"]) < 5]
    if small_n:
        warnings.append("这些分组里存在少于 5 个观测的水平，任何组间检验都会不稳：" + "、".join(small_n))

    high_missing = [c["name"] for c in columns if (c["missing_rate"] or 0) > 0.2]
    if high_missing:
        warnings.append("缺失超过 20% 的列：" + "、".join(high_missing) + "——先判断缺失机制（MCAR/MAR/MNAR），不要默认删行。")

    constant = [c["name"] for c in columns if c["constant"]]
    if constant:
        warnings.append("常量列没有信息量，可以剔除：" + "、".join(constant))

    # 数值列之间的强相关：多重共线性与「重复测量同一件事」的线索
    pairs = []
    if numeric.shape[1] >= 2:
        corr = numeric.corr(numeric_only=True)
        for i, left in enumerate(corr.columns):
            for right in corr.columns[i + 1:]:
                value = corr.loc[left, right]
                if pd.notna(value) and abs(value) >= 0.8:
                    pairs.append({"a": left, "b": right, "r": round_sig(value, 3)})
        pairs.sort(key=lambda item: -abs(item["r"]))
    if pairs:
        warnings.append("高度相关的列（|r|≥0.8）：" + "，".join(f"{p['a']}~{p['b']} r={p['r']}" for p in pairs[:3]) + "。回归里同时放进去会造成共线性。")

    if total < 30:
        warnings.append(f"样本量 n={total}，小于 30：描述统计可以，推断统计要写清局限，别做多重比较。")

    reading = [
        f"这张表 {total} 行 × {len(columns)} 列，数值型 {numeric.shape[1]} 列，类别型 {len(categorical)} 列。",
        f"完整行 {int((~frame.isna().any(axis=1)).sum())} 行；有缺失的行 {int(frame.isna().any(axis=1).sum())} 行。",
    ]
    if numeric.shape[1]:
        reading.append("数值列可做描述统计；组间比较前先确认分组变量的水平数与每组样本量。")
    if duplicate_rows:
        reading.append("先处理重复行，再谈样本量。")

    return {
        "ok": True,
        "dataset": info,
        "shape": {"rows": total, "columns": len(columns)},
        "columns": columns,
        "numeric_columns": list(numeric.columns),
        "categorical_columns": categorical,
        "duplicate_rows": duplicate_rows,
        "strong_correlations": pairs,
        "warnings": warnings,
        "reading": reading,
    }
