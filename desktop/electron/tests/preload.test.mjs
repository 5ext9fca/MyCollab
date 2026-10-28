import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'

test('执行实际 preload，只暴露固定操作且不泄漏 Electron 对象', async () => {
  let exposed
  const calls = []
  const electron = {
    contextBridge: { exposeInMainWorld: (name, value) => { assert.equal(name, 'mycollabDesktop'); exposed = value } },
    ipcRenderer: { invoke: (channel, ...args) => { calls.push({ channel, args }); return Promise.resolve(true) } },
  }
  vm.runInNewContext(await readFile(new URL('../preload.cjs', import.meta.url), 'utf8'), {
    require: name => { assert.equal(name, 'electron'); return electron },
  })
  assert.deepEqual(Object.keys(exposed).sort(), ['startRunner', 'stopRunner', 'runnerStatus', 'diagnoseRunner', 'runnerBinding', 'bindRunner', 'settings', 'setServer', 'setLocalNetwork', 'setAutostart', 'openExternal', 'downloadLibrary'].sort())
  assert.equal(Object.isFrozen(exposed), true)
  await exposed.setServer('https://example.com')
  await exposed.downloadLibrary('/api/library/files/test/')
  assert.deepEqual(calls, [
    { channel: 'desktop:set-server', args: ['https://example.com'] },
    { channel: 'desktop:download-library', args: ['/api/library/files/test/'] },
  ])
})
