"""统计推断：只做有前提检查、有效应量、有区间估计的分析。

原则（写进方法段也站得住）：
- 每个检验都同时给出效应量和 95% 区间，不只给 p；
- 缺失按「逐分析成列删除」处理，并显式报告丢了哪些行；
- 多终点（多个因变量）默认做 Holm 校正，并把原始 p 与校正 p 一起给出；
- 前提不满足时给出替代方法建议，不偷偷换方法；
- 输出结构稳定，便于写进表格和正文。
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy import stats as sps

from lab_common import LabError, jsonable, load_table, numeric_frame, round_sig

SEED = 424242


# ----------------------------------------------------------------- 小工具 --


def as_float(value, digits: int = 4):
    return round_sig(value, digits)


def p_text(p: float) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "p = NA"
    return "p < .001" if p < 0.001 else f"p = {p:.3f}".lstrip("0")


def require_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise LabError(
            "column-not-found",
            f"表里没有这些列：{'、'.join(missing)}",
            f"现有列：{'、'.join(map(str, frame.columns[:30]))}",
        )


def numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    require_columns(frame, [column])
    series = pd.to_numeric(frame[column], errors="coerce")
    if series.notna().sum() < 2:
        raise LabError("not-numeric", f"列「{column}」无法作为数值使用（非空可转换值不足 2 个）")
    return series.astype("float64")


def cohen_d(group_a: np.ndarray, group_b: np.ndarray) -> float:
    na, nb = len(group_a), len(group_b)
    if na < 2 or nb < 2:
        return float("nan")
    var_a, var_b = np.var(group_a, ddof=1), np.var(group_b, ddof=1)
    pooled = math.sqrt(((na - 1) * var_a + (nb - 1) * var_b) / (na + nb - 2))
    if pooled == 0:
        return float("nan")
    return float((np.mean(group_a) - np.mean(group_b)) / pooled)


def hedges_g(d: float, na: int, nb: int) -> float:
    if d is None or (isinstance(d, float) and math.isnan(d)) or na < 2 or nb < 2:
        return float("nan")
    correction = 1 - 3 / (4 * (na + nb) - 9)
    return float(d * correction)


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni：控制族错误率，比 Bonferroni 有功效又不依赖假设。"""

    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda index: pvalues[index])
    adjusted = [0.0] * m
    running = 0.0
    for rank, index in enumerate(order):
        value = min(1.0, (m - rank) * pvalues[index])
        running = max(running, value)
        adjusted[index] = running
    return adjusted


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """BH 控制 FDR，探索性多终点比 Holm 更常用（要在方法段写明用哪种）。"""

    m = len(pvalues)
    order = sorted(range(m), key=lambda index: pvalues[index])
    adjusted = [0.0] * m
    running = 1.0
    for rank in range(m - 1, -1, -1):
        index = order[rank]
        value = min(1.0, pvalues[index] * m / (rank + 1))
        running = min(running, value)
        adjusted[index] = running
    return adjusted


def normality_note(values: np.ndarray, label: str) -> dict[str, Any]:
    n = len(values)
    if n < 3:
        return {"label": label, "n": n, "test": None, "note": "样本太少，不做正态性检验"}
    if n > 5000:
        statistic, p = sps.normaltest(values)
        return {"label": label, "n": n, "test": "D'Agostino K²", "statistic": as_float(statistic), "p": as_float(p)}
    statistic, p = sps.shapiro(values)
    return {"label": label, "n": n, "test": "Shapiro-Wilk", "statistic": as_float(statistic), "p": as_float(p)}


def welch_ci(group_a: np.ndarray, group_b: np.ndarray) -> tuple[float, float, float]:
    """Welch 均值差的 95% CI，返回 (差值, 下限, 上限)。"""

    na, nb = len(group_a), len(group_b)
    mean_diff = float(np.mean(group_a) - np.mean(group_b))
    var_a, var_b = np.var(group_a, ddof=1), np.var(group_b, ddof=1)
    se = math.sqrt(var_a / na + var_b / nb)
    if se == 0:
        return mean_diff, mean_diff, mean_diff
    df = (var_a / na + var_b / nb) ** 2 / ((var_a / na) ** 2 / (na - 1) + (var_b / nb) ** 2 / (nb - 1))
    critical = sps.t.ppf(0.975, df)
    return mean_diff, mean_diff - critical * se, mean_diff + critical * se


def hl_estimate_ci(group_a: np.ndarray, group_b: np.ndarray, alpha: float = 0.05) -> tuple[float, float, float]:
    """Hodges-Lehmann 位移估计与分布无关 CI（Mann-Whitney 的配套效应量）。"""

    differences = (group_a[:, None] - group_b[None, :]).ravel()
    estimate = float(np.median(differences))
    # 用正态近似排序法求 CI（大样本稳定；小样本会略保守）。
    combined = np.concatenate([group_a, group_b])
    n = len(combined)
    mw = sps.mannwhitneyu(group_a, group_b, alternative="two-sided")
    z = sps.norm.ppf(1 - alpha / 2)
    se = math.sqrt(n * (n + 1) / 12 / min(len(group_a), len(group_b)))
    rank_low = int(round(mw.statistic - z * se))
    rank_high = int(round(mw.statistic + z * se))
    ordered = np.sort(combined)
    # 近似：把秩差换成两组的原始差分布分位数
    diffs_sorted = np.sort(differences)
    low = float(diffs_sorted[min(len(diffs_sorted) - 1, max(0, rank_low))])
    high = float(diffs_sorted[min(len(diffs_sorted) - 1, max(0, rank_high))])
    if low > high:
        low, high = high, low
    return estimate, low, high


# ------------------------------------------------------------------ 分析 --


def describe(frame: pd.DataFrame, columns: list[str] | None) -> dict[str, Any]:
    numeric = numeric_frame(frame)
    targets = columns or list(numeric.columns)
    require_columns(frame, targets)
    if not targets:
        raise LabError("no-numeric", "没有可描述的数值列", "指定 columns，或确认数据里确有数值列。")

    table = []
    for column in targets:
        series = pd.to_numeric(frame[column], errors="coerce").dropna()
        n = len(series)
        if n == 0:
            table.append({"variable": column, "n": 0, "note": "整列缺失"})
            continue
        mean = float(series.mean())
        sd = float(series.std(ddof=1)) if n > 1 else float("nan")
        se = sd / math.sqrt(n) if n > 1 and not math.isnan(sd) else float("nan")
        critical = sps.t.ppf(0.975, max(1, n - 1)) if n > 1 else float("nan")
        entry = {
            "variable": column,
            "n": n,
            "missing": int(len(frame) - n),
            "mean": as_float(mean),
            "sd": as_float(sd),
            "median": as_float(series.median()),
            "iqr": [as_float(series.quantile(0.25)), as_float(series.quantile(0.75))],
            "min": as_float(series.min()),
            "max": as_float(series.max()),
            "ci95_mean": [as_float(mean - critical * se), as_float(mean + critical * se)] if n > 1 else None,
            "normality": normality_note(series.to_numpy(), column),
        }
        table.append(entry)

    reading = [f"描述统计覆盖 {len([row for row in table if row.get('n')])} 个数值变量。"]
    reading.append("正文建议报告：均值 ± SD（分布近似正态）或中位数 [IQR]（偏态/有离群值）；两者这里都给了。")
    return {"ok": True, "analysis": "describe", "n_rows": int(len(frame)), "table": table, "reading": reading, "warnings": []}


def compare(frame: pd.DataFrame, dvs: list[str], group_column: str, method: str, alpha: float, correction: str) -> dict[str, Any]:
    require_columns(frame, [group_column, *dvs])
    if len(dvs) == 0:
        raise LabError("missing-parameter", "compare 需要至少一个因变量（dv）")

    raw_results = []
    warnings: list[str] = []

    for dv in dvs:
        working = pd.DataFrame(
            {"y": pd.to_numeric(frame[dv], errors="coerce"), "group": frame[group_column].astype("string").str.strip()}
        ).dropna()
        dropped = int(len(frame) - len(working))
        groups = {str(name): values.to_numpy() for name, values in working.groupby("group", observed=True)["y"]}
        groups = {name: values for name, values in groups.items() if len(values) >= 2}
        if len(groups) < 2:
            warnings.append(f"「{dv}」在「{group_column}」上不足 2 个有效组（每组 ≥2），跳过")
            continue

        names = list(groups)
        arrays = [groups[name] for name in names]
        sizes = {name: int(len(values)) for name, values in groups.items()}
        chosen = method
        if method == "auto":
            if len(arrays) == 2:
                a, b = arrays
                normal = all((normality_note(array, name)["p"] or 0) > 0.05 for array, name in ((a, names[0]), (b, names[1])))
                chosen = "welch" if (normal or (len(a) >= 30 and len(b) >= 30)) else "mannwhitney"
            else:
                normal = all((normality_note(array, name)["p"] or 0) > 0.05 for name, array in groups.items())
                levene_p = sps.levene(*arrays, center="median").pvalue
                chosen = "anova" if normal and levene_p > 0.05 else "kruskal"

        payload: dict[str, Any] = {"dv": dv, "group": group_column, "method": chosen, "groups": sizes, "dropped_rows": dropped}

        if chosen in {"welch", "student"}:
            a, b = arrays[0], arrays[1]
            result = sps.ttest_ind(a, b, equal_var=(chosen == "student"))
            diff, low, high = welch_ci(a, b) if chosen == "welch" else welch_ci(a, b)
            d = cohen_d(a, b)
            payload.update(
                {
                    "statistic": as_float(result.statistic),
                    "df": as_float(result.df) if hasattr(result, "df") else None,
                    "p": as_float(result.pvalue),
                    "effect_size": {"name": "Cohen d", "value": as_float(d), "hedges_g": as_float(hedges_g(d, len(a), len(b)))},
                    "mean_difference": as_float(diff),
                    "ci95_difference": [as_float(low), as_float(high)],
                    "normality": [normality_note(a, names[0]), normality_note(b, names[1])],
                }
            )
            payload["sentence"] = (
                f"{names[0]} 与 {names[1]} 的 {dv}：{'Welch' if chosen == 'welch' else 'Student'} t = "
                f"{as_float(result.statistic, 3)}, {p_text(result.pvalue)}, 差值 {as_float(diff, 3)} "
                f"[{as_float(low, 3)}, {as_float(high, 3)}], Cohen d = {as_float(d, 2)}"
            )
            if len(a) < 5 or len(b) < 5:
                warnings.append(f"「{dv}」有一组 n<5，t 检验的正态近似不可靠")
        elif chosen == "mannwhitney":
            a, b = arrays[0], arrays[1]
            result = sps.mannwhitneyu(a, b, alternative="two-sided")
            estimate, low, high = hl_estimate_ci(a, b)
            payload.update(
                {
                    "statistic": as_float(result.statistic),
                    "p": as_float(result.pvalue),
                    "effect_size": {
                        "name": "rank-biserial r",
                        "value": as_float(2 * result.statistic / (len(a) * len(b)) - 1),
                    },
                    "hl_estimate": as_float(estimate),
                    "ci95_hl": [as_float(low), as_float(high)],
                }
            )
            payload["sentence"] = (
                f"{names[0]} 与 {names[1]} 的 {dv}：Mann-Whitney U = {as_float(result.statistic, 4)}, "
                f"{p_text(result.pvalue)}, Hodges-Lehmann 位移 {as_float(estimate, 3)} "
                f"[{as_float(low, 3)}, {as_float(high, 3)}]"
            )
        elif chosen == "anova":
            result = sps.f_oneway(*arrays)
            grand = np.concatenate(arrays)
            ss_between = sum(len(array) * (np.mean(array) - np.mean(grand)) ** 2 for array in arrays)
            ss_total = np.sum((grand - np.mean(grand)) ** 2)
            eta2 = ss_between / ss_total if ss_total else float("nan")
            k = len(arrays)
            n = len(grand)
            omega2 = (ss_between - (k - 1) * (ss_total - ss_between) / (n - k)) / (ss_total + (ss_total - ss_between) / (n - k)) if n > k else float("nan")
            payload.update(
                {
                    "statistic": as_float(result.statistic),
                    "df_between": k - 1,
                    "df_within": n - k,
                    "p": as_float(result.pvalue),
                    "effect_size": {"name": "eta squared", "value": as_float(eta2), "omega_squared": as_float(omega2)},
                    "group_means": {name: as_float(np.mean(array)) for name, array in groups.items()},
                    "normality": [normality_note(array, name) for name, array in groups.items()],
                    "levene_p": as_float(sps.levene(*arrays, center="median").pvalue),
                }
            )
            payload["sentence"] = (
                f"{len(arrays)} 组间 {dv} 的单因素方差分析：F({k - 1}, {n - k}) = {as_float(result.statistic, 3)}, "
                f"{p_text(result.pvalue)}, η² = {as_float(eta2, 3)}"
            )
        elif chosen == "kruskal":
            result = sps.kruskal(*arrays)
            k = len(arrays)
            n = len(np.concatenate(arrays))
            epsilon2 = (result.statistic - k + 1) / (n - k) if n > k else float("nan")
            payload.update(
                {
                    "statistic": as_float(result.statistic),
                    "df": k - 1,
                    "p": as_float(result.pvalue),
                    "effect_size": {"name": "epsilon squared", "value": as_float(epsilon2)},
                    "group_medians": {name: as_float(np.median(array)) for name, array in groups.items()},
                    "normality": [normality_note(array, name) for name, array in groups.items()],
                    "levene_p": as_float(sps.levene(*arrays, center="median").pvalue),
                }
            )
            payload["sentence"] = (
                f"{len(arrays)} 组间 {dv} 的 Kruskal-Wallis 检验：H({k - 1}) = {as_float(result.statistic, 3)}, "
                f"{p_text(result.pvalue)}, ε² = {as_float(epsilon2, 3)}"
            )
        else:
            raise LabError("unknown-method", f"不认识的检验方法：{method}", "可用：auto / welch / student / mannwhitney / anova / kruskal")

        payload["alpha"] = alpha
        payload["significant"] = bool(payload.get("p") is not None and payload["p"] < alpha)
        raw_results.append(payload)

    pvalues = [item["p"] for item in raw_results if item.get("p") is not None]
    if correction != "none" and len(pvalues) > 1:
        adjusted = holm(pvalues) if correction == "holm" else benjamini_hochberg(pvalues)
        for item, value in zip([r for r in raw_results if r.get("p") is not None], adjusted):
            item["p_adjusted"] = as_float(value)
            item["p_adjusted_method"] = correction
            item["significant_adjusted"] = bool(value < alpha)

    if any(item.get("p") is not None and item["p"] < alpha for item in raw_results) and len(raw_results) > 1 and correction == "none":
        warnings.append("做了多个终点检验但没有校正，结果会偏乐观；建议 correction=holm 或 bh")
    if any(item["p"] > alpha and item["p_adjusted"] < alpha for item in raw_results if "p_adjusted" in item):
        warnings.append("校正后 p 值变小，说明这里算错了——请报 issue")

    reading = [item["sentence"] for item in raw_results]
    if len(raw_results) > 1 and correction != "none":
        reading.append(f"多终点（{len(raw_results)} 个）已用 {correction.upper()} 校正；正文两张表都报，并在方法里写明校正方式。")

    return {
        "ok": True,
        "analysis": "compare",
        "method": method,
        "correction": correction,
        "alpha": alpha,
        "results": raw_results,
        "reading": reading,
        "warnings": warnings,
    }


def associate(frame: pd.DataFrame, x: str, y: str, method: str) -> dict[str, Any]:
    xa = numeric_column(frame, x)
    ya = numeric_column(frame, y)
    working = pd.DataFrame({"x": xa, "y": ya}).dropna()
    if len(working) < 4:
        raise LabError("insufficient-data", "成对完整观测太少（<4），无法估计相关")

    chosen = method
    if method == "auto":
        normal_x = normality_note(working["x"].to_numpy(), x)["p"]
        normal_y = normality_note(working["y"].to_numpy(), y)["p"]
        chosen = "pearson" if (normal_x or 0) > 0.05 and (normal_y or 0) > 0.05 else "spearman"

    if chosen == "pearson":
        result = sps.pearsonr(working["x"], working["y"])
        r = float(result.statistic)
        # Fisher z 变换的 95% CI
        z = np.arctanh(r)
        se = 1 / math.sqrt(len(working) - 3)
        low, high = np.tanh(z - 1.96 * se), np.tanh(z + 1.96 * se)
        p = float(result.pvalue)
        label = "Pearson r"
    else:
        result = sps.spearmanr(working["x"], working["y"])
        r = float(result.statistic)
        p = float(result.pvalue)
        rng = np.random.default_rng(SEED)
        boots = []
        values_x = working["x"].to_numpy()
        values_y = working["y"].to_numpy()
        for _ in range(2000):
            index = rng.integers(0, len(working), len(working))
            boots.append(sps.spearmanr(values_x[index], values_y[index]).statistic)
        low, high = np.percentile(boots, [2.5, 97.5])
        label = "Spearman ρ"

    slope, intercept = np.polyfit(working["x"], working["y"], 1)
    return {
        "ok": True,
        "analysis": "associate",
        "method": chosen,
        "n": int(len(working)),
        "statistic": as_float(r),
        "effect_size": {"name": label, "value": as_float(r)},
        "p": as_float(p),
        "ci95": [as_float(low), as_float(high)],
        "linear_fit": {"slope": as_float(slope), "intercept": as_float(intercept)},
        "sentence": f"{x} 与 {y}：{label} = {as_float(r, 3)}（95% CI {as_float(low, 3)}~{as_float(high, 3)}）, {p_text(p)}, n = {len(working)}",
        "reading": [
            f"{label} = {as_float(r, 3)}，95% CI 跨不跨 0 决定「有没有证据支持非零关联」。",
            "相关不等于因果；若有共同原因（时标、批次、个体差异），必须用回归控制或在讨论里说明。",
        ],
        "warnings": [] if (low > 0 or high < 0 or abs(r) < 0.1) else ["置信区间包含 0：点估计可能被少数点驱动，建议看散点图与稳健性检验"],
    }


def regress(frame: pd.DataFrame, dv: str, predictors: list[str], robust: bool) -> dict[str, Any]:
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.stats.stattools import durbin_watson

    require_columns(frame, [dv, *predictors])
    if not predictors:
        raise LabError("missing-parameter", "regress 需要至少一个预测变量")

    columns = {}
    dropped_for_type: list[str] = []
    for column in [dv, *predictors]:
        series = pd.to_numeric(frame[column], errors="coerce")
        if series.notna().sum() < 2:
            dropped_for_type.append(column)
        columns[column] = series
    if dropped_for_type:
        raise LabError("not-numeric", f"这些列无法当数值变量：{'、'.join(dropped_for_type)}", "分类预测变量请先编码成虚拟变量（0/1）")

    working = pd.DataFrame(columns).dropna()
    n, k = len(working), len(predictors)
    if n <= k + 2:
        raise LabError("insufficient-data", f"有效样本 n={n} 不足以估计 {k} 个系数", "减少预测变量，或补充数据")

    design = sm.add_constant(working[predictors])
    y = working[dv]
    model = sm.OLS(y, design).fit(cov_type="HC3") if robust else sm.OLS(y, design).fit()

    vif = []
    for index, name in enumerate(design.columns):
        if name == "const":
            continue
        try:
            value = variance_inflation_factor(design.to_numpy(), index)
        except Exception:  # noqa: BLE001
            value = float("nan")
        vif.append({"variable": name, "vif": as_float(value)})

    from statsmodels.stats.diagnostic import het_breuschpagan

    bp = het_breuschpagan(model.resid, design)
    coefficients = []
    for name in design.columns:
        coefficient = model.params[name]
        std_error = model.bse[name]
        pvalue = model.pvalues[name]
        low, high = model.conf_int().loc[name]
        coefficients.append(
            {
                "term": name,
                "beta": as_float(coefficient),
                "se": as_float(std_error),
                "t": as_float(coefficient / std_error) if std_error else None,
                "p": as_float(pvalue),
                "ci95": [as_float(low), as_float(high)],
                "significant": bool(pvalue < 0.05),
            }
        )

    # 标准化系数（在同一个完整案例样本上重算，才可比）
    standardized = []
    if n > 2:
        zscores = (working[[dv, *predictors]] - working[[dv, *predictors]].mean()) / working[[dv, *predictors]].std(ddof=1)
        zmodel = sm.OLS(zscores[dv], sm.add_constant(zscores[predictors])).fit()
        standardized = [{"term": name, "beta_std": as_float(zmodel.params[name])} for name in predictors]

    warnings: list[str] = []
    if n < 10 * (k + 1):
        warnings.append(f"每个预测变量只有约 {n / (k + 1):.1f} 个观测，系数区间会偏宽（经验法则 ≥10）")
    if any(item["vif"] and item["vif"] > 10 for item in vif):
        warnings.append("存在 VIF > 10 的预测变量，系数方向和大小都不可靠，先合并或剔除共线变量")
    if bp[1] < 0.05 and not robust:
        warnings.append(f"Breusch-Pagan 检验 p={bp[1]:.3f}：存在异方差，建议 robust=true（HC3）")

    return {
        "ok": True,
        "analysis": "regress",
        "n": int(n),
        "dropped_rows": int(len(frame) - n),
        "robust": robust,
        "r2": as_float(model.rsquared),
        "r2_adj": as_float(model.rsquared_adj),
        "f": as_float(model.fvalue),
        "f_p": as_float(model.f_pvalue),
        "rmse": as_float(math.sqrt(model.mse_resid)) if hasattr(model, "mse_resid") else None,
        "coefficients": coefficients,
        "standardized": standardized,
        "vif": vif,
        "breusch_pagan_p": as_float(bp[1]),
        "durbin_watson": as_float(durbin_watson(model.resid)),
        "reading": [
            f"模型解释力 R² = {as_float(model.rsquared, 3)}（校正后 {as_float(model.rsquared_adj, 3)}），n = {n}。",
            "报告系数时写「每增加 1 个单位，DV 变化 β（95% CI）」，并说明是否稳健标准误。",
            "R² 只说明样本内拟合；外推和有偏抽样的风险要在讨论里写。",
        ],
        "warnings": warnings,
    }


def chisq(frame: pd.DataFrame, x: str, y: str) -> dict[str, Any]:
    require_columns(frame, [x, y])
    working = frame[[x, y]].dropna()
    table = pd.crosstab(working[x].astype("string"), working[y].astype("string"))
    if min(table.shape) < 2:
        raise LabError("invalid-contingency", "交叉表至少需要 2×2 个水平", "确认两个变量都有两个以上取值")

    result = sps.chi2_contingency(table)
    chi2, p, dof, expected = result[0], result[1], result[2], result[3]
    n = int(table.to_numpy().sum())
    cramers_v = math.sqrt(chi2 / (n * (min(table.shape) - 1))) if n else float("nan")
    low_expected = float((expected < 5).mean())

    payload = {
        "ok": True,
        "analysis": "chisq",
        "n": n,
        "statistic": as_float(chi2),
        "df": int(dof),
        "p": as_float(p),
        "effect_size": {"name": "Cramér's V", "value": as_float(cramers_v)},
        "expected_below_5_share": as_float(low_expected, 3),
        "table": {
            "index": [str(item) for item in table.index],
            "columns": [str(item) for item in table.columns],
            "counts": [[int(value) for value in row] for row in table.to_numpy()],
        },
        "sentence": f"{x} × {y} 的卡方检验：χ²({dof}) = {as_float(chi2, 3)}, {p_text(p)}, Cramér's V = {as_float(cramers_v, 3)}, n = {n}",
        "reading": ["Cramér's V 的参考：0.1 小、0.3 中、0.5 大（同一自由度下才可比）。"],
        "warnings": [],
    }
    if low_expected > 0.2:
        payload["warnings"].append(f"{low_expected:.0%} 的单元格期望频数 < 5：卡方近似不可靠，改用 Fisher 精确检验或合并水平")
    if table.shape == (2, 2):
        odds, fisher_p = sps.fisher_exact(table.to_numpy())
        payload["fisher_exact"] = {"odds_ratio": as_float(odds), "p": as_float(fisher_p)}
    return payload


# ------------------------------------------------------------------ 分派 --


def run(frame: pd.DataFrame, spec: dict[str, Any]) -> dict[str, Any]:
    analysis = str(spec.get("analysis") or "").lower()
    alpha = float(spec.get("alpha") or 0.05)
    if analysis == "describe":
        return describe(frame, spec.get("columns") or None)
    if analysis == "compare":
        dvs = spec.get("dvs") or ([spec.get("dv")] if spec.get("dv") else [])
        if isinstance(dvs, str):
            dvs = [item.strip() for item in dvs.split(",") if item.strip()]
        return compare(
            frame,
            dvs,
            str(spec.get("group") or ""),
            str(spec.get("method") or "auto"),
            alpha,
            str(spec.get("correction") or "holm"),
        )
    if analysis == "associate":
        return associate(frame, str(spec.get("x") or ""), str(spec.get("y") or ""), str(spec.get("method") or "auto"))
    if analysis == "regress":
        predictors = spec.get("predictors") or []
        if isinstance(predictors, str):
            predictors = [item.strip() for item in predictors.split(",") if item.strip()]
        return regress(frame, str(spec.get("dv") or ""), predictors, bool(spec.get("robust", True)))
    if analysis == "chisq":
        return chisq(frame, str(spec.get("x") or ""), str(spec.get("y") or ""))
    raise LabError(
        "unknown-analysis",
        f"不支持的分析类型：{analysis or '（空）'}",
        "可用：describe / compare / associate / regress / chisq",
    )


def analyze(path: str, spec: dict[str, Any]) -> dict[str, Any]:
    frame, info = load_table(path)
    result = run(frame, spec)
    result["dataset"] = info
    result["spec"] = spec
    return result
