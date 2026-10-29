// 本地 macOS 安装版入口；不运行 CI 安装器，不修改应用或日常配置。
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { access, copyFile, cp, mkdir, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir, release } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

const { values } = parseArgs({ options: {
  app: { type: 'string', default: '/Applications/MyCollab.app' },
  'smoke-only': { type: 'boolean', default: false },
  'report-root': { type: 'string' }, help: { type: 'boolean', default: false },
} })
if (values.help) {
  console.log('本地 macOS：node desktop/tests/local-macos/run.mjs [--app /Applications/MyCollab.app] [--smoke-only] [--report-root 目录]')
  process.exit(0)
}
if (process.platform !== 'darwin') throw new Error('本入口仅用于本地 macOS，不可在 Linux/WSL 或 Windows 代替执行。')
const here = path.dirname(fileURLToPath(import.meta.url))
const shared = path.resolve(here, '../shared')
const bundle = path.resolve(values.app)
if (!bundle.endsWith('.app')) throw new Error('--app 必须指向已安装的开发版 .app 目录。')
const executable = path.join(bundle, 'Contents/MacOS/MyCollab')
const asar = path.join(bundle, 'Contents/Resources/app.asar')
await access(executable)
await access(asar)
const stage = await mkdtemp(path.join(tmpdir(), 'mycollab-macos-e2e-'))
const runId = new Date().toISOString().replaceAll(':', '-') + '-' + path.basename(stage).split('-').at(-1)
const report = path.join(path.resolve(values['report-root'] || path.join(here, '../../test-results/local-macos')), runId)
for (const name of ['package.json', 'package-lock.json', 'playwright.config.mjs', 'server.mjs', 'server.test.mjs', 'fixtures.mjs', 'acceptance.spec.mjs']) {
  await copyFile(path.join(shared, name), path.join(stage, name))
}
const env = { ...process.env, MYCOLLAB_TEST_PLATFORM: 'darwin', MYCOLLAB_TEST_APP_BINARY: executable }
delete env.ELECTRON_RUN_AS_NODE
const execute = (command, args, timeout) => {
  const result = spawnSync(command, args, { cwd: stage, env, stdio: 'inherit', timeout })
  if (result.error) throw result.error
  return result.status ?? 1
}
const digest = async filename => {
  const hash = createHash('sha256')
  for await (const chunk of createReadStream(filename)) hash.update(chunk)
  return hash.digest('hex')
}
let code = 1
try {
  if (execute('npm', ['ci', '--ignore-scripts', '--no-audit', '--no-fund'], 180000)) throw new Error('测试依赖安装失败。')
  if (execute(process.execPath, ['--test', 'server.test.mjs'], 30000)) throw new Error('本机 HTTP 夹具测试失败。')
  code = execute(process.execPath, ['node_modules/@playwright/test/cli.js', 'test',
    ...(values['smoke-only'] ? ['--grep-invert', '@known-issue'] : [])], 660000)
} finally {
  await mkdir(report, { recursive: true })
  try { await cp(path.join(stage, 'results'), report, { recursive: true }) }
  catch (error) { if (error.code !== 'ENOENT') throw error }
  await writeFile(path.join(report, 'run.json'), JSON.stringify({ app: bundle,
    exeSha256: await digest(executable), appAsarSha256: await digest(asar),
    node: process.version, os: release(), arch: process.arch, smokeOnly: values['smoke-only'], exitCode: code,
    scope: 'macOS 安装版 Electron + 本机 HTTP 夹具；非 Django、供应商、双机网络或原生对话框验收。',
  }, null, 2) + '\n')
  console.log(`验收报告：${report}\n本次独立测试工具目录：${stage}`)
}
process.exitCode = code
