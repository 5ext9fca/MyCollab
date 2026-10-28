import { invoke } from '@tauri-apps/api/core'
export type Config = { server: string; model: string; opencode: string; ca_file: string; token_present: boolean; autostart: boolean }
export type Status = { running: boolean; exit_code: number | null; detail: { state?: string; pending_results?: number; rejected_results?: number }; configured: boolean }
export const api = {
  config: () => invoke<Config>('read_config'),
  save: (config: { server: string; model: string; opencode: string; ca_file: string; device_token: string }) => invoke<void>('save_config', { config }),
  status: () => invoke<Status>('runner_status'),
  start: () => invoke<void>('start_runner'), stop: () => invoke<void>('stop_runner'),
  diagnose: () => invoke<Record<string, unknown>>('diagnose'),
  open: () => invoke<void>('open_website'),
  autostart: (enabled: boolean) => invoke<void>('set_autostart', { enabled }),
  update: () => invoke<string>('check_update'),
}
