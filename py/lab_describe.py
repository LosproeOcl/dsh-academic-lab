"""出图后的学术化饱和描述与预制 prompt。

make_figure 画完图后调用 build_description(spec, result)，把图型、数据、统计与
图注拼成两段文本：

- description：一段学术化的饱和描述，可直接当图注草稿，或作为 Agent 改写的素材；
- prompt：一段预制 prompt，交给 Agent 继续润色成可投稿的论文图注（figure caption）。

全部字段取自 make_figure 的返回 dict（result）与出图 spec，不重新读数据文件。
"""
from __future__ import annotations

from typing import Any

_CHART_CN = {
    "bar": "分组柱状图",
    "line": "折线图",
    "scatter": "散点图",
    "box": "箱线图",
    "violin": "小提琴图",
    "raincloud": "雨云图",
    "hist": "直方图",
    "heatmap": "相关矩阵热力图",
}

# stats_used["error"] 存的是「人类可读标签」，不是 spec 的 ci95/sem/sd 键。
_ERROR_VALUE_CN = {
    "95% CI of mean": "95% 置信区间",
    "SEM": "±1 标准误(SEM)",
    "SD": "±1 标准差(SD)",
    "none": "",
}


def _chart_cn(chart: str) -> str:
    return _CHART_CN.get(chart, chart or "图")


def _vars_note(spec: dict[str, Any]) -> str:
    chart = str(spec.get("chart") or "")
    if chart == "heatmap":
        cols = str(spec.get("columns") or "").strip()
        return f"变量：{cols or '（未指定列）'}"
    x = str(spec.get("x") or "").strip()
    y = str(spec.get("y") or "").strip()
    group = str(spec.get("group") or "").strip()
    bits = []
    if x:
        bits.append(f"横轴「{x}」")
    if y:
        bits.append(f"纵轴「{y}」")
    if group:
        bits.append(f"按「{group}」分组")
    return "变量：" + "，".join(bits) if bits else "变量：（未指定）"


def _summarize_stats(stats: dict[str, Any]) -> list[str]:
    """把 make_figure 的 stats_used 转成可读中文要点。"""
    out: list[str] = []
    chart = str(stats.get("chart") or "")
    if chart in {"bar", "line"}:
        if stats.get("n_per_bar"):
            parts = [f"{k}={v}" for k, v in stats["n_per_bar"].items()]
            out.append(f"各分组样本量：{'，'.join(parts)}")
        if stats.get("error"):
            label = _ERROR_VALUE_CN.get(str(stats["error"]), str(stats["error"]))
            if label:
                out.append(f"误差棒：{label}")
    elif chart == "scatter":
        if stats.get("n_points") is not None:
            out.append(f"散点数：{stats['n_points']}")
        if stats.get("fit"):
            slope = stats["fit"].get("slope")
            intercept = stats["fit"].get("intercept")
            out.append(f"最小二乘拟合：y = {intercept} + {slope}·x")
    elif chart in {"box", "violin", "raincloud"}:
        if stats.get("n_per_group"):
            parts = [f"{k}={v}" for k, v in stats["n_per_group"].items()]
            out.append(f"各分组样本量：{'，'.join(parts)}")
    elif chart == "hist":
        if stats.get("bins"):
            out.append(f"分箱数：{stats['bins']}")
        if stats.get("n") is not None:
            out.append(f"观测数：{stats['n']}")
    elif chart == "heatmap":
        if stats.get("n") is not None:
            out.append(f"纳入相关矩阵的完整观测数：{stats['n']}")
    return out


def build_description(spec: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    chart = str(spec.get("chart") or "")
    title = str(spec.get("title") or "").strip()
    caption = str(result.get("caption") or "").strip()
    stats = result.get("stats") or {}
    warnings = result.get("warnings") or []
    journal = str(result.get("journal") or "")
    dataset = result.get("dataset") or {}
    sha = str(dataset.get("sha256") or "")[:12]
    name = str(dataset.get("path") or "").rsplit("/", 1)[-1]

    stat_lines = _summarize_stats(stats)
    warn_lines = [str(w) for w in warnings][:3]

    # 纳入分析的观测数：与 make_figure 图注同口径（dropna 后）。
    counts = stats.get("n_per_bar") or stats.get("n_per_group") or {}
    plotted_n = stats.get("n") or stats.get("n_points") or (sum(counts.values()) if counts else None)
    raw_n = result.get("n")

    # —— 学术化饱和描述 ——
    desc_parts = [f"本图为{_chart_cn(chart)}，{_vars_note(spec)}。"]
    if plotted_n is not None:
        if raw_n and int(raw_n) != int(plotted_n):
            desc_parts.append(f"纳入分析的观测 n = {plotted_n}（数据文件共 {raw_n} 行，含缺失）。")
        else:
            desc_parts.append(f"纳入分析的观测 n = {plotted_n}。")
    elif raw_n:
        desc_parts.append(f"数据文件共 {raw_n} 行。")
    for line in stat_lines:
        desc_parts.append(line + "。")
    if warn_lines:
        desc_parts.append("数据质量提示：" + "；".join(warn_lines) + "。")
    if title:
        desc_parts.append(f"主题：{title}。")
    if caption:
        desc_parts.append(f"图注草稿：{caption}")
    description = "".join(desc_parts)

    # —— 预制 prompt ——
    prompt_lines = [
        "请为下面这幅图撰写一段学术化的论文图注（figure caption / legend），用于投稿发表。要求：",
        "① 首句用一句话说明图型与它展示的内容；",
        "② 给出样本量与分组方式；",
        "③ 说明统计方法，并在有显著性时给出效应量与置信区间（或 p 值）；",
        "④ 说明误差棒或变异度如何表示；",
        "⑤ 注明变量单位、观测期间与数据来源；",
        "⑥ 只陈述事实，不评价优劣，语言严谨。",
        "",
        "【图的信息】",
        f"- 图型：{_chart_cn(chart)}（{chart}）",
        f"- {_vars_note(spec)}",
    ]
    if plotted_n is not None:
        n_line = f"- 样本量：n = {plotted_n}"
        if raw_n and int(raw_n) != int(plotted_n):
            n_line += f"（数据文件共 {raw_n} 行，含缺失）"
        prompt_lines.append(n_line)
    elif raw_n:
        prompt_lines.append(f"- 样本量：数据文件共 {raw_n} 行")
    for line in stat_lines:
        prompt_lines.append(f"- {line}")
    if warn_lines:
        prompt_lines.append(f"- 数据质量：{'；'.join(warn_lines)}")
    if journal:
        prompt_lines.append(f"- 版式：{journal}")
    if name:
        prompt_lines.append(f"- 数据来源：{name}" + (f"（sha256 {sha}…）" if sha else ""))
    if caption:
        prompt_lines.append(f"- 现有草稿：{caption}")
    prompt = "\n".join(prompt_lines)

    return {"description": description, "prompt": prompt}
