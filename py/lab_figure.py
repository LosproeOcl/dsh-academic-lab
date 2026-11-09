"""出版级出图：宽度按期刊栏宽、字号按期刊惯例、输出矢量 + 位图。

为什么自己画而不直接套 seaborn 主题：
- 期刊要的是「89 mm 宽、7 pt 字、无边框、色盲友好」这类硬约束，主题改起来比重写还麻烦；
- 每张图都要能回答「用了哪些行、多少 n、单位是什么」，这些要作为图注一起产出；
- 矢量 PDF/SVG 才是投稿件，PNG 只是审阅用。
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# matplotlib 的字体缓存目录必须可写；某些沙箱里 ~/.matplotlib 是只读的。
os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mplcache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from scipy import stats as sps  # noqa: E402

from lab_common import LabError, load_table, numeric_frame, round_sig  # noqa: E402

MM_PER_INCH = 25.4

JOURNALS: dict[str, dict[str, Any]] = {
    "nature": {"single": 89.0, "double": 183.0, "font": 7.0, "line": 0.6, "label": "Nature"},
    "science": {"single": 55.0, "double": 120.0, "font": 7.0, "line": 0.6, "label": "Science"},
    "ieee": {"single": 88.9, "double": 181.0, "font": 8.0, "line": 0.7, "label": "IEEE"},
    "aps": {"single": 85.0, "double": 170.0, "font": 8.0, "line": 0.7, "label": "APS"},
    "plos": {"single": 83.0, "double": 173.0, "font": 8.0, "line": 0.7, "label": "PLOS"},
    "generic": {"single": 100.0, "double": 180.0, "font": 9.0, "line": 0.8, "label": "通用"},
}

# Okabe-Ito：色盲友好的 8 色，投稿和打印都安全。
PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#666666"]

CJK_FONT_CANDIDATES = [
    "PingFang SC",
    "Hiragino Sans GB",
    "Songti SC",
    "Heiti SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Microsoft YaHei",
    "SimHei",
    "WenQuanYi Zen Hei",
]


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" or "\u3000" <= char <= "\u303f" for char in text)


def resolve_font(needs_cjk: bool) -> tuple[str | None, list[str]]:
    """找一款能显示中文的字体；找不到就返回 None 并给出警告，不静默画方块。"""

    warnings: list[str] = []
    if not needs_cjk:
        return None, warnings
    available = {entry.name for entry in font_manager.fontManager.ttflist}
    for candidate in CJK_FONT_CANDIDATES:
        if candidate in available:
            return candidate, warnings
    warnings.append(
        "图内有中文，但系统里没找到可用中文字体（PingFang/Noto/文泉驿等）；"
        "中文会显示成方框。可以改用英文标签，或安装 Noto Sans CJK。"
    )
    return None, warnings


def style_axes(ax, font_size: float, line_width: float) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_linewidth(line_width)
    ax.tick_params(direction="out", length=3, width=line_width, pad=2, labelsize=font_size)
    ax.xaxis.label.set_size(font_size + 0.5)
    ax.yaxis.label.set_size(font_size + 0.5)
    ax.title.set_size(font_size + 1.0)


def _prep(frame: pd.DataFrame, spec: dict[str, Any]) -> pd.DataFrame:
    needed = [spec.get(key) for key in ("x", "y", "group") if spec.get(key)]
    missing = [column for column in needed if column not in frame.columns]
    if missing:
        raise LabError("column-not-found", f"表里没有这些列：{'、'.join(missing)}", f"现有列：{'、'.join(map(str, frame.columns[:30]))}")
    subset = frame[needed].dropna() if needed else frame.dropna()
    if len(subset) < 3:
        raise LabError("insufficient-data", f"有效行只有 {len(subset)} 行，画不出有信息量的图")
    return subset


def _error_bars(values: np.ndarray, mode: str) -> tuple[float, float, str]:
    n = len(values)
    mean = float(np.mean(values))
    sd = float(np.std(values, ddof=1)) if n > 1 else 0.0
    if mode in {"none", ""}:
        return 0.0, mean, "无误差棒"
    if mode == "sd":
        return sd, mean, "均值 ± SD"
    if mode == "sem":
        return sd / math.sqrt(n), mean, "均值 ± SEM"
    if mode == "ci95":
        if n < 2:
            return 0.0, mean, "均值（n<2，无区间）"
        critical = sps.t.ppf(0.975, n - 1)
        return critical * sd / math.sqrt(n), mean, "均值 ± 95% CI"
    raise LabError("unknown-error", f"不认识的误差棒类型：{mode}", "可用：ci95 / sem / sd / none")


def _grouped(frame: pd.DataFrame, group: str | None):
    if group:
        names = [str(name) for name in frame[group].astype("string").dropna().unique()]
        names.sort()
        for name in names:
            mask = frame[group].astype("string") == name
            yield name, frame[mask]
    else:
        yield None, frame


def draw(frame: pd.DataFrame, spec: dict[str, Any]) -> tuple[plt.Figure, dict[str, Any]]:
    chart = str(spec.get("chart") or "bar").lower()
    journal = JOURNALS.get(str(spec.get("journal") or "nature").lower())
    if journal is None:
        raise LabError("unknown-journal", f"不认识的期刊版式：{spec.get('journal')}", "可用：" + " / ".join(JOURNALS))
    width_mm = float(spec.get("widthMm") or journal["single"])
    height_mm = float(spec.get("heightMm") or (width_mm * 0.72 if chart != "heatmap" else width_mm * 0.8))
    font_size = float(spec.get("fontSize") or journal["font"])
    line_width = journal["line"]
    error_mode = str(spec.get("error") or "ci95").lower()

    labels_for_font = " ".join(str(spec.get(key) or "") for key in ("title", "xLabel", "yLabel", "caption"))
    cjk_font, warnings = resolve_font(_has_cjk(labels_for_font))

    rc = {
        "font.size": font_size,
        "axes.linewidth": line_width,
        "pdf.fonttype": 42,  # TrueType 嵌入，编辑部要可编辑的字体
        "ps.fonttype": 42,
        "svg.fonttype": "path",
        "figure.dpi": 150,
        # 中文字体普遍缺 U+2212（数学负号），matplotlib 默认用它画负刻度，
        # 结果是坐标轴上的负号变成方框。关掉后统一用 ASCII 连字符。
        "axes.unicode_minus": False,
    }
    if cjk_font:
        # 用「字体族列表」而不是单个 family：matplotlib 3.6+ 会做逐字形回退，
        # 中文字体常缺 ²（上标）、−（U+2212）这类数学符号，单字体就会画成方框。
        rc["font.family"] = [cjk_font, "DejaVu Sans"]
        rc["font.sans-serif"] = [cjk_font, "DejaVu Sans"]
    with plt.rc_context(rc):
        fig, ax = plt.subplots(figsize=(width_mm / MM_PER_INCH, height_mm / MM_PER_INCH))
        style_axes(ax, font_size, line_width)
        stats_used: dict[str, Any] = {"chart": chart, "journal": journal["label"], "width_mm": width_mm, "height_mm": height_mm}

        if chart == "bar":
            x, y = spec.get("x"), spec.get("y")
            if not x or not y:
                raise LabError("missing-parameter", "bar 需要 x（分组）与 y（数值）")
            working = _prep(frame, {"x": x, "y": y, "group": spec.get("group")})
            working = working.assign(_y=pd.to_numeric(working[y], errors="coerce")).dropna(subset=["_y"])
            categories = [str(value) for value in working[x].astype("string").unique()]
            if spec.get("order"):
                categories = [item for item in spec["order"] if item in categories] or categories
            groups = list(_grouped(working, spec.get("group")))
            bar_width = 0.8 / max(1, len(groups))
            for index, (name, subset) in enumerate(groups):
                means, errors = [], []
                for category in categories:
                    values = subset.loc[subset[x].astype("string") == category, "_y"].to_numpy()
                    error, mean, _ = _error_bars(values, error_mode) if len(values) else (0.0, 0.0, "")
                    means.append(mean)
                    errors.append(error)
                positions = np.arange(len(categories)) + (index - (len(groups) - 1) / 2) * bar_width
                ax.bar(
                    positions,
                    means,
                    bar_width,
                    yerr=errors,
                    capsize=2,
                    color=PALETTE[index % len(PALETTE)],
                    edgecolor="white",
                    linewidth=0.4,
                    label=str(name) if name is not None else None,
                    error_kw={"elinewidth": line_width, "capthick": line_width},
                )
            ax.set_xticks(np.arange(len(categories)))
            ax.set_xticklabels(categories)
            if len(categories) > 4:
                for label in ax.get_xticklabels():
                    label.set_rotation(20)
                    label.set_ha("right")
            stats_used["n_per_bar"] = {
                str(cat): int((working[x].astype("string") == cat).sum()) for cat in categories
            }
            stats_used["error"] = {"ci95": "95% CI of mean", "sem": "SEM", "sd": "SD"}.get(error_mode, "none")

        elif chart == "line":
            x, y = spec.get("x"), spec.get("y")
            if not x or not y:
                raise LabError("missing-parameter", "line 需要 x 与 y")
            working = _prep(frame, {"x": x, "y": y, "group": spec.get("group")})
            working = working.assign(_y=pd.to_numeric(working[y], errors="coerce")).dropna(subset=["_y"])
            for index, (name, subset) in enumerate(_grouped(working, spec.get("group"))):
                aggregated = subset.groupby(x, observed=True)["_y"]
                xs = list(aggregated.groups.keys())
                means, errors = [], []
                for key in xs:
                    error, mean, _ = _error_bars(aggregated.get_group(key).to_numpy(), error_mode)
                    means.append(mean)
                    errors.append(error)
                ax.errorbar(
                    xs,
                    means,
                    yerr=errors,
                    marker="o",
                    markersize=3,
                    linewidth=line_width * 1.6,
                    capsize=2,
                    color=PALETTE[index % len(PALETTE)],
                    label=str(name) if name is not None else None,
                )
            stats_used["n_points"] = int(working[x].nunique())

        elif chart == "scatter":
            x, y = spec.get("x"), spec.get("y")
            if not x or not y:
                raise LabError("missing-parameter", "scatter 需要 x 与 y")
            working = _prep(frame, {"x": x, "y": y, "group": spec.get("group")})
            working = working.assign(_x=pd.to_numeric(working[x], errors="coerce"), _y=pd.to_numeric(working[y], errors="coerce")).dropna(subset=["_x", "_y"])
            for index, (name, subset) in enumerate(_grouped(working, spec.get("group"))):
                ax.scatter(
                    subset["_x"],
                    subset["_y"],
                    s=8,
                    linewidths=0,
                    alpha=0.75,
                    color=PALETTE[index % len(PALETTE)],
                    label=str(name) if name is not None else None,
                )
            fit = str(spec.get("fit") or "auto").lower()
            if fit in {"auto", "linear", "true"} and len(working) >= 3:
                slope, intercept = np.polyfit(working["_x"], working["_y"], 1)
                grid = np.linspace(working["_x"].min(), working["_x"].max(), 100)
                ax.plot(grid, slope * grid + intercept, color="#333333", linewidth=line_width * 1.4)
                residual = working["_y"] - (slope * working["_x"] + intercept)
                s_err = math.sqrt(float(np.sum(residual ** 2)) / max(1, len(working) - 2))
                mean_x = float(working["_x"].mean())
                sxx = float(np.sum((working["_x"] - mean_x) ** 2))
                if sxx > 0:
                    band = 1.96 * s_err * np.sqrt(1 / len(working) + (grid - mean_x) ** 2 / sxx)
                    ax.fill_between(grid, slope * grid + intercept - band, slope * grid + intercept + band, color="#999999", alpha=0.25, linewidth=0)
                stats_used["fit"] = {"slope": round_sig(slope), "intercept": round_sig(intercept)}
            stats_used["n"] = int(len(working))

        elif chart in {"box", "violin", "raincloud"}:
            x, y = spec.get("x") or spec.get("group"), spec.get("y")
            if not x or not y:
                raise LabError("missing-parameter", f"{chart} 需要 x（分组）与 y（数值）")
            working = _prep(frame, {"x": x, "y": y})
            working = working.assign(_y=pd.to_numeric(working[y], errors="coerce")).dropna(subset=["_y"])
            categories = [str(value) for value in working[x].astype("string").unique()]
            arrays = [working.loc[working[x].astype("string") == category, "_y"].to_numpy() for category in categories]
            positions = np.arange(1, len(categories) + 1)
            rng = np.random.default_rng(424242)

            if chart == "box":
                box = ax.boxplot(arrays, positions=positions, widths=0.55, patch_artist=True, showfliers=False)
                for index, patch in enumerate(box["boxes"]):
                    patch.set_facecolor(PALETTE[index % len(PALETTE)])
                    patch.set_alpha(0.45)
                    patch.set_edgecolor("#333333")
                    patch.set_linewidth(line_width)
                for element in ("whiskers", "caps", "medians"):
                    for line in box[element]:
                        line.set_linewidth(line_width)
                        line.set_color("#333333")
            elif chart == "violin":
                parts = ax.violinplot(arrays, positions=positions, widths=0.7, showextrema=False)
                for index, body in enumerate(parts["bodies"]):
                    body.set_facecolor(PALETTE[index % len(PALETTE)])
                    body.set_alpha(0.45)
                    body.set_edgecolor("#333333")
                    body.set_linewidth(line_width)
            else:  # raincloud：半边小提琴 + 散点 + 中位数线
                for index, (category, values) in enumerate(zip(categories, arrays)):
                    if len(values) < 3:
                        continue
                    kde = sps.gaussian_kde(values)
                    grid = np.linspace(values.min(), values.max(), 120)
                    density = kde(grid)
                    density = density / density.max() * 0.34
                    ax.fill_betweenx(grid, positions[index] - density, positions[index], color=PALETTE[index % len(PALETTE)], alpha=0.45, linewidth=0)
                for index, (category, values) in enumerate(zip(categories, arrays)):
                    jitter = rng.uniform(-0.12, 0.12, len(values))
                    ax.scatter(positions[index] + 0.1 + jitter, values, s=5, linewidths=0, alpha=0.7, color=PALETTE[index % len(PALETTE)])
                    ax.plot([positions[index] + 0.02, positions[index] + 0.28], [np.median(values)] * 2, color="#333333", linewidth=line_width * 1.6)
            ax.set_xticks(positions)
            ax.set_xticklabels(categories)
            if len(categories) > 4:
                for label in ax.get_xticklabels():
                    label.set_rotation(20)
                    label.set_ha("right")
            stats_used["n_per_group"] = {str(cat): int(len(arr)) for cat, arr in zip(categories, arrays)}

        elif chart == "hist":
            x = spec.get("x")
            if not x:
                raise LabError("missing-parameter", "hist 需要 x")
            working = _prep(frame, {"x": x, "group": spec.get("group")})
            working = working.assign(_x=pd.to_numeric(working[x], errors="coerce")).dropna(subset=["_x"])
            all_values = working["_x"].to_numpy()
            bins = int(spec.get("bins") or max(8, min(40, int(np.sqrt(len(all_values))))))
            if spec.get("group"):
                for index, (name, subset) in enumerate(_grouped(working, spec.get("group"))):
                    ax.hist(subset["_x"], bins=bins, alpha=0.45, color=PALETTE[index % len(PALETTE)], label=str(name), edgecolor="white", linewidth=0.3)
            else:
                ax.hist(all_values, bins=bins, color=PALETTE[0], alpha=0.85, edgecolor="white", linewidth=0.3)
            stats_used["bins"] = bins
            stats_used["n"] = int(len(all_values))

        elif chart == "heatmap":
            columns = spec.get("columns") or list(numeric_frame(frame).columns)
            if isinstance(columns, str):
                columns = [item.strip() for item in columns.split(",") if item.strip()]
            numeric = numeric_frame(frame)
            targets = [column for column in columns if column in numeric.columns]
            if len(targets) < 2:
                raise LabError("insufficient-data", "相关性热图至少需要 2 个数值列")
            matrix = numeric[targets].corr(method=str(spec.get("method") or "pearson"))
            image = ax.imshow(matrix.to_numpy(), cmap=str(spec.get("cmap") or "RdBu_r"), vmin=-1, vmax=1)
            ax.set_xticks(range(len(targets)))
            ax.set_yticks(range(len(targets)))
            ax.set_xticklabels(targets, rotation=45, ha="right")
            ax.set_yticklabels(targets)
            ax.tick_params(length=0)
            for row in range(len(targets)):
                for column in range(len(targets)):
                    value = matrix.iloc[row, column]
                    ax.text(column, row, f"{value:.2f}", ha="center", va="center", fontsize=font_size - 1, color="#111111" if abs(value) < 0.6 else "white")
            colorbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.02)
            colorbar.ax.tick_params(labelsize=font_size - 1, length=2)
            colorbar.outline.set_linewidth(line_width * 0.8)
            ax.spines["left"].set_visible(False)
            ax.spines["bottom"].set_visible(False)
            stats_used["matrix"] = matrix.round(3).to_dict()
            # 相关矩阵是成对剔除缺失算的，所以 n 取「所有目标列都齐全」的行数，比较保守。
            stats_used["n"] = int(numeric[targets].dropna().shape[0])

        else:
            raise LabError("unknown-chart", f"不认识的图表类型：{chart}", "可用：bar / line / scatter / box / violin / raincloud / hist / heatmap")

        if spec.get("xLabel"):
            ax.set_xlabel(str(spec["xLabel"]))
        if spec.get("yLabel"):
            ax.set_ylabel(str(spec["yLabel"]))
        if spec.get("title"):
            ax.set_title(str(spec["title"]), loc="left", pad=6)
        if spec.get("group") and chart not in {"heatmap"}:
            legend = ax.legend(frameon=False, fontsize=font_size - 1, loc="best", handlelength=1.2)
            if legend:
                legend.get_frame().set_linewidth(0)
        if spec.get("panelLabel") and spec.get("panelLabel") not in {"none", "false", ""}:
            ax.text(-0.12, 1.04, str(spec["panelLabel"]), transform=ax.transAxes, fontsize=font_size + 2, fontweight="bold", va="bottom", ha="left")
        fig.tight_layout(pad=0.4)

    return fig, {"stats": stats_used, "warnings": warnings, "font": cjk_font, "error_mode": error_mode, "rc": rc}


def _interactive_data(frame: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any] | None:
    """把一张图要展示的数据压成 JSON 安全的小载荷，供交互视图重绘。

    与 draw() 用同一套聚合逻辑，所以交互视图与静态图数值一致；只覆盖
    bar / line / scatter / box / hist / heatmap 六种，violin 与 raincloud
    返回 None（面板退回静态预览）。"""
    chart = str(spec.get("chart") or "bar").lower()
    x, y = spec.get("x"), spec.get("y")
    group = spec.get("group")
    error_mode = str(spec.get("error") or "ci95").lower()

    def error_of(values):
        if len(values) == 0:
            return 0.0, 0.0
        return _error_bars(np.asarray(values, dtype=float), error_mode)[:2]

    if chart in {"bar", "line"}:
        if not x or not y:
            return None
        working = _prep(frame, {"x": x, "y": y, "group": group})
        working = working.assign(_y=pd.to_numeric(working[y], errors="coerce")).dropna(subset=["_y"])
        categories = [str(value) for value in working[x].astype("string").unique()]
        if spec.get("order"):
            categories = [item for item in spec["order"] if item in categories] or categories
        series = []
        for name, subset in _grouped(working, group):
            means, errors = [], []
            for category in categories:
                values = subset.loc[subset[x].astype("string") == category, "_y"].to_numpy()
                error, mean = error_of(values)
                means.append(round_sig(float(mean)))
                errors.append(round_sig(float(error)))
            series.append({"name": None if name is None else str(name), "means": means, "errors": errors})
        return {
            "chart": chart,
            "categories": categories,
            "series": series,
            "errorMode": {"ci95": "95% CI", "sem": "SEM", "sd": "SD"}.get(error_mode, ""),
        }

    if chart == "scatter":
        if not x or not y:
            return None
        working = _prep(frame, {"x": x, "y": y, "group": group})
        working = working.assign(
            _x=pd.to_numeric(working[x], errors="coerce"),
            _y=pd.to_numeric(working[y], errors="coerce"),
        ).dropna(subset=["_x", "_y"])
        series = []
        for name, subset in _grouped(working, group):
            series.append({
                "name": None if name is None else str(name),
                "x": [round_sig(float(value)) for value in subset["_x"].to_numpy()],
                "y": [round_sig(float(value)) for value in subset["_y"].to_numpy()],
            })
        fit = None
        if str(spec.get("fit") or "auto").lower() in {"auto", "linear", "true"} and len(working) >= 3:
            slope, intercept = np.polyfit(working["_x"], working["_y"], 1)
            fit = {"slope": round_sig(float(slope)), "intercept": round_sig(float(intercept))}
        return {"chart": chart, "series": series, "fit": fit, "xName": str(x), "yName": str(y)}

    if chart == "box":
        xx = x or group
        if not xx or not y:
            return None
        working = _prep(frame, {"x": xx, "y": y})
        working = working.assign(_y=pd.to_numeric(working[y], errors="coerce")).dropna(subset=["_y"])
        categories = [str(value) for value in working[xx].astype("string").unique()]
        boxes = []
        for category in categories:
            values = working.loc[working[xx].astype("string") == category, "_y"].to_numpy()
            if len(values) == 0:
                continue
            q1, med, q3 = np.percentile(values, [25, 50, 75])
            iqr = q3 - q1
            low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            inside = values[(values >= low) & (values <= high)]
            whisker_lo = inside.min() if len(inside) else q1
            whisker_hi = inside.max() if len(inside) else q3
            outliers = [round_sig(float(value)) for value in values[(values < low) | (values > high)]]
            boxes.append({
                "name": category,
                "min": round_sig(float(whisker_lo)), "q1": round_sig(float(q1)),
                "median": round_sig(float(med)), "q3": round_sig(float(q3)),
                "max": round_sig(float(whisker_hi)), "outliers": outliers,
                "n": int(len(values)),
            })
        return {"chart": chart, "categories": categories, "series": boxes}

    if chart == "hist":
        if not x:
            return None
        working = _prep(frame, {"x": x, "group": group})
        working = working.assign(_x=pd.to_numeric(working[x], errors="coerce")).dropna(subset=["_x"])
        all_values = working["_x"].to_numpy()
        bins = int(spec.get("bins") or max(8, min(40, int(np.sqrt(len(all_values))))))
        lo, hi = float(all_values.min()), float(all_values.max())
        if lo == hi:
            lo, hi = lo - 0.5, hi + 0.5
        edges = np.linspace(lo, hi, bins + 1)
        series = []
        for name, subset in _grouped(working, group):
            counts, _ = np.histogram(subset["_x"].to_numpy(), bins=edges)
            series.append({
                "name": None if name is None else str(name),
                "edges": [round_sig(float(value)) for value in edges],
                "counts": [int(count) for count in counts],
            })
        return {"chart": chart, "series": series}

    if chart == "heatmap":
        columns = spec.get("columns") or list(numeric_frame(frame).columns)
        if isinstance(columns, str):
            columns = [item.strip() for item in columns.split(",") if item.strip()]
        numeric = numeric_frame(frame)
        targets = [column for column in columns if column in numeric.columns]
        if len(targets) < 2:
            return None
        matrix = numeric[targets].corr(method=str(spec.get("method") or "pearson"))
        return {
            "chart": chart,
            "labels": [str(column) for column in targets],
            "matrix": [[round_sig(float(value)) for value in row] for row in matrix.to_numpy()],
        }

    return None


# 自包含交互视图：内嵌数据 + 一个零依赖的 SVG 渲染器。悬浮出 tooltip，框选缩放，
# 双击复位。只覆盖 bar / line / scatter / box / hist / heatmap 六种。
_INTERACTIVE_TEMPLATE = r"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;background:#f7f7f5;color:#252320}
  #wrap{max-width:980px;margin:0 auto;padding:20px 24px 44px}
  #title{font-size:15px;font-weight:600;margin:0 0 4px}
  #meta{font-size:12px;color:#8a8a84;margin-bottom:14px}
  #stage{position:relative;background:#fff;border:1px solid #e4e3de;border-radius:10px;overflow:hidden}
  svg{display:block;width:100%;height:auto;cursor:crosshair}
  .tip{position:absolute;pointer-events:none;background:rgba(37,35,32,.95);color:#fff;font-size:12px;line-height:1.55;padding:6px 9px;border-radius:6px;white-space:pre;display:none;max-width:340px;z-index:6}
  .hint{font-size:11px;color:#9a9a94;margin-top:8px}
  .brush{fill:#2563eb;fill-opacity:.12;stroke:#2563eb;stroke-dasharray:3 2}
</style>
</head>
<body>
<div id="wrap">
  <div id="title"></div>
  <div id="meta"></div>
  <div id="stage">
    <svg id="svg"></svg>
    <div class="tip" id="tip"></div>
  </div>
  <div class="hint">悬浮查看数值 · 拖拽框选缩放 · 双击复位</div>
</div>
<script>
const DATA = __DATA__;
const PALETTE = ["#E69F00","#56B4E9","#009E73","#F0E442","#0072B2","#D55E00","#CC79A7","#999999"];
const M = {t:20, r:16, b:48, l:60};
const W = 940, H = 590;
const IW = W - M.l - M.r, IH = H - M.t - M.b;
const NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("svg");
const tip = document.getElementById("tip");
const stage = document.getElementById("stage");
svg.setAttribute("viewBox", "0 0 " + W + " " + H);

document.getElementById("title").textContent = DATA.title || "";
const metaBits = [];
if (DATA.chart) metaBits.push("图表 " + DATA.chart);
if (DATA.errorMode) metaBits.push("误差棒 " + DATA.errorMode);
if (DATA.note) metaBits.push(DATA.note);
document.getElementById("meta").textContent = metaBits.join(" · ");

let marks = [];          // {x0,y0,x1,y1,tip}
let view = null;         // {x:[lo,hi]} 或 {x:[lo,hi], y:[lo,hi]}
let xs = null, ys = null; // 当前 scale，带 invert

function el(tag, attrs, text){
  const e = document.createElementNS(NS, tag);
  if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  return e;
}
function num(v){ const n = parseFloat(v); return Number.isNaN(n) ? 0 : n; }
function fmt(v){
  const n = num(v);
  if (Math.abs(n) >= 100000 || (Math.abs(n) > 0 && Math.abs(n) < 0.0001)) return n.toExponential(2);
  return String(Math.round(n * 1000) / 1000);
}
function lin(lo, hi, r0, r1){
  const span = (hi - lo) || 1;
  const f = function(v){ return r0 + (num(v) - lo) / span * (r1 - r0); };
  f.invert = function(p){ return lo + (p - r0) / (r1 - r0) * span; };
  return f;
}
function catIndexRange(categories, view){
  if (view && view.x) {
    const i0 = Math.max(0, Math.floor(num(view.x[0])));
    const i1 = Math.min(categories.length - 1, Math.ceil(num(view.x[1])));
    return [i0, i1];
  }
  return [0, categories.length - 1];
}
function catScale(categories, view){
  const range = catIndexRange(categories, view);
  const lo = range[0], hi = range[1];
  const n = Math.max(1, hi - lo + 1);
  const f = function(i){ return M.l + (i - lo + 0.5) * IW / n; };
  f.invert = function(p){ return lo + (p - M.l) / IW * n - 0.5; };
  return f;
}
function color(i){ return PALETTE[i % PALETTE.length]; }
function reset(){ view = null; render(); }

function axis(xticks, yscale, ylabel, xlabel){
  // y 轴（线性）：找几个"整"刻度
  const d0 = yscale.invert(M.t + IH), d1 = yscale.invert(M.t);
  let step = Math.pow(10, Math.floor(Math.log10((d1 - d0) || 1)));
  const raw = (d1 - d0) / step;
  if (raw < 2) step /= 5; else if (raw < 4) step /= 2; else if (raw > 8) step *= 2;
  const start = Math.ceil(d0 / step) * step;
  const g = el("g", null);
  for (let v = start; v <= d1 + step * 1e-6; v += step) {
    const py = yscale(v);
    g.appendChild(el("line", {x1: M.l, y1: py, x2: W - M.r, y2: py, stroke: "#eeeef0"}));
    g.appendChild(el("text", {x: M.l - 8, y: py + 3.5, "text-anchor": "end", "font-size": 11, fill: "#8a8a84"}, fmt(v)));
  }
  g.appendChild(el("line", {x1: M.l, y1: M.t, x2: M.l, y2: M.t + IH, stroke: "#c9c9c4"}));
  g.appendChild(el("line", {x1: M.l, y1: M.t + IH, x2: W - M.r, y2: M.t + IH, stroke: "#c9c9c4"}));
  if (ylabel) g.appendChild(el("text", {x: 14, y: M.t + IH / 2, transform: "rotate(-90 14 " + (M.t + IH / 2) + ")", "text-anchor": "middle", "font-size": 12, fill: "#55554f"}, ylabel));
  // x 轴刻度
  if (xticks && xticks.length) {
    xticks.forEach(function(tk){
      g.appendChild(el("text", {x: tk.px, y: M.t + IH + 18, "text-anchor": "middle", "font-size": 11, fill: "#55554f", transform: "rotate(" + (tk.rotate || 0) + " " + tk.px + " " + (M.t + IH + 18) + ")"}, tk.label));
    });
  }
  if (xlabel) g.appendChild(el("text", {x: M.l + IW / 2, y: H - 8, "text-anchor": "middle", "font-size": 12, fill: "#55554f"}, xlabel));
  return g;
}
function addMark(m){ marks.push(m); }

function renderBar(){
  const d = DATA.data, cats = d.categories, series = d.series;
  const allMeans = series.flatMap(function(s){ return s.means; });
  const allErrs = series.flatMap(function(s){ return s.errors; });
  let ylo = Math.min(0, Math.min.apply(null, allMeans.map(function(m){ return num(m); })));
  let yhi = Math.max.apply(null, allMeans.map(function(m){ return num(m); }));
  const maxErr = allErrs.reduce(function(a, b){ return Math.max(a, num(b)); }, 0);
  yhi += maxErr; ylo -= maxErr;
  const pad = (yhi - ylo) * 0.08 || 1;
  ylo -= pad; yhi += pad;
  ys = lin(ylo, yhi, M.t + IH, M.t);
  xs = catScale(cats, view);
  const n = Math.max(1, series.length);
  const bw = Math.min(60, IW / Math.max(1, cats.length) / n * 0.8);
  svg.appendChild(axis(cats.map(function(c, i){ return {px: xs(i), label: c, rotate: cats.length > 5 ? 20 : 0}; }), ys, DATA.yLabel, DATA.xLabel));
  series.forEach(function(s, si){
    const off = (si - (n - 1) / 2) * bw;
    s.means.forEach(function(mv, i){
      const px = xs(i) + off, m = num(mv), e = num(s.errors[i]);
      const y1 = ys(m), y0 = ys(Math.max(ylo, 0));
      const rect = el("rect", {x: px - bw / 2, y: Math.min(y0, y1), width: bw, height: Math.abs(y1 - y0), fill: color(si), "fill-opacity": 0.85});
      svg.appendChild(rect);
      if (e > 0) svg.appendChild(el("line", {x1: px, y1: ys(m - e), x2: px, y2: ys(m + e), stroke: "#333", "stroke-width": 1.2}));
      const tipText = cats[i] + (s.name ? " · " + s.name : "") + "\n均值 " + fmt(m) + (e > 0 ? "  " + (DATA.errorMode || "误差") + " ±" + fmt(e) : "");
      addMark({x0: px - bw / 2, y0: Math.min(y0, y1), x1: px + bw / 2, y1: Math.max(y0, y1), tip: tipText});
    });
  });
}

function renderLine(){
  const d = DATA.data, cats = d.categories, series = d.series;
  const allMeans = series.flatMap(function(s){ return s.means; });
  const allErrs = series.flatMap(function(s){ return s.errors; });
  let ylo = Math.min.apply(null, allMeans.map(num));
  let yhi = Math.max.apply(null, allMeans.map(num));
  const maxErr = allErrs.reduce(function(a, b){ return Math.max(a, num(b)); }, 0);
  ylo -= maxErr; yhi += maxErr;
  const pad = (yhi - ylo) * 0.08 || 1;
  ylo -= pad; yhi += pad;
  ys = lin(ylo, yhi, M.t + IH, M.t);
  xs = catScale(cats, view);
  svg.appendChild(axis(cats.map(function(c, i){ return {px: xs(i), label: c, rotate: cats.length > 5 ? 20 : 0}; }), ys, DATA.yLabel, DATA.xLabel));
  series.forEach(function(s, si){
    const pts = s.means.map(function(mv, i){ return [xs(i), ys(num(mv))]; });
    const path = el("path", {d: pts.map(function(p, i){ return (i ? "L" : "M") + p[0] + " " + p[1]; }).join(" "), fill: "none", stroke: color(si), "stroke-width": 2});
    svg.appendChild(path);
    s.means.forEach(function(mv, i){
      const px = xs(i), py = ys(num(mv)), e = num(s.errors[i]);
      if (e > 0) svg.appendChild(el("line", {x1: px, y1: ys(num(mv) - e), x2: px, y2: ys(num(mv) + e), stroke: "#333", "stroke-width": 1.2}));
      svg.appendChild(el("circle", {cx: px, cy: py, r: 3.2, fill: color(si), stroke: "#fff", "stroke-width": 0.6}));
      const tipText = cats[i] + (s.name ? " · " + s.name : "") + "\n均值 " + fmt(mv) + (e > 0 ? "  " + (DATA.errorMode || "误差") + " ±" + fmt(e) : "");
      addMark({x0: px - 6, y0: py - 6, x1: px + 6, y1: py + 6, tip: tipText});
    });
  });
}

function renderScatter(){
  const d = DATA.data, series = d.series;
  const allx = series.flatMap(function(s){ return s.x.map(num); });
  const ally = series.flatMap(function(s){ return s.y.map(num); });
  let xlo = Math.min.apply(null, allx), xhi = Math.max.apply(null, allx);
  let ylo = Math.min.apply(null, ally), yhi = Math.max.apply(null, ally);
  const xpad = (xhi - xlo) * 0.05 || 1, ypad = (yhi - ylo) * 0.05 || 1;
  xlo -= xpad; xhi += xpad; ylo -= ypad; yhi += ypad;
  if (view && view.x) { xlo = view.x[0]; xhi = view.x[1]; }
  if (view && view.y) { ylo = view.y[0]; yhi = view.y[1]; }
  xs = lin(xlo, xhi, M.l, M.l + IW);
  ys = lin(ylo, yhi, M.t + IH, M.t);
  svg.appendChild(axis([], ys, d.yName || DATA.yLabel, d.xName || DATA.xLabel));
  // x 轴刻度（线性）
  const xticks = [];
  let xstep = Math.pow(10, Math.floor(Math.log10((xhi - xlo) || 1)));
  const xraw = (xhi - xlo) / xstep;
  if (xraw < 2) xstep /= 5; else if (xraw < 4) xstep /= 2; else if (xraw > 8) xstep *= 2;
  for (let v = Math.ceil(xlo / xstep) * xstep; v <= xhi + xstep * 1e-6; v += xstep) {
    xticks.push({px: xs(v), label: fmt(v)});
  }
  svg.appendChild(axis(xticks, ys, d.yName || DATA.yLabel, d.xName || DATA.xLabel));
  series.forEach(function(s, si){
    s.x.forEach(function(xv, i){
      const px = xs(num(xv)), py = ys(num(s.y[i]));
      svg.appendChild(el("circle", {cx: px, cy: py, r: 3, fill: color(si), "fill-opacity": 0.75}));
      addMark({x0: px - 5, y0: py - 5, x1: px + 5, y1: py + 5, tip: (s.name ? s.name + "\n" : "") + d.xName + " " + fmt(xv) + "\n" + d.yName + " " + fmt(s.y[i])});
    });
  });
  if (d.fit) {
    const a = num(d.fit.slope), b = num(d.fit.intercept);
    const f = function(v){ return a * v + b; };
    svg.appendChild(el("line", {x1: xs(xlo), y1: ys(f(xlo)), x2: xs(xhi), y2: ys(f(xhi)), stroke: "#333", "stroke-width": 1.6}));
  }
}

function renderBox(){
  const d = DATA.data, cats = d.categories, series = d.series;
  let ylo = Infinity, yhi = -Infinity;
  series.forEach(function(b){ ylo = Math.min(ylo, num(b.min)); yhi = Math.max(yhi, num(b.max)); });
  const pad = (yhi - ylo) * 0.08 || 1;
  ylo -= pad; yhi += pad;
  ys = lin(ylo, yhi, M.t + IH, M.t);
  xs = catScale(cats, view);
  const bw = Math.min(60, IW / Math.max(1, cats.length) * 0.55);
  svg.appendChild(axis(cats.map(function(c, i){ return {px: xs(i), label: c, rotate: cats.length > 5 ? 20 : 0}; }), ys, DATA.yLabel, DATA.xLabel));
  series.forEach(function(b, i){
    const px = xs(i);
    const tipText = b.name + "\nn = " + b.n + "\nmax " + fmt(b.max) + "\nQ3 " + fmt(b.q3) + "\n中位数 " + fmt(b.median) + "\nQ1 " + fmt(b.q1) + "\nmin " + fmt(b.min);
    svg.appendChild(el("line", {x1: px, y1: ys(num(b.min)), x2: px, y2: ys(num(b.max)), stroke: "#333"}));
    svg.appendChild(el("line", {x1: px - bw / 4, y1: ys(num(b.min)), x2: px + bw / 4, y2: ys(num(b.min)), stroke: "#333"}));
    svg.appendChild(el("line", {x1: px - bw / 4, y1: ys(num(b.max)), x2: px + bw / 4, y2: ys(num(b.max)), stroke: "#333"}));
    svg.appendChild(el("rect", {x: px - bw / 2, y: ys(num(b.q3)), width: bw, height: Math.max(1, ys(num(b.q1)) - ys(num(b.q3))), fill: color(i), "fill-opacity": 0.4, stroke: "#333"}));
    svg.appendChild(el("line", {x1: px - bw / 2, y1: ys(num(b.median)), x2: px + bw / 2, y2: ys(num(b.median)), stroke: "#333", "stroke-width": 2}));
    b.outliers.forEach(function(o){ svg.appendChild(el("circle", {cx: px, cy: ys(num(o)), r: 2.4, fill: "#333"})); });
    addMark({x0: px - bw / 2, y0: ys(num(b.max)), x1: px + bw / 2, y1: ys(num(b.min)), tip: tipText});
  });
}

function renderHist(){
  const d = DATA.data, series = d.series;
  let yhi = 0;
  series.forEach(function(s){ yhi = Math.max(yhi, Math.max.apply(null, s.counts.map(num))); });
  yhi *= 1.08;
  const lo = num(series[0].edges[0]), hi = num(series[0].edges[series[0].edges.length - 1]);
  xs = lin(lo, hi, M.l, M.l + IW);
  ys = lin(0, yhi, M.t + IH, M.t);
  const xticks = [];
  const xstep = (hi - lo) / Math.min(6, series[0].edges.length - 1) || 1;
  for (let v = lo; v <= hi + 1e-9; v += xstep) xticks.push({px: xs(v), label: fmt(v)});
  svg.appendChild(axis(xticks, ys, DATA.yLabel, DATA.xLabel));
  const n = Math.max(1, series.length);
  const bw = (IW / (series[0].edges.length - 1)) / n;
  series.forEach(function(s, si){
    const edges = s.edges.map(num);
    s.counts.forEach(function(c, i){
      const x0 = xs(edges[i]), x1 = xs(edges[i + 1]), y0 = ys(num(c)), y1 = ys(0);
      const rect = el("rect", {x: x0 + si * bw, y: y0, width: Math.max(0.5, bw - 0.5), height: Math.max(0, y1 - y0), fill: color(si), "fill-opacity": si ? 0.45 : 0.85});
      svg.appendChild(rect);
      const tipText = (s.name ? s.name + "\n" : "") + "[" + fmt(edges[i]) + ", " + fmt(edges[i + 1]) + ")\n计数 " + c;
      addMark({x0: x0 + si * bw, y0: y0, x1: x0 + si * bw + bw, y1: y1, tip: tipText});
    });
  });
}

function renderHeatmap(){
  const d = DATA.data, labels = d.labels, m = d.matrix;
  const n = labels.length;
  const cell = Math.min(IW, IH) / n;
  const ox = M.l + (IW - cell * n) / 2, oy = M.t + (IH - cell * n) / 2;
  const cmap = function(v){
    // RdBu 近似：-1 蓝 #2166ac，0 近白，+1 红 #b2182b
    const t = (v + 1) / 2;
    const r = Math.round(178 + (33 - 178) * t);
    const g = Math.round(24 + (102 - 24) * t);
    const b = Math.round(43 + (172 - 43) * t);
    return "rgb(" + r + "," + g + "," + b + ")";
  };
  labels.forEach(function(l, i){
    svg.appendChild(el("text", {x: ox + cell * i + cell / 2, y: M.t - 6, "text-anchor": "middle", "font-size": 10, fill: "#55554f", transform: "rotate(45 " + (ox + cell * i + cell / 2) + " " + (M.t - 6) + ")"}, l));
  });
  m.forEach(function(row, i){
    svg.appendChild(el("text", {x: ox - 6, y: oy + cell * i + cell / 2 + 3.5, "text-anchor": "end", "font-size": 10, fill: "#55554f"}, labels[i]));
    row.forEach(function(v, j){
      const x = ox + cell * j, y = oy + cell * i;
      const rect = el("rect", {x: x, y: y, width: cell, height: cell, fill: cmap(num(v)), stroke: "#fff", "stroke-width": 1});
      svg.appendChild(rect);
      svg.appendChild(el("text", {x: x + cell / 2, y: y + cell / 2 + 3.5, "text-anchor": "middle", "font-size": 10, fill: Math.abs(num(v)) > 0.6 ? "#fff" : "#222"}, fmt(v)));
      addMark({x0: x, y0: y, x1: x + cell, y1: y + cell, tip: labels[i] + " × " + labels[j] + "\nr = " + fmt(v)});
    });
  });
}

function render(){
  svg.innerHTML = "";
  marks = [];
  const ch = DATA.chart;
  if (ch === "bar") renderBar();
  else if (ch === "line") renderLine();
  else if (ch === "scatter") renderScatter();
  else if (ch === "box") renderBox();
  else if (ch === "hist") renderHist();
  else if (ch === "heatmap") renderHeatmap();
}

// ---------------- 交互：hover + 框选缩放 ----------------
let brushRect = null, brushStart = null, brushing = false;

function svgPoint(ev){
  const r = svg.getBoundingClientRect();
  return {x: (ev.clientX - r.left) * W / r.width, y: (ev.clientY - r.top) * H / r.height};
}
function hitTest(p){
  for (let i = marks.length - 1; i >= 0; i--) {
    const mk = marks[i];
    if (p.x >= mk.x0 && p.x <= mk.x1 && p.y >= mk.y0 && p.y <= mk.y1) return mk;
  }
  return null;
}
function showTip(mk, p){
  tip.textContent = mk.tip;
  tip.style.display = "block";
  const r = stage.getBoundingClientRect();
  let left = (p.x / W) * r.width + 12, top = (p.y / H) * r.height + 12;
  if (left + 340 > r.width) left = (p.x / W) * r.width - 352;
  if (top + 80 > r.height) top = (p.y / H) * r.height - 90;
  tip.style.left = left + "px";
  tip.style.top = top + "px";
}
svg.addEventListener("pointermove", function(ev){
  const p = svgPoint(ev);
  if (brushing && brushRect) {
    brushRect.setAttribute("x", Math.min(brushStart.x, p.x));
    brushRect.setAttribute("y", Math.min(brushStart.y, p.y));
    brushRect.setAttribute("width", Math.abs(p.x - brushStart.x));
    brushRect.setAttribute("height", Math.abs(p.y - brushStart.y));
    return;
  }
  const mk = hitTest(p);
  if (mk) showTip(mk, p); else tip.style.display = "none";
});
svg.addEventListener("pointerleave", function(){ if (!brushing) tip.style.display = "none"; });
svg.addEventListener("pointerdown", function(ev){
  if (ev.button !== 0 || !xs || !ys) return;
  const p = svgPoint(ev);
  if (hitTest(p)) return; // 点在数据上时不做框选，避免误触
  brushing = true; brushStart = p;
  brushRect = el("rect", {class: "brush", x: p.x, y: p.y, width: 0, height: 0});
  svg.appendChild(brushRect);
  svg.setPointerCapture(ev.pointerId);
});
svg.addEventListener("pointerup", function(ev){
  if (!brushing || !brushRect) return;
  brushing = false;
  const p = svgPoint(ev);
  const w = Math.abs(p.x - brushStart.x), h = Math.abs(p.y - brushStart.y);
  svg.removeChild(brushRect); brushRect = null;
  if (w < 6 && h < 6) return;
  const x0 = Math.min(brushStart.x, p.x), x1 = Math.max(brushStart.x, p.x);
  const y0 = Math.min(brushStart.y, p.y), y1 = Math.max(brushStart.y, p.y);
  const ch = DATA.chart;
  if (ch === "scatter") {
    view = {x: [xs.invert(x0), xs.invert(x1)], y: [ys.invert(y0), ys.invert(y1)]};
  } else if (ch !== "heatmap") {
    view = {x: [xs.invert(x0), xs.invert(x1)]};
  }
  render();
});
svg.addEventListener("dblclick", reset);

render();
</script>
</body>
</html>
"""


def emit_interactive_html(payload: dict[str, Any], out_dir: str, stem: str) -> dict[str, Any] | None:
    """把交互载荷写成一个自包含 HTML，返回与 files 条目同构的 dict。"""
    if not payload:
        return None
    title = str(payload.get("title") or stem).replace("<", "&lt;").replace(">", "&gt;")
    data_json = json.dumps(payload, ensure_ascii=False)
    html = (
        _INTERACTIVE_TEMPLATE
        .replace("__DATA__", data_json)
        .replace("__TITLE__", title)
    )
    target = Path(out_dir) / f"{stem}.interactive.html"
    target.write_text(html, encoding="utf-8")
    return {"format": "html", "path": str(target), "bytes": target.stat().st_size}


def make_figure(path: str, spec: dict[str, Any], out_dir: str, stem: str) -> dict[str, Any]:
    frame, info = load_table(path)
    stem = stem or "figure"
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    fig, context = draw(frame, spec)
    dpi = int(spec.get("dpi") or 300)
    files = []
    # 保存必须仍在同一份 rc 里：字体在 draw 时写进 Text 对象，但字形回退是在
    # savefig 绘制阶段解析的，rc 一退出就会退回 DejaVu Sans，中文变方框。
    with plt.rc_context(context["rc"]):
        for extension in ("pdf", "svg", "png"):
            target = output / f"{stem}.{extension}"
            kwargs = {"facecolor": "white"}
            if extension == "png":
                kwargs["dpi"] = dpi
            fig.savefig(target, **kwargs)
            files.append({"format": extension, "path": str(target), "bytes": target.stat().st_size})
    plt.close(fig)

    # 交互视图：与静态图同一份聚合数据，输出自包含 HTML，供面板 iframe 内嵌。
    # violin / raincloud 返回 None，面板退回静态预览。
    interactive = _interactive_data(frame, spec)
    if interactive:
        interactive_file = emit_interactive_html({
            "chart": interactive.get("chart"),
            "title": str(spec.get("title") or "").strip(),
            "xLabel": str(spec.get("xLabel") or ""),
            "yLabel": str(spec.get("yLabel") or ""),
            "errorMode": interactive.get("errorMode", ""),
            "note": f"数据 {Path(path).name}",
            "data": interactive,
        }, str(output), stem)
        if interactive_file:
            files.append(interactive_file)

    title = str(spec.get("title") or "").strip()
    caption = str(spec.get("caption") or "").strip()
    stats = context["stats"]
    # 不同图型记的 n 不一样：hist 记 n，scatter 记 n_points，bar/box 记每组计数。
    counts = stats.get("n_per_bar") or stats.get("n_per_group") or {}
    total_n = stats.get("n") or stats.get("n_points") or (sum(counts.values()) if counts else "")
    n_note = jsonable_n(total_n)
    # 只有柱图/折线图才有误差棒；散点与热图写「误差棒」是错的。
    error_note = ""
    if str(spec.get("chart") or "") in {"bar", "line"}:
        error_note = {
            "ci95": "误差棒为 95% 置信区间",
            "sem": "误差棒为 ±1 SEM",
            "sd": "误差棒为 ±1 SD",
            "none": "",
        }.get(str(spec.get("error") or "ci95"), "")
    body_bits = [bit for bit in (f"n = {n_note}" if n_note else "", error_note) if bit]
    head = caption or title
    # 图注按「标题句 → 数据与误差定义 → 来源与指纹」三段拼，避免用分号堆成一句。
    caption_draft = "".join(
        [
            f"{head}。" if head else "",
            f"{'，'.join(body_bits)}。" if body_bits else "",
            f"数据：{Path(path).name}（sha256 {info['sha256'][:12]}…）。",
        ]
    )

    return {
        "ok": True,
        "chart": spec.get("chart"),
        "journal": JOURNALS.get(str(spec.get("journal") or "nature").lower(), {}).get("label"),
        "files": files,
        "png": next((item["path"] for item in files if item["format"] == "png"), None),
        "caption": caption_draft,
        "n": len(frame),
        "dataset": info,
        "font": context["font"],
        "stats": context["stats"],
        "warnings": context["warnings"],
        "reading": [
            f"{JOURNALS.get(str(spec.get('journal') or 'nature').lower(), {}).get('label', '通用')} 版式：宽 {context['stats']['width_mm']} mm，"
            f"字号 {float(spec.get('fontSize') or JOURNALS['nature']['font'])} pt；投稿用 PDF/SVG，审阅用 PNG（{dpi} dpi）。",
            "图注要写清 n、误差棒含义、统计方法；这里已生成草稿，正文还要补单位与来源。",
        ],
    }


def jsonable_n(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value)
