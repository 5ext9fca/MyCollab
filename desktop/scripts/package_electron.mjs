/** 开发包使用临时签名；正式产物不得静默回退为未签名分发。 */
import { existsSync } from 'node:fs'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { requireNotarization, developmentEnvironment, packagingMode } from '../electron/release.mjs'
import { updatePolicy } from '../electron/updates.mjs'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
const desktop = fileURLToPath(new URL('..', import.meta.url))
const { development, directory: directoryOnly } = packagingMode(process.argv.slice(2))
if (!['darwin', 'win32'].includes(process.platform)) throw new Error('请在 Windows 或 macOS 构建桌面客户端。')
if (!['arm64', 'x64'].includes(process.arch) || (process.platform === 'win32' && process.arch !== 'x64')) {
  throw new Error('当前架构不在首批支持范围内。')
}
const runner = path.join(desktop, 'build/runner', `${process.platform === 'darwin' ? 'mac' : 'win'}-${process.arch}`,
  process.platform === 'win32' ? 'mycollab-runner.exe' : 'mycollab-runner')
if (!existsSync(runner)) throw new Error('请先用 Python 3.13 执行 scripts/build_sidecar.py --electron 构建本机 Runner。')
const config = JSON.parse(await readFile(path.join(desktop, 'electron-builder.json'), 'utf8'))
// 目标中的 arch 数组优先于 CLI；必须限制为本机 Runner 的架构。
const nativeTargets = process.platform === 'darwin' ? config.mac : config.win
nativeTargets.target = nativeTargets.target.map((/** @type {{target: string}} */ target) => ({ ...target, arch: [process.arch] }))
config.extraMetadata = { mycollabUpdates: { enabled: false } }
if (development) config.artifactName = 'MyCollab-${version}-${os}-${arch}-development.${ext}'
if (!development) {
  const root = process.env.MYCOLLAB_UPDATE_URL || ''
  const publisher = process.env.MYCOLLAB_UPDATE_PUBLISHER || ''
  const policy = { enabled: true, url: root, publisher, platform: process.platform, arch: process.arch }
  updatePolicy(policy, process.platform, process.arch)
  config.extraMetadata.mycollabUpdates = policy
  config.publish = [{ provider: 'generic', url: root, useMultipleRangeRequest: false }]
  if (process.platform === 'win32') config.win = { ...config.win, publisherName: publisher, verifyUpdateCodeSignature: true }
  else {
    requireNotarization(process.env)
    config.mac = { ...config.mac, notarize: true }
  }
}
await mkdir(path.join(desktop, 'build'), { recursive: true })
const generated = path.join(desktop, 'build/electron-config.json')
await writeFile(generated, JSON.stringify(config, null, 2))
const args = [path.join(desktop, 'node_modules/electron-builder/cli.js'), '--config', generated, '--publish', 'never',
  process.platform === 'darwin' ? '--mac' : '--win', '--' + process.arch]
const env = development ? developmentEnvironment(process.env) : { ...process.env }
if (development) {
  if (directoryOnly) args.push('--dir')
  if (process.platform === 'darwin') args.push('-c.mac.identity=-', '-c.mac.notarize=false')
  else args.push('-c.win.signExecutable=false')
} else {
  args.push('-c.forceCodeSigning=true')
}
const child = spawn(process.execPath, args, { cwd: desktop, env, stdio: 'inherit' })
child.on('error', () => { console.error('无法启动桌面打包工具。'); process.exitCode = 1 })
child.on('exit', code => { process.exitCode = code ?? 1 })
