"""图库与选图判读。

两块能力：
1. 图库（build_gallery）：每种图型一张「示例板」，讲清楚它是什么、解决什么问题、
   数据要什么、怎么读、常见误用——降低用户从数据到图的信息熵。
2. 判读（recommend）：拿到数据画像 + 一句研究问题（我想看什么），给出该画哪种图、
   用哪些列、为什么。推荐里的 spec 可直接交给 /figure 路由出图。

内容取向：学术数据科学为主（8 种统计图），辅以 data-viz-gen 的信息图类型
（统计卡片 / 对比柱状 / 流程 / 仪表盘，绘制在后续阶段接入）。
参考：FT Visual Vocabulary 的九大类、From Data to Viz 的决策树。
"""

from __future__ import annotations

from typing import Any

# ------------------------------------------------------------- 图库元数据 --

# 每张示例板字段：
#   id          与引擎 chart 名一致（信息图用独立 id）
#   name/name_en
#   category    分组（面板按它聚合）
#   kind        academic（学术统计图）| infographic（信息图）
#   summary     卡片副标题（一句话）
#   definition  是什么
#   purpose     解决什么问题 / 何时用
#   data        数据要求
#   read        怎么读
#   pitfalls    常见误用
#   engine      绘制方式；None 表示绘制尚未接入（信息图在后续阶段）
#   requires    需要的列尺度（x/y/group 的取值，供表单提示）

GALLERY: list[dict[str, Any]] = [
    {
        "id": "bar",
        "name": "柱状图",
        "name_en": "Bar chart",
        "category": "比较",
        "category_en": "Comparison",
        "kind": "academic",
        "summary": "比较类别之间的数值大小",
        "definition": "用矩形条的高度表示不同类别上的一个数值指标（均值、频数、百分比）。",
        "purpose": "比较离散类别之间的数量差异，回答「谁多谁少、差多少」。适合分组均值、计数、占比的横向对比。",
        "data": "1 个类别列（x，水平 ≤ 12 个，否则换横向条形或排序取前几）+ 1 个数值列（y）；可选 1 个分组列做分组柱状。",
        "read": "横轴是类别，纵轴是数值；柱越高数值越大；误差棒表示不确定性（95% CI / SEM / SD）。",
        "pitfalls": [
            "纵轴不从 0 开始会夸大差异，视觉比例失真",
            "类别过多（>12）时标签挤成一团，改横向条形图或排序后取前几",
            "同一张图堆太多系列（>4）难以比较，改分面",
            "不要用柱状图表示随时间连续变化的趋势（该用折线图）",
        ],
        "engine": {"command": "figure", "chart": "bar"},
        "requires": {"x": "categorical", "y": "numeric", "group": "optional"},
    },
    {
        "id": "line",
        "name": "折线图",
        "name_en": "Line chart",
        "category": "趋势",
        "category_en": "Trend",
        "kind": "academic",
        "summary": "展示数值随有序变量的变化",
        "definition": "用点加连线表示一个数值随另一个有序变量（时间、剂量、年龄）的变化。",
        "purpose": "展示变化趋势、轨迹与斜率，回答「随 X 变化，Y 怎么变」。适合时间序列、剂量-反应、年龄-指标。",
        "data": "1 个有序 x（时间 / 日期 / 有序类别）+ 1 个数值 y；可选分组列画多条线。",
        "read": "看整体趋势（升 / 降 / 拐点 / 平台期），单点波动往往是噪声；多条线比较斜率。",
        "pitfalls": [
            "x 不是有序变量时折线会暗示不存在的连续性",
            "点数太少（<4）时折线不如散点",
            "双 y 轴易误导，慎用",
            "缺失的时间点会扭曲斜率，注意标注断点",
        ],
        "engine": {"command": "figure", "chart": "line"},
        "requires": {"x": "ordered/date", "y": "numeric", "group": "optional"},
    },
    {
        "id": "scatter",
        "name": "散点图",
        "name_en": "Scatter plot",
        "category": "相关",
        "category_en": "Correlation",
        "kind": "academic",
        "summary": "看两个连续变量之间的关系",
        "definition": "每个观测一个点，横纵各一个数值变量，点落在二维平面。",
        "purpose": "看两个连续变量之间有没有关系、线性还是非线性、有没有离群点，回答「X 和 Y 相关吗」。",
        "data": "2 个数值列（x、y）；可选分组列用颜色区分；可选拟合线 + CI 带。",
        "read": "整体形状（正 / 负 / 无 / 非线性）、离群点、聚成几团；拟合线看趋势，散点看离散。",
        "pitfalls": [
            "相关不等于因果",
            "大样本时点重叠成团，可加透明度或抖动",
            "离群点会强拉回归线，注意标注",
            "分类变量散点会堆成竖线（该用箱线图 / 小提琴图）",
        ],
        "engine": {"command": "figure", "chart": "scatter"},
        "requires": {"x": "numeric", "y": "numeric", "group": "optional"},
    },
    {
        "id": "box",
        "name": "箱线图",
        "name_en": "Box plot",
        "category": "分布",
        "category_en": "Distribution",
        "kind": "academic",
        "summary": "概括一组分布的中心、离散与离群点",
        "definition": "用中位数、四分位距与须线概括一组连续数据的分布，并标出离群点。",
        "purpose": "比较多组分布的中心、离散度和离群点，回答「各组分布差多少、有没有异常值」。",
        "data": "1 个类别列（x）+ 1 个数值列（y）；可选分组列。",
        "read": "箱子 = 四分位距（中间 50% 数据），中线 = 中位数，须线 ≈ 1.5×IQR 内的极值，点 = 离群值。",
        "pitfalls": [
            "n 很小时（<5）箱线图几乎无信息，用点 + 抖动更诚实",
            "会隐藏多峰分布（该用小提琴图 / 直方图看形状）",
            "离群点是统计约定（1.5×IQR），不一定是「错误数据」",
        ],
        "engine": {"command": "figure", "chart": "box"},
        "requires": {"x": "categorical", "y": "numeric", "group": "optional"},
    },
    {
        "id": "violin",
        "name": "小提琴图",
        "name_en": "Violin plot",
        "category": "分布",
        "category_en": "Distribution",
        "kind": "academic",
        "summary": "展示分布的完整形状",
        "definition": "箱线图加旋转的密度曲线，同时展示分布形状和多组比较。",
        "purpose": "看分布的完整形状（多峰、偏态、双峰），比箱线图多一层信息，回答「分布长什么样」。",
        "data": "1 个类别列（x）+ 1 个数值列（y）；可选分组列。",
        "read": "宽 = 数据密、窄 = 稀疏；可叠加中位数 / 四分位点；对称 / 偏态 / 多峰一眼可见。",
        "pitfalls": [
            "小样本（<20）时密度估计不稳，会画出假的多峰",
            "密度曲线面积无统计意义，容易误读为概率",
            "类别很多时每个小提琴变窄，读起来费劲",
        ],
        "engine": {"command": "figure", "chart": "violin"},
        "requires": {"x": "categorical", "y": "numeric", "group": "optional"},
    },
    {
        "id": "raincloud",
        "name": "雨云图",
        "name_en": "Rain cloud plot",
        "category": "分布",
        "category_en": "Distribution",
        "kind": "academic",
        "summary": "分布形状 + 原始数据 + 概括统计三合一",
        "definition": "半小提琴（云）+ 抖动散点（雨）+ 箱线（须）叠在一起的「原始数据友好」分布图。",
        "purpose": "同时给分布形状、每个观测点和概括统计，避免只给箱线图而隐藏个体差异，回答「分布 + 原始数据 + 个体都在哪」。",
        "data": "1 个类别列（x）+ 1 个数值列（y）。",
        "read": "云 = 分布、雨点 = 每个观测、须 = 四分位；点数能直接数出来。",
        "pitfalls": [
            "样本很大时散点重叠，需降采样或调透明度",
            "组很多时每组分到的宽度不够",
            "学术出版里比较新，部分审稿人不熟悉，备好箱线图解释",
        ],
        "engine": {"command": "figure", "chart": "raincloud"},
        "requires": {"x": "categorical", "y": "numeric"},
    },
    {
        "id": "hist",
        "name": "直方图",
        "name_en": "Histogram",
        "category": "分布",
        "category_en": "Distribution",
        "kind": "academic",
        "summary": "看单变量的分布形状",
        "definition": "把连续变量切成等宽区间，用柱高表示每个区间内的观测数。",
        "purpose": "看单变量的分布形状、中心、离散、偏态、多峰，回答「这一列数据怎么分布」。",
        "data": "1 个数值列（x）；可选分组列叠加 / 分面。",
        "read": "柱高 = 频数，读整体形状（正态 / 偏态 / 双峰 / 长尾），不是读单根柱。",
        "pitfalls": [
            "bin 宽度直接影响形状（太细 = 噪声，太粗 = 丢细节），需试几个",
            "纵轴频数 vs 密度不能混用",
            "别把直方图当柱状图（柱状图 x 是类别、柱间有间隙；直方图 x 连续、柱相邻）",
        ],
        "engine": {"command": "figure", "chart": "hist"},
        "requires": {"x": "numeric", "group": "optional"},
    },
    {
        "id": "heatmap",
        "name": "热力图",
        "name_en": "Heatmap",
        "category": "相关",
        "category_en": "Correlation",
        "kind": "academic",
        "summary": "一次看清多个变量的两两关系",
        "definition": "用颜色深浅表示矩阵里每个格子的大小（常为多个变量两两相关）。",
        "purpose": "一次看清多个变量之间的两两关系，或二维交叉表的强度，回答「哪些变量聚在一起」。",
        "data": "2+ 个数值列（做相关矩阵）；或两个类别列做交叉计数。",
        "read": "颜色越深相关越强（看色标）；对角线 = 1；找「深色块」= 高度相关的变量团。",
        "pitfalls": [
            "色标要选感知均匀的（发散色标用于正负相关）",
            "变量很多时标签要旋转 / 缩写，否则读不了",
            "相关矩阵是线性的，非线性关系会被低估",
        ],
        "engine": {"command": "figure", "chart": "heatmap"},
        "requires": {"columns": "numeric 2+"},
    },
    {
        "id": "stats",
        "name": "统计卡片",
        "name_en": "Stat card",
        "category": "概览",
        "category_en": "Overview",
        "kind": "infographic",
        "summary": "大号数字呈现关键指标",
        "definition": "大号数字 + 标签 + 小字说明的 KPI 卡片，一张或一组。",
        "purpose": "把关键指标一眼打到读者面前，用于摘要 / 看板 / 首页，回答「核心数字是多少」。",
        "data": "若干「标签 + 数值 + 说明」键值对。",
        "read": "先读大数字，再读标签和说明；一组卡片按重要性排序。",
        "pitfalls": [
            "别堆太多卡片（>6 失去焦点）",
            "数字要给单位与口径",
            "别把不相关的指标并列制造虚假因果联想",
        ],
        "engine": None,
        "requires": None,
    },
    {
        "id": "comparison",
        "name": "对比柱状",
        "name_en": "Comparison bars",
        "category": "比较",
        "category_en": "Comparison",
        "kind": "infographic",
        "summary": "信息图风格的两项 / 多项对比",
        "definition": "信息图风格的柱状对比，强调两组 / 多项之间的差值，常带图标和强调色。",
        "purpose": "汇报 / 演示里快速呈现「A vs B」的数量对比，回答「谁更大、大多少」。",
        "data": "「项目 + 数值」列表（一维）。",
        "read": "看相对长短，关注差异最大的项；强调色指出重点。",
        "pitfalls": [
            "与学术柱状图同理，纵轴要从 0 起",
            "别用 3D 柱",
            "项目顺序按值排能更快读",
        ],
        "engine": None,
        "requires": None,
    },
    {
        "id": "flow",
        "name": "流程图",
        "name_en": "Flow",
        "category": "流程",
        "category_en": "Flow",
        "kind": "infographic",
        "summary": "节点 + 箭头表达步骤与分支",
        "definition": "节点 + 箭头表达步骤、顺序、分支。",
        "purpose": "讲清一个流程 / 方法 / 决策路径，回答「先做什么、然后什么、怎么分支」。",
        "data": "有序的步骤节点列表 + 方向。",
        "read": "从上到下 / 左到右读；菱形 = 决策分支；箭头 = 顺序。",
        "pitfalls": [
            "步骤太多要分组 / 分层",
            "分支条件写清楚",
            "不要双向箭头让读者不知道方向",
        ],
        "engine": None,
        "requires": None,
    },
    {
        "id": "dashboard",
        "name": "仪表盘",
        "name_en": "Dashboard",
        "category": "概览",
        "category_en": "Overview",
        "kind": "infographic",
        "summary": "多模块组合成一张总览",
        "definition": "多个小图 / 卡片组合成一张总览，通常信息图风格。",
        "purpose": "一页呈现多维度概览，用于汇报 / 项目总览，回答「整体情况如何」。",
        "data": "多个小模块（卡片 + 柱 + 流程的组合）。",
        "read": "先看标题和最大的数字，再扫各模块；布局按阅读优先级排。",
        "pitfalls": [
            "别塞太多模块导致信息过载",
            "每个模块要有清晰标题",
            "配色统一",
        ],
        "engine": None,
        "requires": None,
    },
]

_CATEGORY_ORDER = ["比较", "趋势", "相关", "分布", "流程", "概览"]


def build_gallery() -> dict[str, Any]:
    """返回图库：按 category 聚合的示例板列表。"""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in GALLERY:
        groups.setdefault(item["category"], []).append(item)
    categories = [
        {
            "name": category,
            "name_en": next((i["category_en"] for i in GALLERY if i["category"] == category), category),
            "items": groups.get(category, []),
        }
        for category in _CATEGORY_ORDER
        if category in groups
    ]
    return {"ok": True, "categories": categories, "total": len(GALLERY)}


# ------------------------------------------------------------- 选图判读 --

# 研究问题（我想看什么）→ 判读意图。面板传固定 key，也兜底自由文本关键词。
_INTENTS: dict[str, dict[str, Any]] = {
    "compare": {"keywords": ["比较", "对比", "组间", "差异", "compare", "group", "difference", "哪个", "高低", "多少"]},
    "trend": {"keywords": ["趋势", "变化", "随时间", "时间", "增长", "下降", "trend", "change", "time", "over time"]},
    "distribution": {"keywords": ["分布", "离散", "集中", "偏态", "分布形状", "distribution", "spread", "shape"]},
    "correlation": {"keywords": ["相关", "关系", "关联", "影响", "correlation", "relationship", "association"]},
    "composition": {"keywords": ["占比", "构成", "比例", "组成", "百分比", "proportion", "share", "composition"]},
    "overview": {"keywords": ["概览", "整体", "总览", "情况", "overview", "summary", "一览"]},
}

_ACADEMIC = {i["id"]: i for i in GALLERY if i["kind"] == "academic"}


def _detect_intent(question: str) -> str:
    q = (question or "").strip().lower()
    if q in _INTENTS:
        return q
    for intent, meta in _INTENTS.items():
        for keyword in meta["keywords"]:
            if keyword in q:
                return intent
    return "overview"


def _pick_group(profile: dict[str, Any]) -> str | None:
    """选一个最适合做分组的类别列。

    优先 3~8 个水平的列（更可能是实验分组 / 处理因素），其次二值列（常是
    人口学变量如性别 / 是否），再退化为水平最少的列。"""
    columns = profile.get("columns") or []
    cats = [c for c in columns if c.get("kind") == "categorical"]
    if not cats:
        return None
    moderate = [c for c in cats if 3 <= (c.get("unique") or 0) <= 8]
    if moderate:
        moderate.sort(key=lambda c: (c.get("unique") or 0))
        return moderate[0]["name"]
    binary = [c for c in cats if (c.get("unique") or 0) == 2]
    if binary:
        return binary[0]["name"]
    cats.sort(key=lambda c: (c.get("unique") or 0))
    return cats[0]["name"]


def _numeric_dvs(profile: dict[str, Any], limit: int = 2) -> list[str]:
    numeric = profile.get("numeric_columns") or []
    if not numeric:
        return []
    return numeric[:limit]


def _date_cols(profile: dict[str, Any]) -> list[str]:
    columns = profile.get("columns") or []
    return [c["name"] for c in columns if c.get("looks_like_date")]


def _level_note(profile: dict[str, Any], column: str) -> str:
    columns = profile.get("columns") or []
    for c in columns:
        if c.get("name") == column:
            unique = c.get("unique")
            if unique is not None:
                return f"{column}（{unique} 个水平）"
            return column
    return column


def recommend(profile: dict[str, Any], question: str) -> dict[str, Any]:
    """据数据画像 + 一句研究问题，返回带理由和具体 spec 的推荐列表。

    profile 即 build_profile 的输出（数据集记录里的 .profile）。question 是用户
    想看的意图（compare/trend/distribution/correlation/composition/overview，
    或一句自然语言）。每条推荐含可直接交给 /figure 的 spec 与中文理由。
    """
    if not profile or not isinstance(profile, dict):
        return {"ok": False, "error": {"code": "bad-profile", "message": "缺数据画像", "hint": "先 lab_ingest 登记数据"}}

    numeric = profile.get("numeric_columns") or []
    categorical = profile.get("categorical_columns") or []
    columns = profile.get("columns") or []
    by_name = {c.get("name"): c for c in columns}
    date_cols = _date_cols(profile)
    rows = (profile.get("shape") or {}).get("rows")

    intent = _detect_intent(question)
    recommendations: list[dict[str, Any]] = []

    def push(chart_id: str, spec: dict[str, Any], reason: str, confidence: float) -> None:
        meta = _ACADEMIC.get(chart_id, {})
        recommendations.append(
            {
                "chart_id": chart_id,
                "name": meta.get("name", chart_id),
                "name_en": meta.get("name_en", chart_id),
                "kind": meta.get("kind", "academic"),
                "reason": reason,
                "spec": spec,
                "confidence": round(confidence, 2),
            }
        )

    if intent == "compare":
        group = _pick_group(profile)
        dvs = _numeric_dvs(profile)
        if group and dvs:
            for dv in dvs:
                push(
                    "box",
                    {"chart": "box", "x": group, "y": dv, "journal": "nature", "error": "ci95"},
                    f"用「{group}」分组（{_level_note(profile, group)}）比较「{dv}」的分布与离群点，箱线图最适合看组间中位数差异。",
                    0.95,
                )
                push(
                    "violin",
                    {"chart": "violin", "x": group, "y": dv, "journal": "nature"},
                    f"「{dv}」在「{group}」各组上的分布形状，小提琴图能看出偏态 / 多峰，比箱线图多一层信息。",
                    0.9,
                )
            push(
                "bar",
                {"chart": "bar", "x": group, "y": dvs[0], "journal": "nature", "error": "ci95"},
                f"若只关心各组「{dvs[0]}」的均值差异，柱状图 + 误差棒更直接（注意纵轴从 0 起）。",
                0.85,
            )
        elif dvs and not group:
            push(
                "hist",
                {"chart": "hist", "x": dvs[0], "journal": "nature"},
                f"数据里没有可用的分组列，只能先看「{dvs[0]}」的整体分布；要组间比较请先补一个分组变量。",
                0.5,
            )
        else:
            recommendations.append(
                {"chart_id": None, "name": None, "kind": None,
                 "reason": "要比较组间差异，需要一个类别列（分组）+ 一个数值列（指标），但当前数据两类都不满足，先补充变量。",
                 "spec": None, "confidence": 0}
            )

    elif intent == "trend":
        x_candidates = date_cols or [c for c in columns if c.get("looks_like_date")]
        dvs = _numeric_dvs(profile)
        # 时间列优先；没有时间列就退化为「按类别 / 有序变量」。
        x = date_cols[0] if date_cols else None
        if x and dvs:
            group = _pick_group(profile)
            spec = {"chart": "line", "x": x, "y": dvs[0], "journal": "nature"}
            reason = f"「{x}」是日期 / 时间列，用折线图看「{dvs[0]}」随时间的趋势与拐点。"
            if group:
                spec["group"] = group
                reason += f" 可再按「{group}」分组画多条线比较斜率。"
            push("line", spec, reason, 0.95)
        elif categorical and dvs:
            cat = _pick_group(profile)
            push(
                "line",
                {"chart": "line", "x": cat, "y": dvs[0], "journal": "nature"},
                f"没有时间列，用有序 / 类别列「{cat}」作横轴近似看「{dvs[0]}」的走向；注意折线只在 x 有序时才成立。",
                0.5,
            )
        elif dvs:
            push("hist", {"chart": "hist", "x": dvs[0], "journal": "nature"},
                 f"没有时间或有序变量，只能先看「{dvs[0]}」的分布；要画趋势请补一个时间 / 剂量 / 年龄列。", 0.4)
        else:
            recommendations.append({"chart_id": None, "name": None, "kind": None,
                                    "reason": "要画趋势需要一个数值指标列，当前数据没有，先补充变量。", "spec": None, "confidence": 0})

    elif intent == "distribution":
        dvs = _numeric_dvs(profile)
        group = _pick_group(profile)
        for dv in dvs:
            if group:
                push("violin", {"chart": "violin", "x": group, "y": dv, "journal": "nature"},
                     f"看「{dv}」在各组（{_level_note(profile, group)}）的分布形状，小提琴图能识别偏态与多峰。", 0.9)
            else:
                push("hist", {"chart": "hist", "x": dv, "journal": "nature"},
                     f"看「{dv}」的整体分布形状（正态 / 偏态 / 多峰），直方图最直接。", 0.95)
        if not dvs:
            recommendations.append({"chart_id": None, "name": None, "kind": None,
                                    "reason": "要看分布需要一个数值列，当前数据没有。", "spec": None, "confidence": 0})

    elif intent == "correlation":
        if len(numeric) >= 3:
            push("heatmap", {"chart": "heatmap", "columns": numeric[:6], "journal": "nature"},
                 f"{len(numeric)} 个数值列，热力图一次看清它们两两相关，找「深色块」= 高度相关的变量团。", 0.95)
        if len(numeric) >= 2:
            push("scatter", {"chart": "scatter", "x": numeric[0], "y": numeric[1], "journal": "nature"},
                 f"先看最前两个数值列「{numeric[0]}」vs「{numeric[1]}」的关系；相关矩阵里的强相关对可以逐对画散点验证。", 0.9)
        if len(numeric) < 2:
            recommendations.append({"chart_id": None, "name": None, "kind": None,
                                    "reason": "要看两变量关系至少需要两个数值列，当前只有一个，先补充变量。", "spec": None, "confidence": 0})

    elif intent == "composition":
        group = _pick_group(profile)
        dvs = _numeric_dvs(profile)
        if group:
            push("bar", {"chart": "bar", "x": group, "y": dvs[0] if dvs else None, "journal": "nature", "error": "none"},
                 f"用「{group}」的分组计数 / 汇总看构成占比；柱状图按类别呈现各部分大小（纵轴从 0 起）。", 0.8)
        else:
            recommendations.append({"chart_id": None, "name": None, "kind": None,
                                    "reason": "要看构成占比需要一个类别列，当前数据没有。", "spec": None, "confidence": 0})

    else:  # overview
        dvs = _numeric_dvs(profile)
        group = _pick_group(profile)
        if group and dvs:
            push("box", {"chart": "box", "x": group, "y": dvs[0], "journal": "nature", "error": "ci95"},
                 f"概览先看核心指标「{dvs[0]}」在「{group}」各组上的分布。", 0.85)
        if dvs:
            push("hist", {"chart": "hist", "x": dvs[0], "journal": "nature"}, f"再看「{dvs[0]}」的整体分布。", 0.8)
        if len(numeric) >= 3:
            push("heatmap", {"chart": "heatmap", "columns": numeric[:6], "journal": "nature"},
                 f"数值列较多，热力图给出变量之间的相关性总览。", 0.75)
        if not recommendations:
            recommendations.append({"chart_id": None, "name": None, "kind": None,
                                    "reason": "数据里没有可绘制的数值列，先补充指标变量。", "spec": None, "confidence": 0})

    return {
        "ok": True,
        "intent": intent,
        "rows": rows,
        "numeric_columns": numeric,
        "categorical_columns": categorical,
        "date_columns": date_cols,
        "recommendations": recommendations,
    }
