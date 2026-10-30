import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import ElementPlus from 'element-plus'
import App from './App.vue'
import { api } from './bridge'
vi.mock('./bridge', () => ({ api: {
  config: vi.fn(), status: vi.fn(), save: vi.fn(), start: vi.fn(), stop: vi.fn(), diagnose: vi.fn(), open: vi.fn(), autostart: vi.fn(), update: vi.fn(),
} }))
beforeEach(() => {
  vi.mocked(api.config).mockResolvedValue({ server:'https://example.com', model:'provider/model', opencode:'/opt/homebrew/bin/opencode', ca_file:'', token_present:true, autostart:false })
  vi.mocked(api.status).mockResolvedValue({ running:false, exit_code:null, configured:true, detail:{ state:'stopped', pending_results:1 } })
})
afterEach(() => { vi.clearAllMocks() })
it('读取配置不要求暴露已存凭据，保存后清空新凭据输入', async () => {
  const wrapper = mount(App, { global:{ plugins:[ElementPlus] } })
  await flushPromises()
  const secret = wrapper.find('input[type=password]')
  expect((secret.element as HTMLInputElement).value).toBe('')
  await secret.setValue('mc_agent_new')
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ device_token:'mc_agent_new' }))
  expect((secret.element as HTMLInputElement).value).toBe('')
  expect(wrapper.text()).toContain('待回传 1 项')
  wrapper.unmount()
})
it('运行中禁用配置修改和重复启动，保留停止入口', async () => {
  vi.mocked(api.status).mockResolvedValue({ running:true, exit_code:null, configured:true, detail:{state:'running'} })
  const wrapper = mount(App, { global:{plugins:[ElementPlus]} })
  await flushPromises()
  expect(wrapper.find('input[type=password]').attributes('disabled')).toBeDefined()
  const start = wrapper.findAll('button').find(b => b.text() === '启动')!
  const stop = wrapper.findAll('button').find(b => b.text() === '停止')!
  expect(start.attributes('disabled')).toBeDefined()
  await stop.trigger('click'); await flushPromises()
  expect(api.stop).toHaveBeenCalledOnce()
  wrapper.unmount()
})
it('登录启动默认关闭，原生设置失败时不显示为已开启', async () => {
  vi.mocked(api.autostart).mockRejectedValue('设置失败')
  const wrapper = mount(App, { global:{plugins:[ElementPlus]} })
  await flushPromises()
  const toggle = wrapper.find('[role="switch"]')
  expect(toggle.attributes('aria-checked')).toBe('false')
  await toggle.trigger('click'); await flushPromises()
  expect(api.autostart).toHaveBeenCalledWith(true)
  expect(toggle.attributes('aria-checked')).toBe('false')
  expect(wrapper.text()).toContain('设置失败')
  wrapper.unmount()
})
