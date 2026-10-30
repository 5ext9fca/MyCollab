import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus, { ElMessage } from 'element-plus'
import { installDesktopLinks } from './platform/desktop'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'

import App from './App.vue'
import { router } from './router'
import { ensureCsrf } from './api/client'
import './style.css'

import { initializeTheme } from './theme'

const stopTheme = initializeTheme()
if (import.meta.hot) import.meta.hot.dispose(stopTheme)

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)

// Make sure the CSRF cookie exists before any unsafe request is sent.
ensureCsrf().catch(() => undefined)

installDesktopLinks(message => ElMessage.error(message))
app.mount('#app')
