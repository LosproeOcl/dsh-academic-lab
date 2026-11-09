# DSH 学术数据工作台 · 架构设计

> 版本 0.2 · 状态：待确认。与 [requirements.md](./requirements.md) 配套；决策 D1–D3 确认后冻结。

## 1. 分层

```
┌────────────────────────────────────────────────────────────┐
│ 客户端面板  lib/client.js（单文件构建产物）                  │
│  导航：数据 / 审计 / 统计 / 出图 / 台账（+ 会话抽屉）          │
│  职责：表单参数装配、结果展示、下载；不做任何计算             │
└───────────────┬────────────────────────────────────────────┘
                │ HTTP JSON  /api/dsh-academic-lab/*
┌───────────────▼────────────────────────────────────────────┐
│ 宿主插件  dsh/index.js（运行在 Harness 内）                  │
│  路由：GET state / GET file / POST ingest|audit|stats|figure │
│  职责：路径收敛、大小限制、spawn 引擎、写台账、错误规范化      │
│  工具：lab_*（供 Agent）→ 与路由共用同一引擎调用             │
└───────────────┬────────────────────────────────────────────┘
                │ spawn python3 lab_runner.py <payload.json>
┌───────────────▼────────────────────────────────────────────┐
│ Python 引擎  py/（系统解释器，numpy/scipy/statsmodels/…）    │
│  lab_common / lab_profile / lab_stats / lab_figure / runner │
│  单 JSON 进出；失败返回结构化 error 且非零退出               │
└───────────────┬────────────────────────────────────────────┘
                │ 读写（数据只读 / 产物写）
┌───────────────▼────────────────────────────────────────────┐
│ 数据目录  ~/…/harness/academic-lab/                         │
│  datasets/（登记+指纹） runs/（台账+参数+产物）              │
│  figures/<runId>/  cache/                                   │
└────────────────────────────────────────────────────────────┘
```

## 2. 组件职责

- **客户端面板**：唯一交互入口。表单 + 列表 + 预览 + 下载。所有"动作"都 POST 到宿主，自己绝不 spawn python、绝不写文件。
- **宿主插件**：唯一有权做路径收敛、大小限制、进程调用的层。路由（面板用）和工具（Agent 用）都落到同一个 `runEngine()`，保证一致性。
- **Python 引擎**：纯函数式、无状态、单 JSON 进出。面板与 Agent 共享。
- **数据目录**：持久化登记、台账、产物。是"真相源"，面板与工具都从这里读。

## 3. 交互模型

核心原则：**面板是控制面，引擎是执行面，两条路径收敛到同一引擎**。

```
面板表单 ──POST──▶ 宿主 runEngine() ──spawn──▶ lab_runner.py ──▶ 写台账/产物
Agent 工具 ──execute──▶ 宿主 runEngine() ──spawn──▶ lab_runner.py ──▶ 写台账/产物
```

- 面板路径：参数由表单显式给出。
- Agent 路径：参数由模型从自然语言提取。
- 两条路径产生**同一结构**的运行记录（`runs/<id>/record.json`），台账/复现完全一致。

## 4. 数据模型

```
datasets/<id>/
  meta.json          # { id, name, path, sha256, rows, columns, fingerprint }
  profile.json       # 审计结果（结构化，可被面板直接渲染）

runs/<id>/
  record.json        # { id, datasetId, kind, spec, startedAt, python{version,packages},
                     #   headline, files[], inputFingerprint }
  result.json        # 统计/出图的结构化结果（效应量、CI、p、caption…）

figures/<runId>/     # figure 类型运行的 pdf/svg/png
```

`lab_runner.py` 输出一次性的结果 JSON；宿主把它拆成 `record.json`（台账）与 `result.json`（渲染用），并落地产物路径。

## 5. 路由契约（新增动作）

现有：`GET /state`（聚合数据集/运行/产物）、`GET /file?path=`（产物预览）。

新增（全部 POST，body 为 JSON，均先做路径收敛 + 大小限制）：

| 路由 | body | 返回 |
| --- | --- | --- |
| `POST /ingest` | `{ path }` | `{ ok, datasetId, profile }` |
| `POST /audit` | `{ path }` 或 `{ datasetId }` | `{ ok, profile }` |
| `POST /stats` | `{ path, spec }` | `{ ok, runId, result }` |
| `POST /figure` | `{ path, spec, copyTo? }` | `{ ok, runId, result, files }` |
| `GET /candidates` | —（枚举数据目录+工作区数据文件） | `{ ok, files:[{path,name,bytes}] }` |

安全不变式（沿用现有测试）：
- `path` 必须落在工作区或数据目录内；拒绝绝对路径、`..`、符号链接逃逸。
- 读取类只读；`copyTo` 目标必须落在工作区 `figures/` 内。
- 产物文件名由 `runId` 派生，不接受用户命名路径拼接。

## 6. UI/UX 结构（customFrame 整页）

```
┌ header：AL · DSH 学术数据工作台 · [Python 状态] · [数据集数] [运行数] · [AI 协助] [刷新] ┐
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ tab 导航：数据 / 统计 / 出图 / 台账                                                        │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ [数据] 数据集卡片列表 → 点击进入：审计详情（逐列 + 整表预警）+ 「去统计」「去出图」          │
│ [统计] 左：分析类型+参数表单　右：结果卡（效应量/CI/p/前提/warnings）+「复制参数到会话」      │
│ [出图] 左：图表+变量+期刊+误差棒表单　右：预览图 + 图注 + 下载 PDF/SVG/PNG                 │
│ [台账] 运行历史表 + 筛选 + 单击回看完整参数与产物                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
[会话抽屉] 点「AI 协助」出现，宿主原生会话，380px，可收起
```

响应式：窄容器下列/表重排，长标题缩略，不整页横向溢出。审计结果分页，不一次渲染百万行。

## 7. 分期计划（决策确认后执行，每期单独验收）

- **P0 数据入口 + 审计**：`GET /candidates` + `POST /ingest` + `POST /audit`；数据卡片列表 + 审计详情页。
- **P1 统计表单**：`POST /stats` + 结果卡渲染。
- **P2 出图表单**：`POST /figure` + 预览/下载。
- **P3 台账增强**：筛选、单次回看、复现说明。
- 每期：改代码 → `node scripts/verify.mjs` + 面板桩自检 → 打包 → `install_local_workbench` → 请用户核验界面。

## 8. 待确认（对应 requirements.md §10）

- D1、D2、D3 的取舍会改变 §5 路由与 §6 UI 的细节，但分层与"单一引擎 + 单一台账"不变。
