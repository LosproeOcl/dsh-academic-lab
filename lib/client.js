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
.dshAlEmpty{padding:36px 20px;border:1px dashed var(--dsw-alias-border-l2);border-radius:12px;text-align:center;color:var(--dsw-alias-label-secondary);line-height:1.9}
.dshAlEmpty strong{color:var(--dsw-alias-label-primary)}
.dshAlErr{padding:10px 12px;border-radius:10px;background:color-mix(in srgb,var(--dsw-alias-state-error-primary) 12%,transparent);color:var(--dsw-alias-label-primary);font-size:12px;line-height:19px;white-space:pre-wrap}
.dshAlKbd{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;padding:1px 5px;border-radius:5px;background:var(--dsw-alias-bg-module-platform);border:1px solid var(--dsw-alias-border-l2)}
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
        loadFailed: '读取工作台状态失败',
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
        loadFailed: 'Failed to load workbench state',
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
      return function Panel() {
        const [state, setState] = React.useState(null)
        const [error, setError] = React.useState(null)
        const [busy, setBusy] = React.useState(false)

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

        React.useEffect(() => {
          load()
          const timer = setInterval(() => load(), 12000)
          return () => clearInterval(timer)
        }, [load])

        const datasets = state?.datasets || []
        const runs = state?.runs || []
        const figures = runs.filter((run) => run.kind === 'figure')
        const statsRuns = runs.filter((run) => run.kind === 'stats')
        const python = state?.python || {}

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
          h('button', { className: 'dshAlBtn', onClick: load, disabled: busy }, busy ? '…' : t('refresh'))
        )

        if (error) {
          return h('div', { className: 'dshAl' }, header,
            h('div', { className: 'dshAlBody' },
              h('div', { className: 'dshAlErr' }, `${t('loadFailed')}：${error}`)))
        }
        if (!state) {
          return h('div', { className: 'dshAl' }, header, h('div', { className: 'dshAlBody' }, '…'))
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
                h('span', { className: 'dshAlCardId' }, dataset.id)),
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

        return h('div', { className: 'dshAl' },
          header,
          h('div', { className: 'dshAlBody' },
            python.ok ? null : h('div', { className: 'dshAlErr', style: { marginBottom: '14px' } }, python.error || t('pythonBad')),
            h('section', { className: 'dshAlSection' },
              h('h2', { className: 'dshAlSectionTitle' }, t('datasets'), h('small', null, `共 ${datasets.length} 个`)),
              datasetCards),
            h('section', { className: 'dshAlSection' },
              h('h2', { className: 'dshAlSectionTitle' }, t('figures'), h('small', null, 'PDF / SVG / PNG（300 dpi）')),
              figureGrid),
            h('section', { className: 'dshAlSection' },
              h('h2', { className: 'dshAlSectionTitle' }, t('runs'), h('small', null, t('refreshHint'))),
              runRows)))
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
        // 宿主只在 ≤2 字符时把 icon 当字形渲染，图片路径用不上；白色卡片上 🐳 就是蓝鲸。
        icon: '🐳',
        sessionSetupBody: '这个工作台不需要绑定会话就能查看数据与图表；要让 Agent 做统计和出图，请在绑定到本工作台的对话里直接描述分析需求。'
      }, Panel), 'dsh-academic-lab: registration')
    }

    return { apply, inject: ['desktopWorkbenches', 'locale'] }
  }
})
