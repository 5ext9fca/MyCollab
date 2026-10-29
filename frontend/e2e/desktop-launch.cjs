// 只用于验收：在加载真实宿主之前隔离配置，不修改产品的凭据或安全策略。
const { app } = require('electron')
const path = require('node:path')
const profile = process.env.MYCOLLAB_DESKTOP_TEST_PROFILE
if (!profile || !path.isAbsolute(profile)) throw new Error('桌面验收需要独立的绝对配置路径')
app.setPath('userData', profile)
const home = process.env.MYCOLLAB_DESKTOP_TEST_HOME
if (home) {
  if (!path.isAbsolute(home)) throw new Error('迁移验收需要独立的绝对用户目录')
  app.setPath('home', home)
}
import('../../desktop/electron/main.mjs')
