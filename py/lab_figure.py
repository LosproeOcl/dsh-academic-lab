"""出版级出图：宽度按期刊栏宽、字号按期刊惯例、输出矢量 + 位图。

为什么自己画而不直接套 seaborn 主题：
- 期刊要的是「89 mm 宽、7 pt 字、无边框、色盲友好」这类硬约束，主题改起来比重写还麻烦；
- 每张图都要能回答「用了哪些行、多少 n、单位是什么」，这些要作为图注一起产出；
- 矢量 PDF/SVG 才是投稿件，PNG 只是审阅用。
"""

from __future__ import annotations

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
