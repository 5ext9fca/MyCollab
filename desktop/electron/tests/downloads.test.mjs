import test from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { BlobDownloads } from '../downloads.mjs'

const blob = 'blob:mycollab://app/12345678-1234-1234-1234-123456789012'
function fixture(url = blob) {
  const frame = { url: 'mycollab://app/file-transfer' }
  const contents = { mainFrame: frame }
  const item = new EventEmitter()
  item.getURL = () => url
  item.cancel = () => { item.cancelled = true; item.emit('done', {}, 'cancelled') }
  item.setSaveDialogOptions = value => { item.dialog = value }
  const event = { preventDefault() { this.prevented = true } }
  return { frame, contents, item, event }
}

test('页面 Blob 使用原生保存选择，完成后不再参与身份切换取消', () => {
  const manager = new BlobDownloads(() => assert.fail('不应提示失败'))
  const { frame, contents, item, event } = fixture()
  manager.accept(event, item, contents, frame, contents, true)
  assert.equal(event.prevented, undefined)
  assert.deepEqual(item.dialog, { title: '保存文件', buttonLabel: '保存' })
  item.emit('done', {}, 'completed')
  manager.cancel()
  assert.equal(item.cancelled, undefined)
})

test('拒绝外部 Blob、任意 URL、子框架和身份切换中的新保存', () => {
  for (const url of ['blob:https://example.com/id', 'https://example.com/file', 'blob:mycollab://app.evil/id', 'file:///tmp/file']) {
    const { frame, contents, item, event } = fixture(url)
    new BlobDownloads(() => {}).accept(event, item, contents, frame, contents, true)
    assert.equal(event.prevented, true)
  }
  for (const kind of ['contents', 'frame', 'unavailable']) {
    const { frame, contents, item, event } = fixture()
    new BlobDownloads(() => {}).accept(event, item, kind === 'contents' ? {} : contents,
      kind === 'frame' ? { ...frame } : frame, contents, kind !== 'unavailable')
    assert.equal(event.prevented, true)
  }
})

test('切换身份取消全部未完成保存，重复清理无副作用，用户取消不报失败', () => {
  const manager = new BlobDownloads(() => assert.fail('不应提示失败'))
  const items = [fixture(), fixture()]
  for (const { frame, contents, item, event } of items) manager.accept(event, item, contents, frame, contents, true)
  items[0].item.emit('done', {}, 'cancelled')
  manager.cancel()
  manager.cancel()
  assert.equal(items[0].item.cancelled, undefined)
  assert.equal(items[1].item.cancelled, true)
  assert.equal(manager.active.size, 0)
})

test('保存中断仅提示一次失败，不保留任务', () => {
  let failures = 0
  const manager = new BlobDownloads(() => { failures++ })
  const { frame, contents, item, event } = fixture()
  manager.accept(event, item, contents, frame, contents, true)
  item.emit('done', {}, 'interrupted')
  item.emit('done', {}, 'interrupted')
  assert.equal(failures, 1)
  assert.equal(manager.active.size, 0)
})
