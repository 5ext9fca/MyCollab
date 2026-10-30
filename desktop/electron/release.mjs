/** 与锁定版本打包器的凭据优先级保持一致；不读取或记录凭据内容。 */
/** @param {NodeJS.ProcessEnv} env */
export function requireNotarization(env) {
  const account = ['APPLE_ID', 'APPLE_APP_SPECIFIC_PASSWORD', 'APPLE_TEAM_ID']
  const api = ['APPLE_API_KEY', 'APPLE_API_KEY_ID', 'APPLE_API_ISSUER']
  const present = (/** @type {string} */ key) => Boolean(env[key]?.trim())
  // 打包器优先使用账户，其次 API 密钥，最后钥匙串配置；不允许残缺的高优先级配置被忽略。
  if (env.APPLE_ID || env.APPLE_APP_SPECIFIC_PASSWORD) {
    if (account.every(present)) return
    throw new Error('macOS 正式打包需要完整的 Apple 账户公证配置。')
  }
  if (api.some(key => Boolean(env[key]))) {
    if (api.every(present)) return
    throw new Error('macOS 正式打包需要完整的 Apple API 公证配置。')
  }
  if (present('APPLE_KEYCHAIN_PROFILE')) return
  throw new Error('macOS 正式打包必须配置公证凭据或钥匙串公证配置，不能跳过公证。')
}

/** 开发打包子进程不继承签名或公证身份；不修改调用方环境。
 * @param {NodeJS.ProcessEnv} source
 */
export function developmentEnvironment(source) {
  const env = { ...source }
  for (const key of Object.keys(env)) {
    if (/^(?:WIN_)?CSC_/i.test(key) || /^APPLE_/i.test(key)) delete env[key]
  }
  env.CSC_IDENTITY_AUTO_DISCOVERY = 'false'
  // PR 默认跳过包括临时签名在内的所有签名；此环境已剥离发行身份，打包参数固定使用临时签名。
  env.CSC_FOR_PULL_REQUEST = 'true'
  return env
}

/** 显式区分开发目录、开发安装包与正式发行，拒绝拼错参数导致意外发行。
 * @param {string[]} args
 */
export function packagingMode(args) {
  if (args.length === 0) return { development: false, directory: false }
  if (args.length === 1 && args[0] === '--dir') return { development: true, directory: true }
  if (args.length === 1 && args[0] === '--development') return { development: true, directory: false }
  throw new Error('打包参数仅允许 --dir（开发目录）或 --development（开发安装包）；无参数为正式发行。')
}
