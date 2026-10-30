// 非 GUI 子进程夹具：配置只从管道读取，EOF 表示停止。
let input = ''
let configured = false
process.stdin.setEncoding('utf8')
process.stdin.on('data', chunk => {
  if (configured) return
  input += chunk
  const end = input.indexOf('\n')
  if (end < 0) return
  configured = true
  const config = JSON.parse(input.slice(0, end))
  if (process.argv.includes(config.device_token) || process.env.MYCOLLAB_TEST_SECRET) process.exit(3)
  if (config.model === 'exit') process.exit(2)
  if (process.argv.includes('--diagnose')) {
    console.log(JSON.stringify({ opencode: config.model === 'classified-error' ? 'unavailable' : 'ok', server: 'ok', protocol: 1, opencode_error: config.model === 'classified-error' ? 'permission_denied' : config.device_token, secret: config.device_token }))
    process.exit(0)
  }
  console.log(JSON.stringify({ event: 'ready' }))
})
process.stdin.on('end', () => process.exit(130))
