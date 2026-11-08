#!/usr/bin/env node
/**
 * 打包前检查：files 清单是否齐全、有没有越界路径、体积是否超限。
 * 不替代 DSH 的安装校验，只保证 pnpm pack 产出的 tgz 里确实有该有的东西。
 */
import { readdirSync, statSync } from 'node:fs'
import { readFile, stat } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const ROOT = resolve(import.meta.dirname, '..')
const failures = []

const pkg = JSON.parse(await readFile(join(ROOT, 'package.json'), 'utf8'))
const files = pkg.files || []

function fail(message) {
  failures.push(message)
  console.log(`  ✗ ${message}`)
}

console.log('files 清单')
let total = 0
for (const entry of files) {
  try {
    const info = await stat(join(ROOT, entry))
    if (info.isDirectory()) {
      const names = readdirSync(join(ROOT, entry))
      if (!names.length) fail(`${entry}/ 是空目录`)
      else console.log(`  ✓ ${entry}/（${names.length} 项）`)
      for (const name of names) total += statSync(join(ROOT, entry, name)).size
      continue
    }
    total += info.size
    console.log(`  ✓ ${entry}（${(info.size / 1024).toFixed(1)} KB）`)
  } catch {
    fail(`${entry} 不存在`)
  }
}
console.log(`  合计 ${(total / 1024).toFixed(1)} KB`)

console.log('清单约束')
if (!pkg.main || !files.includes(pkg.main.replace(/^\.\//, ''))) fail('main 必须出现在 files 里')
if (pkg.dsh?.bundle?.patch) {
  const patch = pkg.dsh.bundle.patch.replace(/^\.\//, '')
  if (!files.includes(patch)) fail('cordis.patch.yml 必须在 files 里')
  const text = await readFile(join(ROOT, patch), 'utf8')
  if (!text.includes('dshHomePath(')) fail('cordis.patch.yml 应该用 dshHomePath 注入数据目录')
  if (!text.includes(pkg.name)) fail('cordis.patch.yml 里应包含插件名')
}
for (const file of files) {
  if (file.startsWith('/') || file.includes('..')) fail(`${file} 是绝对路径或越界路径`)
}
if (!(pkg.dsh?.client?.platform === 'web')) fail('缺少 dsh.client.platform = web')
if (!Array.isArray(pkg.dsh?.client?.inject) || !pkg.dsh.client.inject.includes('dsh-desktop-workbenches')) {
  fail('客户端 inject 需要 dsh-desktop-workbenches')
}
if (files.some((file) => file.endsWith('.py'))) {
  const runner = await readFile(join(ROOT, 'py', 'lab_runner.py'), 'utf8')
  if (!runner.includes('def main')) fail('py/lab_runner.py 不像入口文件')
}

if (failures.length) {
  console.log(`\n${failures.length} 项失败`)
  process.exit(1)
}
console.log('\n打包检查通过。')
