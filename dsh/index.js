/**
 * DSH 学术数据工作台 · 服务端入口。
 *
 * 只做三件事：
 *   1. 用本机 Python 科学栈（numpy/pandas/scipy/statsmodels/matplotlib）执行
 *      数据审计、统计推断和出版级出图；本插件不自己实现统计量。
 *   2. 把每次分析的「输入指纹 / 参数 / 环境 / 产物」写进运行台账，保证可复现。
 *   3. 给工作台面板提供只读接口：数据集、运行记录、图表文件。
 *
 * 为什么不在 Node 里算统计：效应量、稳健标准误、多重比较校正这些只要有一处
 * 实现偏差，论文就是错的。statsmodels/scipy 是被反复验证过的实现，用它们。
 */
import Schema from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { spawn } from 'node:child_process'
import { createHash, randomUUID } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { mkdir, readFile, readdir, rename, stat, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { basename, extname, isAbsolute, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = 'dsh-academic-lab'
export const inject = ['connection', 'tools', 'systemPrompt']
export const Config = Schema.object({
  root: Schema.string().required(),
  python: Schema.string().default(''),
  figuresDir: Schema.string().default('figures')
})

const API = '/api/dsh-academic-lab'
const PY_DIR = resolve(fileURLToPath(new URL('../py/', import.meta.url)))
const RUNNER = join(PY_DIR, 'lab_runner.py')
const MAX_INPUT_BYTES = 200 * 1024 * 1024
const PY_TIMEOUT_MS = 180_000
const SUPPORTED_EXT = new Set(['.csv', '.tsv', '.txt', '.xlsx', '.xlsm', '.xls', '.json', '.jsonl', '.ndjson', '.parquet'])

class LabError extends Error {
  constructor(message, status = 400) {
    super(message)
    this.status = status
  }
}

// ------------------------------------------------------------ 小工具 ---

function nowIso() {
  return new Date().toISOString()
}

function shortId(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${randomUUID().slice(0, 6)}`
}

function slugify(value) {
  return String(value)
    .toLowerCase()
    .replace(/\.[a-z0-9]+$/, '')
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48) || 'dataset'
}

async function ensureDirs(root) {
  for (const dir of ['datasets', 'runs', 'figures', 'cache']) {
    await mkdir(join(root, dir), { recursive: true })
  }
}

async function readJsonFile(file, fallback = null) {
  try {
    return JSON.parse(await readFile(file, 'utf8'))
  } catch {
    return fallback
  }
}

async function writeJsonFile(file, value) {
  const temp = `${file}.${process.pid}.tmp`
  await writeFile(temp, JSON.stringify(value, null, 2), 'utf8')
  await rename(temp, file)
}

async function sha256File(file) {
  return new Promise((resolveHash, reject) => {
    const hash = createHash('sha256')
    const stream = createReadStream(file)
    stream.on('data', (chunk) => hash.update(chunk))
    stream.on('error', reject)
    stream.on('end', () => resolveHash(hash.digest('hex')))
  })
}

function jsonResponse(value, status = 200) {
  return Response.json(value, { status, headers: { 'cache-control': 'no-store' } })
}

function route(path, methods, fetch) {
  return { path: `${API}/${path}`, methods, requestBody: 'buffered', fetch }
}

// --------------------------------------------------------- Python 桥 ---

const PY_CANDIDATES = [
  process.env.DSH_LAB_PYTHON,
  '/opt/homebrew/bin/python3',
  '/usr/local/bin/python3',
  '/usr/bin/python3',
  'python3'
].filter(Boolean)

const PY_PROBE = 'import numpy,pandas,scipy,statsmodels,matplotlib;print("ok")'
let pythonCache = null

function runProcess(command, args, { input, timeoutMs = PY_TIMEOUT_MS, env } = {}) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(command, args, {
      env: { ...process.env, ...env },
      stdio: ['pipe', 'pipe', 'pipe']
    })
    const outChunks = []
    const errChunks = []
    let settled = false
    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill('SIGKILL')
      rejectRun(new LabError(`Python 执行超时（${Math.round(timeoutMs / 1000)} 秒）。数据量或图数量可能过大。`, 504))
    }, timeoutMs)

    child.stdout.on('data', (chunk) => outChunks.push(chunk))
    child.stderr.on('data', (chunk) => errChunks.push(chunk))
    child.on('error', (error) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      rejectRun(new LabError(`无法启动 Python（${command}）：${error.message}`))
    })
    child.on('close', (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolveRun({
        code,
        stdout: Buffer.concat(outChunks).toString('utf8'),
        stderr: Buffer.concat(errChunks).toString('utf8')
      })
    })
    if (input !== undefined) child.stdin.end(input)
    else child.stdin.end()
  })
}

/** 找一台装了科学栈的 Python。宿主进程的 PATH 往往不含 Homebrew，所以要猜路径。 */
async function detectPython(configured) {
  if (pythonCache && (!configured || pythonCache.command === configured)) return pythonCache
  const candidates = [configured, ...PY_CANDIDATES].filter(Boolean)
  const attempts = []
  for (const command of candidates) {
    try {
      const result = await runProcess(command, ['-c', PY_PROBE], { timeoutMs: 20_000 })
      if (result.code === 0 && result.stdout.trim() === 'ok') {
        const version = await runProcess(command, ['-c', 'import sys;print(sys.version.split()[0])'], { timeoutMs: 10_000 })
        pythonCache = { command, version: version.stdout.trim() || 'unknown' }
        return pythonCache
      }
      attempts.push(`${command}: 缺依赖或不可用`)
    } catch (error) {
      attempts.push(`${command}: ${error.message}`)
    }
  }
  throw new LabError(
    '本机没找到带科学栈的 Python。需要 numpy / pandas / scipy / statsmodels / matplotlib。\n'
      + '修复：python3 -m pip install numpy pandas scipy statsmodels matplotlib openpyxl\n'
      + '或在插件配置里写死解释器路径（config.python）。\n尝试过：'
      + attempts.join('；'),
    503
  )
}

async function runEngine(root, configuredPython, payload) {
  const python = await detectPython(configuredPython)
  await mkdir(join(root, 'cache', 'matplotlib'), { recursive: true })
  const result = await runProcess(python.command, [RUNNER, '-'], {
    input: JSON.stringify(payload),
    env: {
      MPLCONFIGDIR: join(root, 'cache', 'matplotlib'),
      MPLBACKEND: 'Agg',
      PYTHONIOENCODING: 'utf-8',
      PYTHONHASHSEED: '0'
    }
  })
  let parsed = null
  try {
    parsed = JSON.parse(result.stdout)
  } catch {
    // 半截 JSON 说明进程被打断或打印了多余内容；把 stderr 带出去便于定位。
  }
  if (!parsed) {
    throw new LabError(
      `分析引擎返回了无法解析的输出（exit ${result.code}）：`
        + (result.stderr.trim().split('\n').slice(-6).join('\n') || result.stdout.slice(0, 400)),
      500
    )
  }
  if (!parsed.ok) {
    const error = parsed.error || {}
    const hint = error.hint ? `\n建议：${error.hint}` : ''
    throw new LabError(`${error.message || '分析失败'}${hint}`, 422)
  }
  parsed.__stderr = result.stderr.trim().split('\n').filter((line) => line && !line.includes('findfont')).slice(-6)
  return { python: python.command, version: python.version, data: parsed }
}

// ------------------------------------------------------- 数据集登记 ---

function datasetIdFor(file, hash) {
  return `${slugify(basename(file))}-${hash.slice(0, 8)}`
}

async function resolveDataPath(rawPath, root) {
  if (!rawPath || typeof rawPath !== 'string') throw new LabError('需要数据文件路径。')
  const candidate = isAbsolute(rawPath) ? rawPath : resolve(process.cwd(), rawPath)
  if (!existsSync(candidate)) {
    throw new LabError(`文件不存在：${candidate}。请传绝对路径（当前进程目录是 ${process.cwd()}）。`)
  }
  const info = await stat(candidate)
  if (!info.isFile()) throw new LabError(`不是文件：${candidate}`)
  if (info.size > MAX_INPUT_BYTES) {
    throw new LabError(`文件 ${(info.size / 1024 / 1024).toFixed(0)} MB，超过 200 MB 上限；先抽样或聚合再分析。`)
  }
  const suffix = extname(candidate).toLowerCase()
  if (!SUPPORTED_EXT.has(suffix)) {
    throw new LabError(`不支持的文件类型：${suffix || '无扩展名'}。支持 CSV/TSV/XLSX/JSON/JSONL/Parquet。`)
  }
  return candidate
}

async function listDatasets(root) {
  const dir = join(root, 'datasets')
  await mkdir(dir, { recursive: true })
  const files = (await readdir(dir)).filter((file) => file.endsWith('.json'))
  const entries = []
  for (const file of files) {
    const record = await readJsonFile(join(dir, file))
    if (record) entries.push(record)
  }
  entries.sort((a, b) => String(b.registeredAt).localeCompare(String(a.registeredAt)))
  return entries
}

async function getDataset(root, id) {
  if (!id) throw new LabError('需要 datasetId（先用 lab_datasets 看已登记的数据集）。')
  const record = await readJsonFile(join(root, 'datasets', `${id}.json`))
  if (!record) throw new LabError(`没有这个数据集：${id}`)
  return record
}

async function listRuns(root, limit = 20) {
  const dir = join(root, 'runs')
  await mkdir(dir, { recursive: true })
  const files = (await readdir(dir)).filter((file) => file.endsWith('.json'))
  const entries = []
  for (const file of files) {
    const record = await readJsonFile(join(dir, file))
    if (record) entries.push(record)
  }
  entries.sort((a, b) => String(b.startedAt).localeCompare(String(a.startedAt)))
  return entries.slice(0, Math.max(1, Math.min(200, limit)))
}

async function saveRun(root, record) {
  await writeJsonFile(join(root, 'runs', `${record.id}.json`), record)
}

// ------------------------------------------------------- 文本渲染 ---

function fmtP(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'n/a'
  const p = Number(value)
  if (p < 0.001) return 'p < .001'
  return `p = ${p.toFixed(3)}`
}

function bulletList(items) {
  return items.filter(Boolean).map((item) => `- ${item}`).join('\n')
}

function formatProfile(result) {
  const lines = []
  lines.push(`数据：${basename(result.dataset?.path || '')}，${result.shape.rows} 行 × ${result.shape.columns} 列`)
  lines.push(`指纹：sha256 ${String(result.dataset?.sha256 || '').slice(0, 16)}…`)
  lines.push('')
  const numeric = result.columns.filter((column) => column.kind === 'numeric')
  if (numeric.length) {
    lines.push('数值列：')
    for (const column of numeric.slice(0, 12)) {
      lines.push(
        `- ${column.name}：n=${column.n ?? ''}，均值 ${column.mean}，SD ${column.sd}，`
          + `中位数 ${column.median}，范围 ${column.min}~${column.max}，缺失 ${column.missing}`
          + (column.outliers_iqr ? `，离群 ${column.outliers_iqr}` : '')
      )
    }
  }
  const categorical = result.columns.filter((column) => column.kind === 'categorical')
  if (categorical.length) {
    lines.push('类别列：')
    for (const column of categorical.slice(0, 10)) {
      const tops = (column.top_values || []).slice(0, 4).map((item) => `${item.value}(${item.count})`).join(' / ')
      lines.push(`- ${column.name}：${column.unique} 个水平，缺失 ${column.missing}${tops ? `，主要为 ${tops}` : ''}`)
    }
  }
  if (result.warnings?.length) {
    lines.push('')
    lines.push('需要先处理的问题：')
    lines.push(bulletList(result.warnings))
  }
  if (result.reading?.length) {
    lines.push('')
    lines.push(result.reading.join('\n'))
  }
  return lines.join('\n')
}

function formatStats(result) {
  const lines = []
  if (result.analysis === "compare") {
    for (const item of result.results || []) {
      const groups = Object.entries(item.groups || {}).map(([label, count]) => `${label} n=${count}`).join("，")
      lines.push(`- ${item.sentence || `${item.dv}（${item.method}）`}`)
      if (groups) lines.push(`  分组：${groups}${item.dropped_rows ? `；剔除缺失 ${item.dropped_rows} 行` : ""}`)
      if (item.p_adjusted !== undefined) {
        lines.push(`  ${String(item.p_adjusted_method || result.correction || "holm").toUpperCase()} 校正后 ${fmtP(item.p_adjusted)}`)
      }
      if (item.ci95_difference) lines.push(`  差值 95% CI：[${item.ci95_difference[0]}, ${item.ci95_difference[1]}]`)
      if (item.effect_size?.omega_squared !== undefined) lines.push(`  ω² = ${item.effect_size.omega_squared}（小样本校正后的效应量）`)
      if (item.effect_size?.hedges_g !== undefined) lines.push(`  Hedges g = ${item.effect_size.hedges_g}`)
      if (item.normality) {
        lines.push(`  正态性：${item.normality.map((entry) => `${entry.label} ${entry.test} p=${entry.p}`).join("；")}`)
      }
      if (item.levene_p !== undefined) lines.push(`  Levene 方差齐性 p = ${item.levene_p}`)
    }
  } else if (result.analysis === "describe") {
    for (const row of result.table || []) {
      lines.push(
        `- ${row.variable}：n=${row.n}，均值 ${row.mean} ± ${row.sd}，中位数 ${row.median}`
          + `（IQR ${row.iqr?.[0]}~${row.iqr?.[1]}），范围 ${row.min}~${row.max}`
          + (row.ci95_mean ? `，均值 95% CI [${row.ci95_mean[0]}, ${row.ci95_mean[1]}]` : "")
      )
    }
  } else if (result.analysis === "regress") {
    lines.push(`R² = ${result.r2}（校正 ${result.r2_adj}），F = ${result.f}（p = ${result.f_p}），n = ${result.n}`)
    lines.push(
      `稳健标准误：${result.robust ? "HC3" : "否"}；Breusch-Pagan p = ${result.breusch_pagan_p}；`
        + `Durbin-Watson = ${result.durbin_watson}`
    )
    for (const term of result.coefficients || []) {
      const stars = term.p < 0.001 ? "***" : term.p < 0.01 ? "**" : term.p < 0.05 ? "*" : ""
      lines.push(
        `- ${term.term}：β = ${term.beta}${stars}，SE ${term.se}，95% CI [${term.ci95?.[0]}, ${term.ci95?.[1]}]，p = ${term.p}`
      )
    }
    if (result.standardized?.length) {
      lines.push(`标准化系数：${result.standardized.map((entry) => `${entry.term} ${entry.beta_std}`).join("，")}`)
    }
    if (result.vif?.length) {
      lines.push(`VIF：${result.vif.map((entry) => `${entry.variable} ${entry.vif}`).join("，")}`)
    }
  } else {
    lines.push(result.sentence || "")
  }

  const reading = (result.reading || []).filter((line) => !lines.some((existing) => existing.includes(line)))
  if (reading.length) {
    lines.push("")
    lines.push(reading.join("\n"))
  }
  if (result.warnings?.length) {
    lines.push("")
    lines.push("注意：")
    lines.push(bulletList(result.warnings))
  }
  return lines.filter((line) => line !== undefined && line !== "").join("\n")
}

// ---------------------------------------------------------- 插件 ---

export function apply(ctx, config) {
  const root = resolve(config.root)
  const figuresDir = isAbsolute(config.figuresDir) ? config.figuresDir : resolve(process.cwd(), config.figuresDir)
  const state = { python: null, lastError: null }

  ctx.effect(() => {
    ensureDirs(root).catch((error) => {
      state.lastError = String(error?.message || error)
    })
    return () => {}
  }, 'academic-lab: data root')

  // ------------------------------------------------------------ 路由 --
  ctx.effect(() => {
    const disposers = []
    const register = (entry) => {
      try {
        const dispose = ctx.connection.fetch.register(entry)
        if (typeof dispose === 'function') disposers.push(dispose)
      } catch (error) {
        console.warn(`[dsh-academic-lab] 路由 ${entry.path} 登记失败：${(error && error.message) || error}`)
      }
    }

    register(route('health', ['GET'], async () => {
      let python = { ok: false, command: null, version: null, error: null }
      try {
        const detected = await detectPython(config.python)
        python = { ok: true, command: detected.command, version: detected.version }
        state.python = detected
      } catch (error) {
        python.error = error.message
        state.lastError = error.message
      }
      const [datasets, runs] = await Promise.all([listDatasets(root), listRuns(root, 200)])
      return jsonResponse({
        ok: true,
        name,
        root,
        figuresDir,
        python,
        datasets: datasets.length,
        runs: runs.length,
        lastError: state.lastError
      })
    }))

    register(route('state', ['GET'], async () => {
      const [datasets, runs] = await Promise.all([listDatasets(root), listRuns(root, 50)])
      let python = { ok: false, command: null, version: null }
      try {
        python = { ok: true, ...(await detectPython(config.python)) }
      } catch (error) {
        python.error = error.message
      }
      return jsonResponse({ ok: true, python, datasets, runs })
    }))

    register(route('file', ['GET'], async (request) => {
      const url = new URL(request.url)
      const requested = url.searchParams.get('path') || ''
      const normalized = resolve(requested)
      const allowed = join(root, 'figures') + sep
      const alsoAllowed = figuresDir + sep
      if (!normalized.startsWith(allowed) && !normalized.startsWith(alsoAllowed)) {
        return jsonResponse({ ok: false, error: '只能读取本工作台的图表目录' }, 403)
      }
      try {
        const payload = await readFile(normalized)
        const extension = extname(normalized).toLowerCase()
        const types = {
          '.png': 'image/png',
          '.svg': 'image/svg+xml',
          '.pdf': 'application/pdf',
          '.json': 'application/json'
        }
        return new Response(payload, {
          status: 200,
          headers: { 'content-type': types[extension] || 'application/octet-stream', 'cache-control': 'no-cache' }
        })
      } catch {
        return jsonResponse({ ok: false, error: '文件不存在' }, 404)
      }
    }))

    // ---------------------------------------------- 数据入口（面板自服务）--
    // 面板没有宿主文件选择器（pickFile 在宿主协议里不存在），所以数据入口分成
    // 两条：① 数据目录里的 inbox/ 投放箱，用户把文件放进来即可点选；② 粘贴一个
    // 绝对路径（GUI 工作区标题栏能看到路径，或从 Finder 拖入复制）。两条都走
    // 同一个 ingest，与 Agent 的 lab_ingest 共用引擎与台账。
    register(route('candidates', ['GET'], async () => {
      const inbox = join(root, 'inbox')
      await mkdir(inbox, { recursive: true })
      const names = await readdir(inbox)
      const files = []
      for (const file of names) {
        const suffix = extname(file).toLowerCase()
        if (!SUPPORTED_EXT.has(suffix)) continue
        try {
          const info = await stat(join(inbox, file))
          if (info.isFile()) {
            files.push({ name: file, path: join(inbox, file), size: info.size, mtime: info.mtimeMs })
          }
        } catch {
          // 条目消失或不可读就跳过，不影响其余。
        }
      }
      files.sort((a, b) => b.mtime - a.mtime)
      return jsonResponse({ ok: true, inbox, files: files.slice(0, 500) })
    }))

    register(route('ingest', ['POST'], async (request) => {
      let body = {}
      try { body = await request.json() } catch { body = {} }
      const file = await resolveDataPath(body?.path, root)
      const hash = await sha256File(file)
      const id = datasetIdFor(file, hash)
      const existing = await readJsonFile(join(root, 'datasets', `${id}.json`))
      if (existing?.profile && existing.sha256 === hash) {
        return jsonResponse({ ok: true, id, record: existing, cached: true })
      }
      const { data } = await runEngine(root, config.python, { command: 'profile', path: file })
      const record = {
        id,
        name: String(body?.name || basename(file)),
        path: file,
        sha256: hash,
        rows: data.shape.rows,
        columns: data.shape.columns,
        registeredAt: existing?.registeredAt || nowIso(),
        auditedAt: nowIso(),
        profile: data
      }
      await writeJsonFile(join(root, 'datasets', `${id}.json`), record)
      return jsonResponse({ ok: true, id, record })
    }))

    // ---------------------------------------------- 统计推断（面板自服务）--
    // 面板把表单参数原样交给同一个引擎/同一个台账，与 Agent 的 lab_stats 同源，
    // 不会出现「面板算一遍、会话里再算一遍」结果对不上的情况。
    register(route('stats', ['POST'], async (request) => {
      let body = {}
      try { body = await request.json() } catch { body = {} }
      const dataset = await getDataset(root, body?.datasetId)
      const spec = {
        analysis: String(body?.analysis || ''),
        dv: body?.dv,
        group: body?.group,
        x: body?.x,
        y: body?.y,
        predictors: body?.predictors,
        columns: body?.columns,
        dvs: body?.dv,
        method: body?.method,
        correction: body?.correction,
        robust: body?.robust,
        alpha: body?.alpha
      }
      const hash = await sha256File(dataset.path)
      const startedAt = nowIso()
      const { data, python } = await runEngine(root, config.python, { command: 'stats', path: dataset.path, spec })
      const run = {
        id: shortId('run'),
        kind: 'stats',
        startedAt,
        finishedAt: nowIso(),
        datasetId: dataset.id,
        dataset: { path: dataset.path, sha256: hash },
        spec,
        python,
        result: data,
        headline: data.sentence || (data.reading || [])[0] || ''
      }
      await saveRun(root, run)
      return jsonResponse({ ok: true, run })
    }))

    // ---------------------------------------------- 出版级出图（面板自服务）--
    // 与 Agent 的 lab_figure 同源：同一引擎、同一 outDir 结构、同一台账。
    register(route('figure', ['POST'], async (request) => {
      let body = {}
      try { body = await request.json() } catch { body = {} }
      const dataset = await getDataset(root, body?.datasetId)
      const stem = slugify(String(body?.title || `${dataset.id}-${body?.chart || 'figure'}`))
      const runId = shortId('fig')
      const outDir = join(root, 'figures', runId)
      const spec = {
        chart: body?.chart,
        x: body?.x,
        y: body?.y,
        group: body?.group,
        journal: body?.journal || 'nature',
        widthMm: body?.widthMm,
        heightMm: body?.heightMm,
        error: body?.error || 'ci95',
        title: body?.title,
        xLabel: body?.xLabel,
        yLabel: body?.yLabel,
        caption: body?.caption,
        columns: body?.columns
      }
      const hash = await sha256File(dataset.path)
      const startedAt = nowIso()
      const { data, python } = await runEngine(root, config.python, {
        command: 'figure',
        path: dataset.path,
        spec,
        outDir,
        stem
      })
      const run = {
        id: runId,
        kind: 'figure',
        startedAt,
        finishedAt: nowIso(),
        datasetId: dataset.id,
        dataset: { path: dataset.path, sha256: hash },
        spec,
        python,
        files: data.files.map((file) => file.path),
        copies: [],
        caption: data.caption,
        warnings: data.warnings
      }
      await saveRun(root, run)
      return jsonResponse({ ok: true, run })
    }))

    return () => {
      for (const dispose of disposers) {
        if (typeof dispose === 'function') dispose()
      }
    }
  }, 'academic-lab: api routes')

  // --------------------------------------------------------- 工具 --
  const register = (tool) => ctx.tools.register(tool)
  const textOutput = () => ({
    schema: { type: 'string' },
    render: (_args, value) => [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value, null, 2) }]
  })

  register(defineTool({
    name: 'lab_datasets',
    description: 'List datasets registered in the DSH academic data workbench (id, rows × columns, fingerprint, when registered). Call this before lab_stats / lab_figure when you need an existing datasetId.',
    parameters: {},
    output: textOutput(),
    async execute() {
      const datasets = await listDatasets(root)
      if (!datasets.length) {
        return '还没有登记数据集。先让用户把 CSV/XLSX 放进工作区，再调用 lab_ingest（path 传绝对路径）。'
      }
      const lines = datasets.map((item) =>
        `- ${item.id}：${item.name}（${item.rows} 行 × ${item.columns} 列，sha256 ${String(item.sha256).slice(0, 12)}…，登记于 ${item.registeredAt}）`
      )
      return `共 ${datasets.length} 个数据集：\n${lines.join('\n')}`
    }
  }))

  register(defineTool({
    name: 'lab_ingest',
    description: 'Register a data file in the DSH academic data workbench and immediately audit it: rows/columns, per-column missingness and distributions, duplicates, constant columns, strong correlations, and warnings. Returns a datasetId used by the other lab_* tools. The file is read in place and never modified.',
    parameters: {
      path: { type: 'string', required: true, description: 'Absolute path of a CSV/TSV/XLSX/JSON/JSONL/Parquet file.' },
      name: { type: 'string', description: 'Human-readable dataset name; defaults to the file name.' }
    },
    output: textOutput(),
    async execute(args) {
      const file = await resolveDataPath(args?.path, root)
      const hash = await sha256File(file)
      const id = datasetIdFor(file, hash)
      const existing = await readJsonFile(join(root, 'datasets', `${id}.json`))
      if (existing?.profile) {
        return `数据集已登记：${id}（sha256 未变，直接复用上次审计结果）\n\n${formatProfile(existing.profile)}`
      }
      const { data } = await runEngine(root, config.python, { command: 'profile', path: file })
      const record = {
        id,
        name: String(args?.name || basename(file)),
        path: file,
        sha256: hash,
        rows: data.shape.rows,
        columns: data.shape.columns,
        registeredAt: nowIso(),
        profile: data
      }
      await writeJsonFile(join(root, 'datasets', `${id}.json`), record)
      return `已登记数据集 ${id}。\n\n${formatProfile(data)}`
    }
  }))

  register(defineTool({
    name: 'lab_profile',
    description: 'Re-audit a registered dataset (or an arbitrary path) and return the full data-quality report. Use after the data changes, or when you need details the ingest summary omitted (per-column stats, strong correlations, date detection).',
    parameters: {
      datasetId: { type: 'string', description: 'Dataset id from lab_datasets.' },
      path: { type: 'string', description: 'Or an absolute file path, to audit without registering.' }
    },
    output: textOutput(),
    async execute(args) {
      let file
      let record = null
      if (args?.datasetId) {
        record = await getDataset(root, args.datasetId)
        file = record.path
      } else {
        file = await resolveDataPath(args?.path, root)
      }
      const hash = await sha256File(file)
      const { data } = await runEngine(root, config.python, { command: 'profile', path: file })
      const changed = record ? record.sha256 !== hash : false
      if (record) {
        record.profile = data
        record.sha256 = hash
        record.auditedAt = nowIso()
        await writeJsonFile(join(root, 'datasets', `${record.id}.json`), record)
      }
      return `${changed ? '⚠️ 文件内容已变化，审计结果已更新。\n' : ''}${formatProfile(data)}`
    }
  }))

  register(defineTool({
    name: 'lab_stats',
    description: 'Run a statistical analysis with publication-style output: effect sizes, 95% CIs, assumption checks, and multiple-comparison correction. Analyses: describe (numeric summaries), compare (t-test / Mann-Whitney / ANOVA / Kruskal with Holm or BH correction across DVs), associate (Pearson/Spearman with CI), regress (OLS with robust HC3 option, VIF, Breusch-Pagan, Durbin-Watson), chisq (Cramer\'s V, Fisher exact for 2×2). Every call writes a reproducible run record.',
    parameters: {
      datasetId: { type: 'string', required: true, description: 'Dataset id from lab_datasets / lab_ingest.' },
      analysis: { type: 'string', required: true, description: 'describe | compare | associate | regress | chisq' },
      dv: { type: 'string', description: 'Dependent variable(s), comma-separated for compare.' },
      group: { type: 'string', description: 'Grouping column for compare.' },
      x: { type: 'string', description: 'x variable for associate / chisq.' },
      y: { type: 'string', description: 'y variable for associate / chisq.' },
      predictors: { type: 'string', description: 'Comma-separated predictors for regress.' },
      columns: { type: 'string', description: 'Comma-separated columns for describe (default: all numeric).' },
      method: { type: 'string', description: 'auto | welch | student | mannwhitney | anova | kruskal (compare); auto | pearson | spearman (associate).' },
      correction: { type: 'string', description: 'holm (default) | bh | none — applied across multiple DVs in compare.' },
      robust: { type: 'boolean', description: 'Use HC3 robust standard errors in regress (default true).' },
      alpha: { type: 'number', description: 'Significance level, default 0.05.' }
    },
    output: textOutput(),
    async execute(args) {
      const dataset = await getDataset(root, args?.datasetId)
      const spec = {
        analysis: String(args?.analysis || ''),
        dv: args?.dv,
        group: args?.group,
        x: args?.x,
        y: args?.y,
        predictors: args?.predictors,
        columns: args?.columns,
        dvs: args?.dv,
        method: args?.method,
        correction: args?.correction,
        robust: args?.robust,
        alpha: args?.alpha
      }
      const hash = await sha256File(dataset.path)
      const startedAt = nowIso()
      const { data, python } = await runEngine(root, config.python, { command: 'stats', path: dataset.path, spec })
      const run = {
        id: shortId('run'),
        kind: 'stats',
        startedAt,
        finishedAt: nowIso(),
        datasetId: dataset.id,
        dataset: { path: dataset.path, sha256: hash },
        spec,
        python,
        result: data,
        headline: (data.reading || [])[0] || ''
      }
      await saveRun(root, run)
      return `${formatStats(data)}\n\n— 运行记录 ${run.id}（数据指纹 ${hash.slice(0, 12)}…，已写入台账）`
    }
  }))

  register(defineTool({
    name: 'lab_figure',
    description: 'Render a publication-quality figure (PDF vector + SVG + 300 dpi PNG) at a journal column width with colorblind-safe colors. Charts: bar, line, scatter (optional fit + CI band), box, violin, raincloud, hist, heatmap. Journals: nature / science / ieee / aps / plos / generic. Returns file paths, n, and a caption draft. Files are saved to the workbench data directory and copied into the workspace figures/ folder.',
    parameters: {
      datasetId: { type: 'string', required: true, description: 'Dataset id.' },
      chart: { type: 'string', required: true, description: 'bar | line | scatter | box | violin | raincloud | hist | heatmap' },
      x: { type: 'string', description: 'x / grouping / category column.' },
      y: { type: 'string', description: 'y / value column.' },
      group: { type: 'string', description: 'Optional grouping column (legend).' },
      journal: { type: 'string', description: 'nature (default) | science | ieee | aps | plos | generic' },
      widthMm: { type: 'number', description: 'Width in mm; defaults to the journal single-column width.' },
      heightMm: { type: 'number', description: 'Height in mm; defaults to width × 0.72.' },
      error: { type: 'string', description: 'ci95 (default) | sem | sd | none' },
      title: { type: 'string', description: 'Figure title (rendered above the axes).' },
      xLabel: { type: 'string', description: 'x axis label.' },
      yLabel: { type: 'string', description: 'y axis label.' },
      caption: { type: 'string', description: 'Caption text; a draft with n and source is generated if omitted.' },
      columns: { type: 'string', description: 'Comma-separated numeric columns for heatmap.' },
      copyTo: { type: 'string', description: 'Optional absolute directory to copy the PNG/SVG/PDF into (typically the workspace figures/ folder, so the user can open them directly).' }
    },
    output: textOutput(),
    async execute(args) {
      const dataset = await getDataset(root, args?.datasetId)
      const stem = slugify(String(args?.title || `${dataset.id}-${args?.chart || 'figure'}`))
      const runId = shortId('fig')
      const outDir = join(root, 'figures', runId)
      const spec = {
        chart: args?.chart,
        x: args?.x,
        y: args?.y,
        group: args?.group,
        journal: args?.journal || 'nature',
        widthMm: args?.widthMm,
        heightMm: args?.heightMm,
        error: args?.error || 'ci95',
        title: args?.title,
        xLabel: args?.xLabel,
        yLabel: args?.yLabel,
        caption: args?.caption,
        columns: args?.columns
      }
      const hash = await sha256File(dataset.path)
      const startedAt = nowIso()
      const { data, python } = await runEngine(root, config.python, {
        command: 'figure',
        path: dataset.path,
        spec,
        outDir,
        stem
      })

      // 工作区副本：用户要能直接点开看，而不是去数据目录翻。
      // 宿主进程的 cwd 不一定可写，失败就退化为只有数据目录里的正式产物。
      const copies = []
      let copyError = null
      if (args?.copyTo) {
        try {
          const targetDir = isAbsolute(args.copyTo) ? args.copyTo : resolve(process.cwd(), args.copyTo)
          await mkdir(targetDir, { recursive: true })
          const base = join(targetDir, `${stem}-${runId.split('-').pop()}`)
          for (const file of data.files) {
            const target = `${base}${extname(file.path)}`
            await writeFile(target, await readFile(file.path))
            copies.push(target)
          }
        } catch (error) {
          copyError = String(error?.message || error)
        }
      }

      const run = {
        id: runId,
        kind: 'figure',
        startedAt,
        finishedAt: nowIso(),
        datasetId: dataset.id,
        dataset: { path: dataset.path, sha256: hash },
        spec,
        python,
        files: data.files.map((file) => file.path),
        copies,
        caption: data.caption,
        warnings: data.warnings
      }
      await saveRun(root, run)

      const list = data.files.map((file) => `- ${file.format.toUpperCase()}：${file.path}`).join('\n')
      const copiesList = copies.length
        ? copies.map((file) => `- ${file}`).join('\n')
        : copyError
          ? `（副本未写入：${copyError}；正式产物见上方路径）`
          : '（没有传 copyTo，未生成工作区副本）' 
      return [
        `已出图：${data.chart}（${data.journal} 版式），n = ${data.n}`,
        list,
        '',
        copies.length ? '工作区副本（报告/预览用）：' : '副本：',
        copiesList,
        '',
        `图注草稿：${data.caption}`,
        data.warnings?.length ? `\n注意：\n${bulletList(data.warnings)}` : '',
        '',
        `— 运行记录 ${runId}（数据指纹 ${hash.slice(0, 12)}…）`
      ].filter(Boolean).join('\n')
    }
  }))

  register(defineTool({
    name: 'lab_runs',
    description: 'List recent analysis runs from the reproducibility ledger: id, kind, dataset, parameters, and headline result. Use lab_run to see one run in full.',
    parameters: {
      limit: { type: 'number', description: 'How many runs to list, default 10.' },
      datasetId: { type: 'string', description: 'Only runs of this dataset.' }
    },
    output: textOutput(),
    async execute(args) {
      let runs = await listRuns(root, Number(args?.limit) || 10)
      if (args?.datasetId) runs = runs.filter((run) => run.datasetId === args.datasetId)
      if (!runs.length) return '运行台账为空。'
      const lines = runs.map((run) =>
        `- ${run.id}｜${run.kind}｜${run.datasetId}｜${run.startedAt}｜${run.headline || run.caption || ''}`
      )
      return `最近 ${runs.length} 次运行：\n${lines.join('\n')}`
    }
  }))

  register(defineTool({
    name: 'lab_run',
    description: 'Show one run record in full: exact parameters, input fingerprint, Python and package versions, output files, and the reproducibility note.',
    parameters: {
      runId: { type: 'string', required: true, description: 'Run id from lab_runs.' }
    },
    output: textOutput(),
    async execute(args) {
      const record = await readJsonFile(join(root, 'runs', `${args?.runId}.json`))
      if (!record) throw new LabError(`没有这次运行：${args?.runId}`)
      return JSON.stringify(record, null, 2)
    }
  }))

  console.log('[dsh-academic-lab] 已注册工具：lab_datasets / lab_ingest / lab_profile / lab_stats / lab_figure / lab_runs / lab_run')
  console.log(`[dsh-academic-lab] 数据目录：${root}`)

  ctx.systemPrompt.section({
    name: 'tool:academic-data-lab',
    order: 132,
    text: [
      'DSH academic data workbench: the user\'s data files live in the workspace; analysis and publication figures run through this workbench.',
      'Workflow: lab_ingest (absolute path) → read the audit warnings → lab_stats → lab_figure → report with effect sizes, CIs, n and the run id.',
      'Prefer lab_stats over ad-hoc python for inferential statistics: it returns effect sizes, 95% CIs, assumption checks and Holm/BH correction, and records provenance.',
      'Never claim a p value or effect size that lab_stats did not return; if the engine reports warnings (missingness, duplicates, small n, heteroscedasticity), surface them in the answer instead of hiding them.',
      'lab_figure writes PDF/SVG/PNG at journal column widths; cite the journal preset and the caption draft, and keep the n and units in the caption.',
      'Datasets, run records and figures live in the workbench data directory; the panel shows them read-only. Figures are also copied into the workspace figures/ folder for the user.'
    ].join(' ')
  })
}
