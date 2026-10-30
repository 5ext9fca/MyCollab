import { isAppPage } from './policy.mjs'

/** 管理页面生成的 Blob 保存；字节仍由 Chromium 流式写入，不经过 IPC。 */
export class BlobDownloads {
  /** @type {Set<import('electron').DownloadItem>} */
  active = new Set()
  /** @param {() => void} failed */
  constructor(failed) { this.failed = failed }

  /** @param {import('electron').Event} event
   * @param {import('electron').DownloadItem} item
   * @param {import('electron').WebContents | undefined} contents
   * @param {import('electron').WebFrameMain | null} frame
   * @param {import('electron').WebContents | undefined} expected
   * @param {boolean} available
   */
  accept(event, item, contents, frame, expected, available) {
    if (!available || !expected || contents !== expected || !frame || frame !== expected.mainFrame ||
        !isAppPage(frame.url) || !/^blob:mycollab:\/\/app\/[0-9a-f-]{36}$/i.test(item.getURL())) {
      event.preventDefault()
      return
    }
    item.setSaveDialogOptions({ title: '保存文件', buttonLabel: '保存' })
    this.active.add(item)
    item.once('done', (_event, state) => {
      const tracked = this.active.delete(item)
      if (tracked && state === 'interrupted') this.failed()
    })
  }

  cancel() {
    for (const item of this.active) {
      // 先移除，身份切换造成的取消不弹出旧页面的失败提示。
      this.active.delete(item)
      item.cancel()
    }
  }
}
