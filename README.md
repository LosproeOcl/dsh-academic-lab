# DSH 学术数据工作台（dsh-academic-lab）

把「数据 → 审计 → 统计推断 → 出版级图 → 可复现台账」做成一个 DSH 工作台。
Agent 通过 `lab_*` 工具调用本机 Python 科学栈完成计算；面板只读展示数据集、图表和运行记录，
不重复造第二套算法，避免会话里报一个数、面板里显示另一个数。

## 它解决什么问题

通用对话里做数据分析，最容易出的三类错是：

1. **只报 p 值，不报效应量和不确定区间。** 这里每条推断都返回效应量 + 95% CI，
   多终点默认 Holm 校正，并给出所用检验的前提检查（正态性、方差齐性、期望频数）。
2. **数字无法回溯。** 每次分析记录数据文件 sha256、完整参数、Python 与包版本、时间戳；
   `lab_runs` / `lab_run` 可以逐条还原。
3. **图不是给论文用的。** 出图按期刊栏宽（Nature/Science/IEEE/APS/PLOS）与字号出
   PDF 矢量 + SVG + 300 dpi PNG，配色用 Okabe-Ito 色盲安全色，图注草稿自动带 n 与数据指纹。

## 环境要求

- DSH Desktop（桌面版），插件安装进当前 Profile。
- 本机 Python 3.10+，需要：`numpy pandas scipy statsmodels matplotlib openpyxl`（Parquet 另需 pyarrow）。
  推荐 3.12+。

```bash
python3 -m pip install numpy pandas scipy statsmodels matplotlib openpyxl
```

插件会依次尝试 `config.python` → `$DSH_LAB_PYTHON` → `/opt/homebrew/bin/python3` →
`/usr/local/bin/python3` → `/usr/bin/python3` → `python3`，用一次 `import` 探测挑选真正带科学栈的解释器。
DSH 自带的 Office Python 不含 scipy/statsmodels，不会被选中。

## 工具

| 工具 | 作用 |
| --- | --- |
| `lab_datasets` | 列出已登记数据集 |
| `lab_ingest` | 登记数据文件并立刻审计（行列、缺失、分布、重复、常量列、强相关） |
| `lab_profile` | 重新审计（数据变动后），或审计未登记的路径 |
| `lab_stats` | `describe` / `compare` / `associate` / `regress` / `chisq` |
| `lab_figure` | `bar` / `line` / `scatter` / `box` / `violin` / `raincloud` / `hist` / `heatmap`（可选 `copyTo` 复制到工作区） |
| `lab_runs` | 最近运行台账 |
| `lab_run` | 单次运行的完整记录（参数、指纹、产物路径） |

`compare` 的 `method=auto`：两组按正态性 + 样本量选 Welch t 或 Mann-Whitney；多组按正态性 +
Levene 选单因素 ANOVA 或 Kruskal-Wallis。`regress` 默认 HC3 稳健标准误，附 VIF、
Breusch-Pagan、Durbin-Watson 与标准化系数。

## 数据与产物位置

- 数据目录：`<DSH 数据目录>/academic-lab/`
  - `datasets/<id>.json` 数据集索引与审计快照
  - `runs/<runId>.json` 运行台账
  - `figures/<runId>/` 正式产物（PDF/SVG/PNG）
  - `cache/matplotlib/` 字体缓存
- 工作区副本：出图时把 `copyTo` 指向会话工作区的 `figures/` 即可同时复制一份，
  方便在对话里直接打开；不传就只保留数据目录里的正式产物。

**原始数据只读**：插件从不改写用户的数据文件，只计算 sha256 与读取。

## 自检

```bash
node scripts/verify.mjs        # 静态检查 + 审计/统计/出图端到端
node scripts/check-package.mjs # 打包清单检查
```

`verify.mjs` 会在 `examples/out/` 生成临时图，跑完自动清理。

## 边界

- 这是统计工具，不是因果推断机器。观察性数据的相关、回归系数不构成因果结论，
  面板和工具输出里会保留这句话。
- 前提检查不通过时给警告而不是硬拦；是否换检验由分析者决定，决定与理由应当写进报告。
- 出图只覆盖常见单图类型；复合图（多面板 a/b/c）需要在生成后用矢量工具拼版。
- 中文字体优先 PingFang SC / Hiragino Sans GB，其次 Noto Sans CJK / 文泉驿；
  都没有时工具会明确提示「中文会显示成方框」，而不是静默出一张坏图。

## 许可

MIT。

## 示例产物

`examples/out/` 里是用 `examples/trial.csv` 跑出来的四张图（Nature/Science/IEEE 栏宽）：
柱状（均值 + 95% CI）、箱线、带线性拟合与 CI 带的散点、相关矩阵热图。
它们由 `py/lab_runner.py` 直接生成，可用来核对字体、字号与图注格式是否符合目标期刊。
