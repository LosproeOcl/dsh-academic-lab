#!/usr/bin/env node
/**
 * 本机验证：插件静态检查 + Python 引擎端到端（审计 → 统计 → 出图）。
 * 不联网、不写用户数据目录；所有产物落在 examples/out/ 下，跑完清理。
 */
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { mkdir, readFile, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const ROOT = resolve(import.meta.dirname, '..')
const PY = process.env.DSH_LAB_PYTHON || 'python3'
const OUT = join(ROOT, 'examples', '.verify-out')
const failures = []

function run(command, args, { input, cwd = ROOT } = {}) {
  return new Promise((done) => {
    const child = spawn(command, args, { cwd, env: { ...process.env, MPLBACKEND: 'Agg' }, stdio: ['pipe', 'pipe', 'pipe'] })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', (chunk) => { stdout += chunk })
    child.stderr.on('data', (chunk) => { stderr += chunk })
    child.on('error', (error) => done({ code: -1, stdout, stderr: String(error) }))
    child.on('close', (code) => done({ code, stdout, stderr }))
    child.stdin.end(input ?? '')
  })
}

function check(label, condition, detail = '') {
  if (condition) {
    console.log(`  ✓ ${label}`)
  } else {
    failures.push(`${label}${detail ? `：${detail}` : ''}`)
    console.log(`  ✗ ${label}${detail ? `：${detail}` : ''}`)
  }
}

async function engine(payload) {
  const result = await run(PY, [join(ROOT, 'py', 'lab_runner.py'), '-'], { input: JSON.stringify(payload) })
  try {
    return JSON.parse(result.stdout)
  } catch {
    return { ok: false, error: { message: `unparsable (exit ${result.code})`, hint: result.stderr.slice(-500) } }
  }
}

console.log('1) 静态检查')
for (const file of ['dsh/index.js', 'lib/client.js']) {
  const result = await run(process.execPath, ['--check', join(ROOT, file)])
  check(`${file} 语法`, result.code === 0, result.stderr.slice(0, 300))
}
const client = await readFile(join(ROOT, 'lib', 'client.js'), 'utf8')
check('客户端走 __ModuleLoader__', client.includes('__ModuleLoader__.load('))
check('客户端注册工作台', client.includes('desktopWorkbenches.register('))
const entry = await readFile(join(ROOT, 'dsh', 'index.js'), 'utf8')
check('服务端声明 inject', entry.includes("export const inject = ['connection', 'tools', 'systemPrompt']"))
check('路由登记包在 effect 内', entry.includes("'academic-lab: api routes'"))
check('数据入口路由存在', entry.includes("'candidates'") && entry.includes("'ingest'"))
check('客户端有数据入口', client.includes('doIngest') && client.includes('/candidates'))
check('统计路由存在', entry.includes("'stats'") && entry.includes("command: 'stats'"))
check('客户端有统计表单', client.includes('runStats') && client.includes('/stats') && client.includes('statAnalysis'))
check('出图路由存在', entry.includes("'figure'") && entry.includes("command: 'figure'"))
check('客户端有出图表单', client.includes('runFigure') && client.includes('/figure') && client.includes('figChart'))
check('数据目录用 dshHomePath', (await readFile(join(ROOT, 'cordis.patch.yml'), 'utf8')).includes("dshHomePath('academic-lab')"))

console.log('2) Python 依赖探测')
const probe = await run(PY, ['-c', 'import numpy,pandas,scipy,statsmodels,matplotlib;print("ok")'])
check(`科学栈可用（${PY}）`, probe.stdout.trim() === 'ok', probe.stderr.slice(0, 300))

const sample = join(ROOT, 'examples', 'trial.csv')
check('示例数据存在', existsSync(sample))
await mkdir(OUT, { recursive: true })

console.log('3) 数据审计')
const profile = await engine({ command: 'profile', path: sample })
check('profile 返回 ok', profile.ok === true, JSON.stringify(profile.error))
if (profile.ok) {
  check('行数 122', profile.shape.rows === 122, String(profile.shape.rows))
  check('识别重复行', (profile.warnings || []).some((w) => w.includes('重复')), (profile.warnings || []).join(' | '))
  check('数值列有 n 字段', profile.columns.filter((c) => c.kind === 'numeric').every((c) => typeof c.n === 'number'))
}

console.log('4) 统计推断')
const compare = await engine({
  command: 'stats',
  path: sample,
  spec: { analysis: 'compare', dv: 'outcome_score', group: 'group', correction: 'holm' }
})
check('compare 返回 ok', compare.ok === true, JSON.stringify(compare.error))
if (compare.ok) {
  const first = compare.results?.[0] || {}
  check('带效应量', Boolean(first.effect_size?.name), JSON.stringify(first.effect_size))
  check('带前提检查说明', Boolean(first.normality || first.levene_p !== undefined || compare.warnings?.length))
  check('p 值存在', typeof first.p === 'number', String(first.p))
  check('分组计数', first.groups && Object.values(first.groups).reduce((a, b) => a + b, 0) > 100)
}
const regress = await engine({
  command: 'stats',
  path: sample,
  spec: { analysis: 'regress', dv: 'outcome_score', predictors: ['bmi', 'age_years'], robust: true }
})
check('regress 返回 ok', regress.ok === true, JSON.stringify(regress.error))
if (regress.ok) {
  check('robust 标准误', regress.robust === true, String(regress.robust))
  check('系数含 CI', Array.isArray(regress.coefficients) && Array.isArray(regress.coefficients[0]?.ci95))
}

console.log('5) 出版级出图')
const figure = await engine({
  command: 'figure',
  path: sample,
  outDir: OUT,
  stem: 'verify-bar',
  spec: { chart: 'bar', x: 'group', y: 'outcome_score', journal: 'nature', title: '验证图' }
})
check('figure 返回 ok', figure.ok === true, JSON.stringify(figure.error))
if (figure.ok) {
  const files = figure.files || []
  for (const format of ['pdf', 'svg', 'png']) {
    const file = files.find((item) => item.format === format)
    check(`产出 ${format.toUpperCase()}`, Boolean(file && existsSync(file.path)), file?.path || 'missing')
  }
  check('图注带数据指纹', String(figure.caption || '').includes('sha256'))
}

const scatter = await engine({
  command: 'figure',
  path: sample,
  outDir: OUT,
  stem: 'verify-scatter',
  spec: { chart: 'scatter', x: 'bmi', y: 'outcome_score', journal: 'ieee', title: '散点' }
})
check('scatter 返回 ok', scatter.ok === true, JSON.stringify(scatter.error))
if (scatter.ok) {
  check('scatter 图注带 n', /n = \d+/.test(String(scatter.caption || '')), String(scatter.caption))
  check('scatter 图注不提误差棒', !String(scatter.caption || '').includes('误差棒'), String(scatter.caption))
}

const heatmap = await engine({
  command: 'figure',
  path: sample,
  outDir: OUT,
  stem: 'verify-heatmap',
  spec: { chart: 'heatmap', columns: ['age_years', 'bmi', 'outcome_score'], journal: 'nature', title: '相关矩阵' }
})
check('heatmap 返回 ok', heatmap.ok === true, JSON.stringify(heatmap.error))
if (heatmap.ok) {
  check('heatmap 图注带 n', /n = \d+/.test(String(heatmap.caption || '')), String(heatmap.caption))
}

await rm(OUT, { recursive: true, force: true })

if (failures.length) {
  console.log(`\n${failures.length} 项失败：`)
  for (const failure of failures) console.log(`  - ${failure}`)
  process.exit(1)
}
console.log('\n全部通过。')
