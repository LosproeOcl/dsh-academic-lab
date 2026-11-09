/**
 * DSH 学术数据工作台 · 客户端面板。
 *
 * 只读视图：数据集审计、图表产物、运行台账。分析本身由会话里的 Agent 通过
 * lab_* 工具驱动——面板不重复造一套表单，避免两条路径算出不一样的数。
 *
 * 加载协议：window.__ModuleLoader__.load({ id, factory })，与仓库内其他插件一致。
 */
window.__ModuleLoader__.load({
  id: 'dsh-academic-lab',
  factory: (require) => {
    const React = require('react')
    const h = React.createElement

    const NS = 'dsh-academic-lab'
    const API = '/api/dsh-academic-lab'

    // ---------------------------------------------------------------- 样式 --

    const css = `
.dshAl{position:relative;display:flex;flex-direction:column;flex:1 1 auto;width:100%;height:100%;min-width:0;min-height:0;box-sizing:border-box;background:var(--dsw-alias-bg-layer-1);color:var(--dsw-alias-label-primary);font-size:13px}
.dshAlHeader{display:flex;align-items:center;gap:10px;flex:0 0 auto;min-height:48px;padding:8px 14px;border-bottom:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-module-platform)}
.dshAlMark{display:grid;place-items:center;width:24px;height:24px;border-radius:7px;background:var(--dsw-alias-state-business-primary);color:#fff;font-size:11px;font-weight:700;letter-spacing:.02em}
.dshAlTitle{font-size:14px;font-weight:600;line-height:22px;white-space:nowrap}
.dshAlMeta{display:flex;align-items:center;gap:10px;min-width:0;overflow:hidden;color:var(--dsw-alias-label-tertiary);font-size:12px;white-space:nowrap;text-overflow:ellipsis}
.dshAlSpacer{flex:1 1 auto}
.dshAlDot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;background:var(--dsw-alias-label-caption,var(--dsw-alias-label-tertiary))}
.dshAlDot[data-state=ok]{background:var(--dsw-alias-state-business-primary)}
.dshAlDot[data-state=bad]{background:var(--dsw-alias-state-error-primary)}
.dshAlBtn{display:inline-flex;align-items:center;gap:5px;padding:5px 11px;font:inherit;font-size:12px;line-height:20px;white-space:nowrap;cursor:pointer;color:var(--dsw-alias-label-primary);background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md)}
.dshAlBtn:hover:not(:disabled){background:var(--dsw-alias-interactive-bg-hover)}
.dshAlBtn:disabled{opacity:.5;cursor:default}
.dshAlBody{flex:1 1 auto;min-height:0;overflow-y:auto;padding:14px}
.dshAlSection{margin-bottom:20px}
.dshAlSectionTitle{display:flex;align-items:baseline;gap:8px;margin:0 0 10px;font-size:13px;font-weight:600}
.dshAlSectionTitle small{font-weight:400;color:var(--dsw-alias-label-tertiary);font-size:12px}
.dshAlGrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.dshAlCard{border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-lg,10px);background:var(--dsw-alias-bg-layer-1);padding:12px;min-width:0}
.dshAlCardHead{display:flex;align-items:baseline;gap:8px;min-width:0}
.dshAlCardName{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dshAlCardId{flex:0 0 auto;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:var(--dsw-alias-label-tertiary)}
.dshAlCardMeta{margin-top:6px;color:var(--dsw-alias-label-secondary);font-size:12px;line-height:19px}
.dshAlWarn{margin-top:8px;padding:7px 9px;border-radius:8px;font-size:12px;line-height:18px;background:color-mix(in srgb,var(--dsw-alias-state-warning-primary,#c98a00) 12%,transparent);color:var(--dsw-alias-label-primary)}
.dshAlTable{width:100%;border-collapse:collapse;font-size:12px}
.dshAlTable th{text-align:left;font-weight:500;color:var(--dsw-alias-label-tertiary);padding:6px 8px;border-bottom:1px solid var(--dsw-alias-border-l2);white-space:nowrap}
.dshAlTable td{padding:6px 8px;border-bottom:1px solid var(--dsw-alias-border-l1,#00000010);vertical-align:top}
.dshAlTable tr:last-child td{border-bottom:0}
.dshAlMono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:var(--dsw-alias-label-secondary)}
.dshAlFig{margin:0;border:1px solid var(--dsw-alias-border-l2);border-radius:10px;overflow:hidden;background:#fff}
.dshAlFig img{display:block;width:100%;height:auto}
.dshAlFig figcaption{padding:7px 9px;font-size:12px;line-height:18px;color:var(--dsw-alias-label-secondary)}
.dshAlFigPreview{display:block;max-width:100%;height:auto;margin:10px 0;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;background:#fff}
.dshAlFigFrame{display:block;width:100%;height:520px;margin:10px 0;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;background:#fff}
.dshAlBtnOn{background:color-mix(in srgb,var(--dsw-alias-brand-primary) 18%,transparent);border-color:var(--dsw-alias-brand-primary);color:var(--dsw-alias-brand-primary)}
.dshAlEmpty{padding:36px 20px;border:1px dashed var(--dsw-alias-border-l2);border-radius:12px;text-align:center;color:var(--dsw-alias-label-secondary);line-height:1.9}
.dshAlEmpty strong{color:var(--dsw-alias-label-primary)}
.dshAlErr{padding:10px 12px;border-radius:10px;background:color-mix(in srgb,var(--dsw-alias-state-error-primary) 12%,transparent);color:var(--dsw-alias-label-primary);font-size:12px;line-height:19px;white-space:pre-wrap}
.dshAlRoot{display:flex;flex:1 1 auto;width:100%;height:100%;min-width:0;min-height:0;overflow:hidden}
.dshAlMain{display:flex;flex-direction:column;flex:1 1 auto;min-width:0;min-height:0}
.dshAlChat{display:flex;flex-direction:column;flex:0 0 380px;width:380px;min-width:300px;max-width:46%;min-height:0;border-left:1px solid var(--dsw-alias-border-l2);background:var(--dsw-alias-bg-layer-1)}
.dshAlChatHead{display:flex;align-items:center;gap:8px;flex:0 0 auto;min-height:48px;padding:8px 12px;border-bottom:1px solid var(--dsw-alias-border-l2);font-size:12px;color:var(--dsw-alias-label-secondary)}
.dshAlChatBody{position:relative;flex:1 1 auto;min-height:0;overflow:hidden}
.dshAlChatSlot{position:relative;z-index:1;height:100%;min-height:0;background:var(--dsw-alias-bg-layer-1)}
.dshAlChatHint{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:24px;text-align:center;font-size:12px;line-height:20px;color:var(--dsw-alias-label-secondary);background:var(--dsw-alias-bg-layer-1)}
.dshAlKbd{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;padding:1px 5px;border-radius:5px;background:var(--dsw-alias-bg-module-platform);border:1px solid var(--dsw-alias-border-l2)}
.dshAlField{display:flex;gap:8px;align-items:center;margin-bottom:10px}
.dshAlInput{flex:1 1 auto;min-width:0;font:inherit;font-size:12px;line-height:20px;padding:6px 10px;color:var(--dsw-alias-label-primary);background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md)}
.dshAlInput:focus{outline:none;border-color:var(--dsw-alias-state-business-primary)}
.dshAlList{margin:0;padding:0;list-style:none}
.dshAlListItem{display:flex;align-items:center;gap:8px;padding:6px 9px;border:1px solid var(--dsw-alias-border-l2);border-radius:8px;margin-bottom:6px;min-width:0}
.dshAlListItem .dshAlCardName{flex:1 1 auto;min-width:0}
.dshAlHint{color:var(--dsw-alias-label-tertiary);font-size:12px;line-height:18px;word-break:break-all}
.dshAlMsg{margin-top:8px;padding:7px 9px;border-radius:8px;font-size:12px;line-height:18px;white-space:pre-wrap}
.dshAlMsg[data-ok="true"]{background:color-mix(in srgb,var(--dsw-alias-state-business-primary) 12%,transparent)}
.dshAlMsg[data-ok="false"]{background:color-mix(in srgb,var(--dsw-alias-state-error-primary) 12%,transparent)}
.dshAlChip{display:inline-block;margin:2px 4px 0 0;padding:1px 7px;border-radius:999px;font-size:11px;color:var(--dsw-alias-label-secondary);background:var(--dsw-alias-bg-module-platform)}
.dshAlSel{min-width:0;font:inherit;font-size:12px;line-height:20px;padding:6px 8px;color:var(--dsw-alias-label-primary);background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l2);border-radius:var(--dsw-radius-md)}
.dshAlSel:focus{outline:none;border-color:var(--dsw-alias-state-business-primary)}
.dshAlFieldRow{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:10px}
.dshAlFieldCol{display:flex;flex-direction:column;gap:4px;min-width:150px}
.dshAlFieldCol>span{font-size:11px;color:var(--dsw-alias-label-tertiary)}
.dshAlChipRow{display:flex;flex-wrap:wrap;gap:6px}
.dshAlChipBtn{font:inherit;font-size:11px;line-height:20px;padding:2px 9px;border-radius:999px;cursor:pointer;color:var(--dsw-alias-label-secondary);background:var(--dsw-alias-bg-layer-1);border:1px solid var(--dsw-alias-border-l2)}
.dshAlChipBtn[data-on="true"]{color:#fff;background:var(--dsw-alias-state-business-primary);border-color:var(--dsw-alias-state-business-primary)}
.dshAlChipBtn:disabled{opacity:.5;cursor:default}
.dshAlResult{margin-top:10px;padding:11px 12px;border:1px solid var(--dsw-alias-border-l2);border-radius:10px;background:var(--dsw-alias-bg-layer-1)}
.dshAlResultHead{display:flex;align-items:baseline;gap:8px;margin-bottom:6px}
.dshAlResultHead .dshAlCardName{flex:1 1 auto}
.dshAlResultLine{margin:0 0 4px;font-size:12px;line-height:19px}
.dshAlResultLine[data-strong="true"]{font-weight:600}
.dshAlGroupTitle{display:flex;align-items:baseline;gap:6px;margin:0 0 8px;font-size:13px;font-weight:600}
.dshAlGroupTitle small{font-weight:400;color:var(--dsw-alias-label-tertiary);font-size:12px}
`

    function installStyles() {
      const existing = document.querySelector('style[data-plugin-css="dsh-academic-lab"]')
      if (existing) return
      const style = document.createElement('style')
      style.dataset.plugin = 'dsh-academic-lab'
      style.dataset.pluginCss = 'dsh-academic-lab'
      style.textContent = css
      document.head.appendChild(style)
    }

    // ---------------------------------------------------------------- 文案 --

    const dict = {
      zh: {
        panelTitle: 'DSH 学术数据工作台',
        description: '数据审计、统计推断与出版级出图；每次分析留指纹与运行台账，结果可复现。',
        pythonOk: 'Python 就绪',
        pythonBad: 'Python 不可用',
        refresh: '刷新',
        datasets: '数据集',
        figures: '图表',
        runs: '运行台账',
        noData: '还没有登记数据。',
        noDataHint: '把 CSV / XLSX 放进工作区，然后让 Agent 做一次数据审计；登记后会出现在这里。',
        emptyFigures: '还没有出图。让 Agent 用 lab_figure 生成 PDF/SVG/PNG。',
        emptyRuns: '还没有运行记录。',
        cols: '列',
        rows: '行',
        missing: '缺失',
        warning: '需要先处理',
        refreshHint: '面板每 12 秒自动同步一次，可随时手动刷新。',
        chatOpen: 'AI 协助',
        chatClose: '收起对话',
        chatTitle: 'AI 协助',
        chatStarting: '正在准备会话…',
        chatHint: '还没有绑定到本工作台的会话。点上面的「AI 协助」会创建或恢复一条。',
        chatFailed: '无法打开会话',
        loadFailed: '读取工作台状态失败',
        ingestTitle: '登记数据',
        ingestPlaceholder: '粘贴数据文件绝对路径，例如 /Volumes/DATA/…/data.csv',
        ingestBtn: '登记并审计',
        ingestBusy: '审计中…',
        inboxTitle: '投放箱',
        inboxHint: '把 CSV / XLSX 放进投放箱，点文件名即可登记。',
        inboxPath: '投放箱目录',
        inboxEmpty: '投放箱里还没有数据文件。',
        ingestOk: '已登记',
        ingestCached: '已登记（复用）',
        reaudit: '重新审计',
        reauditing: '审计中…',
        candidatesFailed: '读取投放箱失败',
        statsTitle: '统计分析',
        statsHint: '参数直接交给统计引擎，与会话里的 lab_stats 同源，不重复算。',
        statsDataset: '数据集',
        statsAnalysis: '分析',
        statsRun: '运行分析',
        statsRunning: '计算中…',
        analysisDescribe: '描述统计 (describe)',
        analysisCompare: '组间比较 (compare)',
        analysisAssociate: '相关性 (associate)',
        analysisRegress: '回归 (regress)',
        analysisChisq: '卡方检验 (chisq)',
        statsDv: '因变量（数值，可多选）',
        statsGroup: '分组（类别）',
        statsX: 'X 变量',
        statsY: 'Y 变量',
        statsPredictors: '预测变量（数值，可多选）',
        statsColumns: '列（留空 = 全部数值列）',
        statsMethod: '方法',
        statsCorrection: '多重校正',
        statsRobust: 'HC3 稳健标准误',
        statsResult: '结果',
        noNumericCols: '该数据集没有数值列',
        noCatCols: '该数据集没有类别列',
        pickDataset: '先登记一个数据集',
        figureTitle: '出版级出图',
        figureHint: 'PDF 矢量 + SVG + 300 dpi PNG，按期刊版式；与 Agent 的 lab_figure 同源。',
        figureChart: '图表',
        figureX: 'X 变量',
        figureY: 'Y 变量（数值）',
        figureGroup: '分组（可选）',
        figureColumns: '列（heatmap，逗号分隔）',
        figureJournal: '期刊',
        figureError: '误差棒',
        figureTitleLabel: '标题',
        figureXLabelLabel: 'X 轴标签',
        figureYLabelLabel: 'Y 轴标签',
        figureRun: '出图',
        figureRunning: '渲染中…',
        figureResultTitle: '产物',
        figureFiles: '文件',
        figureInteractive: '交互',
        figureDescription: '饱和描述',
        figureCopyPrompt: '复制图注 prompt',
        figureCopied: '已复制',
        galleryTitle: '图库',
        galleryHint: '每种图一张示例板，点开看它是干什么的、要什么数据、怎么读。',
        galleryEmpty: '图库加载失败。',
        galleryDefinition: '是什么',
        galleryPurpose: '解决什么问题',
        galleryData: '需要什么数据',
        galleryRead: '怎么读',
        galleryPitfalls: '常见误用',
        galleryUse: '用这个图',
        galleryInfographic: '信息图 · 在会话里让 AI 生成',
        galleryCopyPrompt: '复制提示词模板',
        galleryCopied: '已复制',
        recommendTitle: '选图判读',
        recommendHint: '填一句「我想看什么」，引擎按数据画像推荐该画哪种图。',
        recommendDataset: '数据集',
        recommendPlaceholder: '例如：比较各组差异 / 看趋势 / 看分布 / 看两个变量的关系',
        recommendRun: '判读',
        recommendRunning: '判读中…',
        recommendResult: '推荐',
        recommendDraw: '画这张',
        recommendEmpty: '没有可推荐的图，换一句描述试试。',
        intentCompare: '比较组间差异',
        intentTrend: '看趋势',
        intentDistribution: '看分布',
        intentCorrelation: '看两变量关系',
        intentComposition: '看占比',
        intentOverview: '概览',
        sessionSetupBody: '这个工作台不需要绑定会话就能查看数据与图表；要让 Agent 做统计和出图，请在绑定到本工作台的对话里直接描述分析需求。'
      },
      en: {
        panelTitle: 'DSH Academic Data Lab',
        description: 'Data audit, statistical inference and publication figures, with a fingerprint on every run.',
        pythonOk: 'Python ready',
        pythonBad: 'Python unavailable',
        refresh: 'Refresh',
        datasets: 'Datasets',
        figures: 'Figures',
        runs: 'Run ledger',
        noData: 'No datasets yet.',
        noDataHint: 'Put a CSV/XLSX in the workspace and ask the agent to audit it; registered datasets appear here.',
        emptyFigures: 'No figures yet. Ask the agent to run lab_figure for PDF/SVG/PNG.',
        emptyRuns: 'No runs recorded yet.',
        cols: 'columns',
        rows: 'rows',
        missing: 'missing',
        warning: 'Needs attention',
        refreshHint: 'Auto-syncs every 12 seconds.',
        chatOpen: 'Ask AI',
        chatClose: 'Hide chat',
        chatTitle: 'AI assistance',
        chatStarting: 'Preparing the conversation…',
        chatHint: 'No conversation is bound to this workbench yet. Click “Ask AI” to create or restore one.',
        chatFailed: 'Could not open the conversation',
        loadFailed: 'Failed to load workbench state',
        ingestTitle: 'Register data',
        ingestPlaceholder: 'Paste an absolute path to a data file, e.g. /Volumes/DATA/…/data.csv',
        ingestBtn: 'Register & audit',
        ingestBusy: 'Auditing…',
        inboxTitle: 'Inbox',
        inboxHint: 'Drop CSV/XLSX into the inbox, then click a file name to register it.',
        inboxPath: 'Inbox folder',
        inboxEmpty: 'No data files in the inbox yet.',
        ingestOk: 'Registered',
        ingestCached: 'Registered (cached)',
        reaudit: 'Re-audit',
        reauditing: 'Auditing…',
        candidatesFailed: 'Failed to load the inbox',
        statsTitle: 'Statistics',
        statsHint: 'Parameters go straight to the stats engine — the same one behind lab_stats.',
        statsDataset: 'Dataset',
        statsAnalysis: 'Analysis',
        statsRun: 'Run',
        statsRunning: 'Computing…',
        analysisDescribe: 'Describe',
        analysisCompare: 'Compare groups',
        analysisAssociate: 'Correlation',
        analysisRegress: 'Regression',
        analysisChisq: 'Chi-square',
        statsDv: 'Outcome (numeric, multi)',
        statsGroup: 'Group (categorical)',
        statsX: 'X variable',
        statsY: 'Y variable',
        statsPredictors: 'Predictors (numeric, multi)',
        statsColumns: 'Columns (blank = all numeric)',
        statsMethod: 'Method',
        statsCorrection: 'Correction',
        statsRobust: 'HC3 robust SE',
        statsResult: 'Result',
        noNumericCols: 'No numeric columns',
        noCatCols: 'No categorical columns',
        pickDataset: 'Register a dataset first',
        figureTitle: 'Publication figure',
        figureHint: 'PDF vector + SVG + 300 dpi PNG at journal widths; same engine as lab_figure.',
        figureChart: 'Chart',
        figureX: 'X variable',
        figureY: 'Y variable (numeric)',
        figureGroup: 'Group (optional)',
        figureColumns: 'Columns (heatmap, comma-separated)',
        figureJournal: 'Journal',
        figureError: 'Error bars',
        figureTitleLabel: 'Title',
        figureXLabelLabel: 'X label',
        figureYLabelLabel: 'Y label',
        figureRun: 'Render',
        figureRunning: 'Rendering…',
        figureResultTitle: 'Output',
        figureFiles: 'Files',
        figureInteractive: 'Interactive',
        figureDescription: 'Description',
        figureCopyPrompt: 'Copy caption prompt',
        figureCopied: 'Copied',
        galleryTitle: 'Gallery',
        galleryHint: 'One card per chart — open it to see what it is for, what data it needs, how to read it.',
        galleryEmpty: 'Failed to load the gallery.',
        galleryDefinition: 'What it is',
        galleryPurpose: 'What it solves',
        galleryData: 'Data it needs',
        galleryRead: 'How to read',
        galleryPitfalls: 'Common pitfalls',
        galleryUse: 'Use this chart',
        galleryInfographic: 'Infographic · ask AI in the chat',
        galleryCopyPrompt: 'Copy prompt template',
        galleryCopied: 'Copied',
        recommendTitle: 'Pick a chart',
        recommendHint: 'Describe what you want to see; the engine recommends charts from the data profile.',
        recommendDataset: 'Dataset',
        recommendPlaceholder: 'e.g. compare groups / trend / distribution / relationship',
        recommendRun: 'Recommend',
        recommendRunning: 'Recommending…',
        recommendResult: 'Recommendations',
        recommendDraw: 'Draw this',
        recommendEmpty: 'Nothing to recommend — try another question.',
        intentCompare: 'Compare groups',
        intentTrend: 'Trend',
        intentDistribution: 'Distribution',
        intentCorrelation: 'Relationship',
        intentComposition: 'Composition',
        intentOverview: 'Overview',
        sessionSetupBody: 'Data and figures are readable without a bound conversation; to run statistics and render figures, talk to the agent in a conversation bound to this workbench.'
      }
    }

    /** ISO 时间转本地「MM-DD HH:mm」；台账存 UTC，直接切片会差 8 小时。 */
    function formatTime(value) {
      if (!value) return ''
      const date = new Date(value)
      if (Number.isNaN(date.getTime())) return String(value).slice(0, 16)
      const pad = (n) => String(n).padStart(2, '0')
      return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    }

    // ---------------------------------------------------------------- 面板 --

    function createPanel(t) {
      return function Panel(props) {
        const service = props?.service
        const conversation = props?.conversation
        const [chat, setChat] = React.useState(false)
        const [chatPending, setChatPending] = React.useState(false)
        const [chatError, setChatError] = React.useState(null)
        const [state, setState] = React.useState(null)
        const [error, setError] = React.useState(null)
        const [busy, setBusy] = React.useState(false)
        const [candidates, setCandidates] = React.useState(null)
        const [pathDraft, setPathDraft] = React.useState('')
        const [ingesting, setIngesting] = React.useState(false)
        const [ingestMsg, setIngestMsg] = React.useState(null)
        const [gallery, setGallery] = React.useState(null)
        const [galleryOpen, setGalleryOpen] = React.useState(null)
        const [recDataset, setRecDataset] = React.useState('')
        const [recQuestion, setRecQuestion] = React.useState('')
        const [recBusy, setRecBusy] = React.useState(false)
        const [recResult, setRecResult] = React.useState(null)
        const [recError, setRecError] = React.useState(null)
        const figureRef = React.useRef(null)
        const [figDataset, setFigDataset] = React.useState('')
        const [figChart, setFigChart] = React.useState('bar')
        const [figX, setFigX] = React.useState('')
        const [figY, setFigY] = React.useState('')
        const [figGroup, setFigGroup] = React.useState('')
        const [figColumns, setFigColumns] = React.useState('')
        const [figJournal, setFigJournal] = React.useState('nature')
        const [figError, setFigError] = React.useState('ci95')
        const [figTitle, setFigTitle] = React.useState('')
        const [figXLabel, setFigXLabel] = React.useState('')
        const [figYLabel, setFigYLabel] = React.useState('')
        const [figBusy, setFigBusy] = React.useState(false)
        const [figResult, setFigResult] = React.useState(null)
        const [figErrorMsg, setFigErrorMsg] = React.useState(null)
        const [figInteractive, setFigInteractive] = React.useState(false)
        const [figCopied, setFigCopied] = React.useState(false)
        const [galleryCopiedId, setGalleryCopiedId] = React.useState(null)

        const load = React.useCallback(async () => {
          setBusy(true)
          try {
            const response = await fetch(`${API}/state`, { headers: { accept: 'application/json' } })
            const payload = await response.json()
            if (!payload?.ok) throw new Error(payload?.error || 'unknown')
            setState(payload)
            setError(null)
          } catch (failure) {
            setError(String(failure?.message || failure))
          } finally {
            setBusy(false)
          }
        }, [])

        const loadCandidates = React.useCallback(async () => {
          try {
            const response = await fetch(`${API}/candidates`, { headers: { accept: 'application/json' } })
            const payload = await response.json()
            setCandidates(payload?.ok ? payload : null)
          } catch {
            setCandidates(null)
          }
        }, [])

        // 图库：纯元数据，与数据无关，加载一次即可。
        const loadGallery = React.useCallback(async () => {
          try {
            const response = await fetch(`${API}/gallery`, { headers: { accept: 'application/json' } })
            const payload = await response.json()
            setGallery(payload?.ok ? payload : null)
          } catch {
            setGallery(null)
          }
        }, [])

        // 登记：把绝对路径丢给服务端跑审计并落台账。面板与 Agent 的 lab_ingest 同源。
        const doIngest = React.useCallback(async (path) => {
          if (!path || ingesting) return
          setIngesting(true)
          setIngestMsg(null)
          try {
            const response = await fetch(`${API}/ingest`, {
              method: 'POST',
              headers: { 'content-type': 'application/json', accept: 'application/json' },
              body: JSON.stringify({ path })
            })
            const payload = await response.json()
            if (!payload?.ok) throw new Error(payload?.error || `ingest failed (${response.status})`)
            setIngestMsg({ ok: true, text: `${t('ingestOk')}：${payload.id}${payload.cached ? `（${t('ingestCached')}）` : ''}` })
            setPathDraft('')
            await Promise.all([load(), loadCandidates()])
          } catch (failure) {
            setIngestMsg({ ok: false, text: String(failure?.message || failure) })
          } finally {
            setIngesting(false)
          }
        }, [ingesting, load, loadCandidates, t])

        // 选图判读：数据画像 + 一句「我想看什么」，引擎返回该画什么图、用哪些列。
        const runRecommend = React.useCallback(async (datasetId) => {
          if (!datasetId || recBusy) return
          setRecBusy(true)
          setRecResult(null)
          setRecError(null)
          try {
            const query = new URLSearchParams({ datasetId, question: recQuestion.trim() })
            const response = await fetch(`${API}/recommend?${query}`, { headers: { accept: 'application/json' } })
            const payload = await response.json()
            if (!payload?.ok) throw new Error(payload?.error || `recommend failed (${response.status})`)
            setRecResult(payload)
          } catch (failure) {
            setRecError(String(failure?.message || failure))
          } finally {
            setRecBusy(false)
          }
        }, [recQuestion, recBusy])

        // 出版级出图：把表单参数交给 /figure，与 Agent 的 lab_figure 共用引擎与台账。
        const runFigure = React.useCallback(async (datasetId) => {
          if (!datasetId || figBusy) return
          setFigBusy(true)
          setFigResult(null)
          setFigInteractive(false)
          setFigErrorMsg(null)
          try {
            const body = {
              datasetId,
              chart: figChart,
              journal: figJournal || 'nature',
              error: figError || 'ci95',
              title: figTitle || undefined,
              xLabel: figXLabel || undefined,
              yLabel: figYLabel || undefined
            }
            if (figChart === 'heatmap') {
              body.columns = figColumns || undefined
            } else if (figChart === 'hist') {
              body.x = figX
              body.group = figGroup || undefined
            } else {
              body.x = figX
              body.y = figY
              body.group = figGroup || undefined
            }
            const response = await fetch(`${API}/figure`, {
              method: 'POST',
              headers: { 'content-type': 'application/json', accept: 'application/json' },
              body: JSON.stringify(body)
            })
            const payload = await response.json()
            if (!payload?.ok) throw new Error(payload?.error || `figure failed (${response.status})`)
            setFigResult(payload.run)
            await load()
          } catch (failure) {
            setFigErrorMsg(String(failure?.message || failure))
          } finally {
            setFigBusy(false)
          }
        }, [figChart, figJournal, figError, figTitle, figXLabel, figYLabel, figColumns, figX, figY, figGroup, figBusy, load])

        // 「用这个图」：把一张示例板或一条判读推荐的参数填进出图表单，并滚到出图区。
        const applySpec = React.useCallback((spec) => {
          if (!spec) return
          if (spec.chart) setFigChart(spec.chart)
          setFigX(spec.x || '')
          setFigY(spec.y || '')
          setFigColumns(Array.isArray(spec.columns) ? spec.columns.join(', ') : (spec.columns || ''))
          setFigGroup(spec.group || '')
          if (spec.journal) setFigJournal(spec.journal)
          if (figureRef.current) figureRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }, [])

        // 信息图类型是 AI 绘制：点「复制提示词模板」把一句可发送的话放进剪贴板，
        // 用户在会话里粘给 Agent，Agent 用 lab_infographic 生成。
        const copyInfographicPrompt = React.useCallback(async (item) => {
          const prompt = `请帮我用信息图「${item.name}」（${item.name_en}）展示以下内容。` +
            `类型：${item.engine?.type || item.id}。` +
            `请描述要展示的数据/步骤，然后用 lab_infographic 生成自包含 HTML 信息图。`
          try {
            await navigator.clipboard.writeText(prompt)
            setGalleryCopiedId(item.id)
            setTimeout(() => setGalleryCopiedId(null), 1600)
          } catch {
            setGalleryCopiedId(null)
          }
        }, [])

        // 整页布局下没有常驻会话区。用户显式点「AI 协助」时才创建或恢复会话，
        // 创建走宿主公开接口 ensureSession，工作台不自己开会话、也不自造聊天界面。
        const openChat = React.useCallback(async () => {
          setChat(true)
          setChatError(null)
          if (typeof service?.ensureSession !== 'function') return
          if (service.currentSession?.()) return
          setChatPending(true)
          try {
            await service.ensureSession({})
          } catch (failure) {
            setChatError(String(failure?.message || failure))
          } finally {
            setChatPending(false)
          }
        }, [service])

        React.useEffect(() => {
          load()
          loadCandidates()
          loadGallery()
          const timer = setInterval(() => { load(); loadCandidates() }, 12000)
          return () => clearInterval(timer)
        }, [load, loadCandidates, loadGallery])

        const datasets = state?.datasets || []
        const runs = state?.runs || []
        const figures = runs.filter((run) => run.kind === 'figure')
        const statsRuns = runs.filter((run) => run.kind === 'stats')
        const python = state?.python || {}

        // 出图表单：x/y/group 根据图表类型取类别列或数值列，heatmap 走 columns 文本。
        const figSelectedDataset = datasets.find((item) => item.id === figDataset) || datasets[0] || null
        const figProfile = figSelectedDataset?.profile || {}
        const figNumericCols = (figProfile.columns || []).filter((column) => column.kind === 'numeric').map((column) => column.name)
        const figCatCols = (figProfile.columns || []).filter((column) => column.kind === 'categorical').map((column) => column.name)
        const figXCols = (figChart === 'scatter' || figChart === 'hist') ? figNumericCols : figCatCols
        const toggleIn = (list, value) => (list.includes(value) ? list.filter((item) => item !== value) : [...list, value])
        const colSelect = (options, value, onChange, emptyLabel) =>
          h('select', { className: 'dshAlSel', value, onChange: (event) => onChange(event.target.value), disabled: options.length === 0 },
            h('option', { value: '' }, options.length === 0 ? emptyLabel : '—'),
            ...options.map((opt) => h('option', { key: opt, value: opt }, opt)))
        const chipMulti = (options, selected, onToggle, emptyLabel) =>
          options.length === 0
            ? h('span', { className: 'dshAlHint' }, emptyLabel)
            : h('div', { className: 'dshAlChipRow' }, options.map((opt) =>
                h('button', {
                  key: opt, type: 'button', className: 'dshAlChipBtn',
                  'data-on': String(selected.includes(opt)),
                  onClick: () => onToggle(toggleIn(selected, opt))
                }, opt)))

        const header = h('header', { className: 'dshAlHeader' },
          h('span', { className: 'dshAlMark' }, 'AL'),
          h('span', { className: 'dshAlTitle' }, t('panelTitle')),
          h('span', { className: 'dshAlMeta' },
            h('span', null,
              h('span', { className: 'dshAlDot', 'data-state': python.ok ? 'ok' : 'bad' }),
              python.ok ? `${t('pythonOk')} · ${python.version || ''}` : `${t('pythonBad')}`),
            h('span', null, `${t('datasets')} ${datasets.length}`),
            h('span', null, `${t('runs')} ${runs.length}`)),
          h('span', { className: 'dshAlSpacer' }),
          chat
            ? h('button', { className: 'dshAlBtn', onClick: () => setChat(false) }, t('chatClose'))
            : h('button', { className: 'dshAlBtn', onClick: openChat }, t('chatOpen')),
          h('button', { className: 'dshAlBtn', onClick: load, disabled: busy }, busy ? '…' : t('refresh'))
        )

        // 宿主把原生会话节点交给面板，整页布局里由我们自己决定它出现的位置。
        const chatDrawer = !chat ? null : h('aside', { className: 'dshAlChat' },
          h('div', { className: 'dshAlChatHead' },
            h('span', null, t('chatTitle')),
            h('span', { className: 'dshAlSpacer' }),
            h('button', { className: 'dshAlBtn', onClick: () => setChat(false) }, '×')),
          h('div', { className: 'dshAlChatBody' },
            // 没有绑定会话时宿主把 conversation 节点隐藏（display:none），
            // 这时底层的说明文字才会露出来，避免抽屉一片空白。
            h('div', { className: 'dshAlChatHint' }, t('chatHint')),
            h('div', { className: 'dshAlChatSlot' }, conversation || null),
            chatPending ? h('div', { className: 'dshAlChatHint' }, t('chatStarting')) : null,
            chatError ? h('div', { className: 'dshAlChatHint' },
              h('strong', null, t('chatFailed')),
              h('div', null, chatError)) : null))

        const shell = (body) => h('div', { className: 'dshAlRoot' },
          h('div', { className: 'dshAlMain' }, body),
          chatDrawer)

        if (error) {
          return shell(h('div', { className: 'dshAl' }, header,
            h('div', { className: 'dshAlBody' },
              h('div', { className: 'dshAlErr' }, `${t('loadFailed')}：${error}`))))
        }
        if (!state) {
          return shell(h('div', { className: 'dshAl' }, header, h('div', { className: 'dshAlBody' }, '…')))
        }

        const datasetCards = datasets.length === 0
          ? h('div', { className: 'dshAlEmpty' },
            h('div', null, h('strong', null, t('noData'))),
            h('div', null, t('noDataHint')))
          : h('div', { className: 'dshAlGrid' }, datasets.map((dataset) => {
            const profile = dataset.profile || {}
            const columns = profile.columns || []
            const warnings = profile.warnings || []
            return h('article', { className: 'dshAlCard', key: dataset.id },
              h('div', { className: 'dshAlCardHead' },
                h('span', { className: 'dshAlCardName' }, dataset.name),
                h('span', { className: 'dshAlCardId' }, dataset.id),
                h('span', { className: 'dshAlSpacer' }),
                h('button', { className: 'dshAlBtn', onClick: () => doIngest(dataset.path), disabled: ingesting }, ingesting ? t('reauditing') : t('reaudit'))),
              h('div', { className: 'dshAlCardMeta' },
                `${dataset.rows} ${t('rows')} × ${dataset.columns} ${t('cols')}`,
                h('br'),
                h('span', { className: 'dshAlMono' }, `sha256 ${String(dataset.sha256 || '').slice(0, 12)}…`)),
              columns.length
                ? h('div', { className: 'dshAlCardMeta' },
                  columns.slice(0, 4).map((column) =>
                    h('div', { key: column.name },
                      `${column.name}：`,
                      column.kind === 'numeric'
                        ? `均值 ${column.mean}，SD ${column.sd}，${t('missing')} ${column.missing}`
                        : `${column.unique} 个水平，${t('missing')} ${column.missing}`)))
                : null,
              warnings.length
                ? h('div', { className: 'dshAlWarn' },
                  h('div', null, `${t('warning')}（${warnings.length}）`),
                  warnings.slice(0, 2).map((warning, index) => h('div', { key: index }, `· ${warning}`)))
                : null)
          }))

        const figureGrid = figures.length === 0
          ? h('div', { className: 'dshAlEmpty' }, t('emptyFigures'))
          : h('div', { className: 'dshAlGrid' }, figures.map((run) => {
            const preview = (run.files || []).find((file) => String(file).toLowerCase().endsWith('.png'))
              || (run.files || []).find((file) => String(file).toLowerCase().endsWith('.svg'))
            const source = preview ? `${API}/file?path=${encodeURIComponent(preview)}` : null
            return h('figure', { className: 'dshAlFig', key: run.id },
              source ? h('img', { src: source, alt: run.caption || run.id, loading: 'lazy' }) : null,
              h('figcaption', null,
                h('div', null, run.caption || run.id),
                h('div', { className: 'dshAlMono' }, `${run.id} · ${run.spec?.journal || ''} ${run.spec?.chart || ''}`)))
          }))

        const runRows = statsRuns.length === 0
          ? h('div', { className: 'dshAlEmpty' }, t('emptyRuns'))
          : h('table', { className: 'dshAlTable' },
            h('thead', null, h('tr', null,
              h('th', null, 'ID'), h('th', null, '数据集'), h('th', null, '分析'), h('th', null, '结论'), h('th', null, '时间'))),
            h('tbody', null, statsRuns.map((run) =>
              h('tr', { key: run.id },
                h('td', { className: 'dshAlMono' }, run.id),
                h('td', null, run.datasetId),
                h('td', null, `${run.spec?.analysis || ''}${run.spec?.dv ? ` · ${run.spec.dv}` : ''}`),
                h('td', null, run.headline || ''),
                h('td', { className: 'dshAlMono' }, formatTime(run.startedAt))))))

        const inboxFiles = candidates?.files || []
        const ingestSection = h('section', { className: 'dshAlSection' },
          h('h2', { className: 'dshAlSectionTitle' }, t('ingestTitle')),
          h('div', { className: 'dshAlField' },
            h('input', {
              className: 'dshAlInput',
              placeholder: t('ingestPlaceholder'),
              value: pathDraft,
              onChange: (event) => setPathDraft(event.target.value),
              onKeyDown: (event) => { if (event.key === 'Enter') doIngest(pathDraft.trim()) }
            }),
            h('button', { className: 'dshAlBtn', onClick: () => doIngest(pathDraft.trim()), disabled: ingesting || !pathDraft.trim() }, ingesting ? t('ingestBusy') : t('ingestBtn'))),
          ingestMsg ? h('div', { className: 'dshAlMsg', 'data-ok': String(ingestMsg.ok) }, ingestMsg.text) : null,
          h('h2', { className: 'dshAlSectionTitle', style: { marginTop: '16px' } }, t('inboxTitle'), h('small', null, t('inboxHint'))),
          candidates?.inbox
            ? h('div', { className: 'dshAlHint', style: { marginBottom: '8px' } }, `${t('inboxPath')}：`, h('span', { className: 'dshAlMono' }, candidates.inbox))
            : null,
          inboxFiles.length === 0
            ? h('div', { className: 'dshAlEmpty' }, t('inboxEmpty'))
            : h('ul', { className: 'dshAlList' }, inboxFiles.map((file) =>
                h('li', { className: 'dshAlListItem', key: file.path },
                  h('span', { className: 'dshAlCardName' }, file.name),
                  h('span', { className: 'dshAlChip' }, `${(file.size / 1024).toFixed(1)} KB`),
                  h('button', { className: 'dshAlBtn', onClick: () => doIngest(file.path), disabled: ingesting }, ingesting ? '…' : t('ingestBtn'))))))

        // 图库：每种图一张示例板，点击展开「是什么 / 解决什么 / 数据要求 / 怎么读 / 误用」。
        const galleryCategories = gallery?.categories || []
        const gallerySection = h('section', { className: 'dshAlSection' },
          h('h2', { className: 'dshAlSectionTitle' }, t('galleryTitle'), h('small', null, t('galleryHint'))),
          galleryCategories.length === 0
            ? h('div', { className: 'dshAlEmpty' }, t('galleryEmpty'))
            : galleryCategories.map((category) => h('div', { key: category.name, style: { marginBottom: '16px' } },
                h('h3', { className: 'dshAlGroupTitle' }, category.name, h('small', null, category.name_en)),
                h('div', { className: 'dshAlGrid' }, category.items.map((item) => {
                  const open = galleryOpen === item.id
                  const isAcademic = !!item.engine?.chart
                  const isInfographic = item.engine?.command === 'infographic'
                  return h('article', {
                    className: 'dshAlCard', key: item.id,
                    style: { cursor: 'pointer' },
                    onClick: () => setGalleryOpen(open ? null : item.id)
                  },
                    h('div', { className: 'dshAlCardHead' },
                      h('span', { className: 'dshAlCardName' }, item.name),
                      h('span', { className: 'dshAlCardId' }, item.name_en),
                      h('span', { className: 'dshAlChip' }, item.kind === 'academic' ? '学术' : '信息图'),
                      h('span', { className: 'dshAlSpacer' }),
                      h('span', { className: 'dshAlHint' }, open ? '收起' : '详情')),
                    h('div', { className: 'dshAlCardMeta' }, item.summary),
                    open
                      ? h('div', null,
                          item.definition ? h('div', { className: 'dshAlCardMeta' }, h('strong', null, t('galleryDefinition')), h('br'), item.definition) : null,
                          item.purpose ? h('div', { className: 'dshAlCardMeta' }, h('strong', null, t('galleryPurpose')), h('br'), item.purpose) : null,
                          item.data ? h('div', { className: 'dshAlCardMeta' }, h('strong', null, t('galleryData')), h('br'), item.data) : null,
                          item.read ? h('div', { className: 'dshAlCardMeta' }, h('strong', null, t('galleryRead')), h('br'), item.read) : null,
                          item.pitfalls ? h('div', { className: 'dshAlWarn' }, h('strong', null, t('galleryPitfalls')), h('br'), item.pitfalls) : null,
                          h('div', { style: { marginTop: '10px' } },
                            isAcademic
                              ? h('button', { className: 'dshAlBtn', onClick: (event) => { event.stopPropagation(); applySpec({ chart: item.engine.chart }) } }, t('galleryUse'))
                              : isInfographic
                                ? h('div', null,
                                    h('div', { className: 'dshAlHint', style: { marginBottom: '5px' } }, t('galleryInfographic')),
                                    h('button', { className: 'dshAlBtn', onClick: (event) => { event.stopPropagation(); copyInfographicPrompt(item) } },
                                      galleryCopiedId === item.id ? t('galleryCopied') : t('galleryCopyPrompt')))
                                : null))
                      : null)
                })))))

        // 选图判读：画像 + 一句研究问题 → 推荐图，点推荐直接出图。
        const recSelectedDataset = datasets.find((item) => item.id === recDataset) || datasets[0] || null
        const intentPresets = [
          ['compare', t('intentCompare')],
          ['trend', t('intentTrend')],
          ['distribution', t('intentDistribution')],
          ['correlation', t('intentCorrelation')],
          ['composition', t('intentComposition')],
          ['overview', t('intentOverview')]
        ]
        const recommendSection = h('section', { className: 'dshAlSection' },
          h('h2', { className: 'dshAlSectionTitle' }, t('recommendTitle'), h('small', null, t('recommendHint'))),
          datasets.length === 0
            ? h('div', { className: 'dshAlEmpty' }, t('pickDataset'))
            : h('div', null,
              h('div', { className: 'dshAlFieldRow' },
                h('div', { className: 'dshAlFieldCol', style: { flex: '1 1 280px' } },
                  h('span', null, t('recommendDataset')),
                  h('select', { className: 'dshAlSel', value: recSelectedDataset?.id || '', onChange: (event) => setRecDataset(event.target.value) },
                    datasets.map((dataset) => h('option', { key: dataset.id, value: dataset.id }, `${dataset.name} · ${dataset.id}`))))),
              h('div', { className: 'dshAlField' },
                h('input', {
                  className: 'dshAlInput',
                  placeholder: t('recommendPlaceholder'),
                  value: recQuestion,
                  onChange: (event) => setRecQuestion(event.target.value),
                  onKeyDown: (event) => { if (event.key === 'Enter') runRecommend(recSelectedDataset?.id) }
                }),
                h('button', { className: 'dshAlBtn', onClick: () => runRecommend(recSelectedDataset?.id), disabled: recBusy || !recSelectedDataset }, recBusy ? t('recommendRunning') : t('recommendRun'))),
              h('div', { className: 'dshAlChipRow', style: { marginBottom: '10px' } }, intentPresets.map(([key, label]) =>
                h('button', { className: 'dshAlChipBtn', key, type: 'button', onClick: () => setRecQuestion(key) }, label))),
              recError ? h('div', { className: 'dshAlMsg', 'data-ok': 'false' }, recError) : null,
              recResult && (recResult.recommendations || []).length
                ? h('div', { className: 'dshAlResult' },
                    h('div', { className: 'dshAlResultHead' },
                      h('span', { className: 'dshAlCardName' }, t('recommendResult')),
                      h('span', { className: 'dshAlChip' }, recResult.intent || '')),
                    (recResult.recommendations || []).map((rec, index) =>
                      h('div', { className: 'dshAlResultLine', key: index, style: { marginBottom: '10px' } },
                        h('strong', null, `${index + 1}. ${rec.name || rec.chart_id}`),
                        h('span', { className: 'dshAlHint' }, `（${rec.chart_id}）`),
                        h('div', null, rec.reason),
                        h('button', { className: 'dshAlBtn', style: { marginTop: '5px' }, onClick: () => applySpec(rec.spec) }, t('recommendDraw')))))
                : recResult ? h('div', { className: 'dshAlEmpty' }, recResult.hint || t('recommendEmpty')) : null))

        // 出图表单：按图表类型露出 x/y/group 或 columns，误差棒只在 bar/line 出现。
        const chartOptions = ['bar', 'line', 'scatter', 'box', 'violin', 'raincloud', 'hist', 'heatmap']
        const journalOptions = ['nature', 'science', 'ieee', 'aps', 'plos', 'generic']
        const figFields = (() => {
          if (figChart === 'heatmap') {
            return h('div', { className: 'dshAlFieldRow' },
              h('div', { className: 'dshAlFieldCol', style: { flex: '1 1 320px' } },
                h('span', null, t('figureColumns')),
                h('input', { className: 'dshAlInput', value: figColumns, onChange: (event) => setFigColumns(event.target.value), placeholder: 'outcome_score, bmi, followup_days' })))
          }
          if (figChart === 'hist') {
            return h('div', { className: 'dshAlFieldRow' },
              h('div', { className: 'dshAlFieldCol' },
                h('span', null, t('figureX')),
                colSelect(figNumericCols, figX, setFigX, t('noNumericCols'))),
              h('div', { className: 'dshAlFieldCol' },
                h('span', null, t('figureGroup')),
                colSelect(figCatCols, figGroup, setFigGroup, t('noCatCols'))))
          }
          return h('div', { className: 'dshAlFieldRow' },
            h('div', { className: 'dshAlFieldCol' },
              h('span', null, t('figureX')),
              colSelect(figXCols, figX, setFigX, figXCols.length === 0 ? t('noCatCols') : '—')),
            h('div', { className: 'dshAlFieldCol' },
              h('span', null, t('figureY')),
              colSelect(figNumericCols, figY, setFigY, t('noNumericCols'))),
            h('div', { className: 'dshAlFieldCol' },
              h('span', null, t('figureGroup')),
              colSelect(figCatCols, figGroup, setFigGroup, t('noCatCols'))))
        })()

        const figPreview = (figResult?.files || []).find((file) => String(file).toLowerCase().endsWith('.png'))
          || (figResult?.files || []).find((file) => String(file).toLowerCase().endsWith('.svg'))
        const figPreviewSrc = figPreview ? `${API}/file?path=${encodeURIComponent(figPreview)}` : null
        const figFileLinks = ['pdf', 'svg', 'png'].map((ext) => {
          const file = (figResult?.files || []).find((entry) => String(entry).toLowerCase().endsWith(`.${ext}`))
          return file
            ? h('a', { className: 'dshAlBtn', key: ext, href: `${API}/file?path=${encodeURIComponent(file)}`, target: '_blank', rel: 'noreferrer' }, ext.toUpperCase())
            : null
        }).filter(Boolean)
        // 交互视图：引擎对多数图型额外产出 `<stem>.interactive.html`，面板在 iframe 里内嵌。
        const figInteractiveFile = (figResult?.files || []).find((entry) => String(entry).toLowerCase().endsWith('.html')) || null
        const figInteractiveSrc = figInteractiveFile ? `${API}/file?path=${encodeURIComponent(figInteractiveFile)}` : null

        const figureSection = h('section', { className: 'dshAlSection', ref: figureRef },
          h('h2', { className: 'dshAlSectionTitle' }, t('figureTitle'), h('small', null, t('figureHint'))),
          datasets.length === 0
            ? h('div', { className: 'dshAlEmpty' }, t('pickDataset'))
            : h('div', null,
              h('div', { className: 'dshAlFieldRow' },
                h('div', { className: 'dshAlFieldCol', style: { flex: '1 1 260px' } },
                  h('span', null, t('statsDataset')),
                  h('select', { className: 'dshAlSel', value: figSelectedDataset?.id || '', onChange: (event) => setFigDataset(event.target.value) },
                    datasets.map((dataset) => h('option', { key: dataset.id, value: dataset.id }, `${dataset.name} · ${dataset.id}`)))),
                h('div', { className: 'dshAlFieldCol', style: { flex: '1 1 200px' } },
                  h('span', null, t('figureChart')),
                  h('select', { className: 'dshAlSel', value: figChart, onChange: (event) => setFigChart(event.target.value) },
                    chartOptions.map((chart) => h('option', { key: chart, value: chart }, chart))))),
              figFields,
              h('div', { className: 'dshAlFieldRow' },
                h('div', { className: 'dshAlFieldCol' },
                  h('span', null, t('figureJournal')),
                  colSelect(journalOptions, figJournal, setFigJournal, '—')),
                figChart === 'bar' || figChart === 'line'
                  ? h('div', { className: 'dshAlFieldCol' },
                      h('span', null, t('figureError')),
                      colSelect(['ci95', 'sem', 'sd', 'none'], figError, setFigError, '—'))
                  : null),
              h('div', { className: 'dshAlFieldRow' },
                h('div', { className: 'dshAlFieldCol', style: { flex: '1 1 260px' } },
                  h('span', null, t('figureTitleLabel')),
                  h('input', { className: 'dshAlInput', value: figTitle, onChange: (event) => setFigTitle(event.target.value) })),
                h('div', { className: 'dshAlFieldCol' },
                  h('span', null, t('figureXLabelLabel')),
                  h('input', { className: 'dshAlInput', value: figXLabel, onChange: (event) => setFigXLabel(event.target.value) })),
                h('div', { className: 'dshAlFieldCol' },
                  h('span', null, t('figureYLabelLabel')),
                  h('input', { className: 'dshAlInput', value: figYLabel, onChange: (event) => setFigYLabel(event.target.value) }))),
              h('div', { className: 'dshAlField' },
                h('button', { className: 'dshAlBtn', onClick: () => runFigure(figSelectedDataset?.id), disabled: figBusy || !figSelectedDataset }, figBusy ? t('figureRunning') : t('figureRun'))),
              figErrorMsg ? h('div', { className: 'dshAlMsg', 'data-ok': 'false' }, figErrorMsg) : null,
              figResult
                ? h('div', { className: 'dshAlResult' },
                    h('div', { className: 'dshAlResultHead' },
                      h('span', { className: 'dshAlCardName' }, t('figureResultTitle')),
                      h('span', { className: 'dshAlCardId' }, figResult.id),
                      h('span', { className: 'dshAlSpacer' }),
                      figInteractiveSrc
                        ? h('button', {
                            className: figInteractive ? 'dshAlBtn dshAlBtnOn' : 'dshAlBtn',
                            key: 'interactive',
                            onClick: () => setFigInteractive((value) => !value)
                          }, t('figureInteractive'))
                        : null,
                      ...figFileLinks),
                    figPreviewSrc && !figInteractive
                      ? h('img', { className: 'dshAlFigPreview', src: figPreviewSrc, alt: figResult.caption || figResult.id })
                      : null,
                    figInteractive && figInteractiveSrc
                      ? h('iframe', {
                          className: 'dshAlFigFrame',
                          src: figInteractiveSrc,
                          title: figResult.caption || t('figureInteractive'),
                          sandbox: 'allow-scripts allow-same-origin'
                        })
                      : null,
                    figResult.caption ? h('div', { className: 'dshAlResultLine' }, figResult.caption) : null,
                    figResult.description
                      ? h('div', { className: 'dshAlResultLine', style: { color: 'var(--dsh-al-muted, #777)' } }, `${t('figureDescription')}：${figResult.description}`)
                      : null,
                    figResult.prompt
                      ? h('div', { className: 'dshAlField' },
                          h('button', {
                            className: 'dshAlBtn',
                            onClick: () => {
                              const done = () => { setFigCopied(true); setTimeout(() => setFigCopied(false), 1600) }
                              if (navigator?.clipboard?.writeText) {
                                navigator.clipboard.writeText(figResult.prompt).then(done, () => done())
                              } else {
                                done()
                              }
                            }
                          }, figCopied ? t('figureCopied') : t('figureCopyPrompt')))
                      : null,
                    (figResult.warnings || []).slice(0, 4).map((warning, index) =>
                      h('div', { className: 'dshAlWarn', key: index }, `· ${warning}`)))
                : null))

        return shell(h('div', { className: 'dshAl' },
          header,
          h('div', { className: 'dshAlBody' },
            python.ok ? null : h('div', { className: 'dshAlErr', style: { marginBottom: '14px' } }, python.error || t('pythonBad')),
            ingestSection,
            recommendSection,
            gallerySection,
            figureSection,
            h('section', { className: 'dshAlSection' },
              h('h2', { className: 'dshAlSectionTitle' }, t('datasets'), h('small', null, `共 ${datasets.length} 个`)),
              datasetCards),
            h('section', { className: 'dshAlSection' },
              h('h2', { className: 'dshAlSectionTitle' }, t('figures'), h('small', null, 'PDF / SVG / PNG（300 dpi）')),
              figureGrid),
            h('section', { className: 'dshAlSection' },
              h('h2', { className: 'dshAlSectionTitle' }, t('runs'), h('small', null, t('refreshHint'))),
              runRows))))
      }
    }

    // ---------------------------------------------------------------- 装配 --

    function apply(ctx) {
      installStyles()
      ctx.effect(() => ctx.locale.register(NS, dict), 'dsh-academic-lab: dictionaries')
      const t = ctx.locale.bind(NS)
      const Panel = createPanel(t)
      ctx.effect(() => ctx.desktopWorkbenches.register({
        title: 'DSH 学术数据工作台',
        titleEn: 'DSH Academic Data Lab',
        panelTitle: 'DSH 学术数据工作台',
        description: '数据审计、统计推断与出版级出图；每次分析留指纹与运行台账，结果可复现。',
        repository: 'https://github.com/dsh-local/dsh-academic-lab',
        category: '数据',
        customFrame: true,
        sessionSetupBody: '这个工作台不需要绑定会话就能查看数据与图表；要让 Agent 做统计和出图，请在绑定到本工作台的对话里直接描述分析需求。'
      }, Panel), 'dsh-academic-lab: registration')
    }

    return { apply, inject: ['desktopWorkbenches', 'locale'] }
  }
})
