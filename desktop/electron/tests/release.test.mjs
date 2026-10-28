import test from 'node:test'
import assert from 'node:assert/strict'
import { requireNotarization, developmentEnvironment } from '../release.mjs'

test('正式 macOS 公证配置缺失或仅有团队信息时拒绝打包', () => {
  for (const env of [{}, { APPLE_TEAM_ID: 'team' }, { APPLE_KEYCHAIN_PROFILE: ' ' }]) {
    assert.throws(() => requireNotarization(env), /不能跳过公证/)
  }
})
test('支持账户、API 或钥匙串三种完整公证配置', () => {
  for (const env of [
    { APPLE_ID: 'account', APPLE_APP_SPECIFIC_PASSWORD: 'secret', APPLE_TEAM_ID: 'team' },
    { APPLE_API_KEY: '/key.p8', APPLE_API_KEY_ID: 'key', APPLE_API_ISSUER: 'issuer' },
    { APPLE_KEYCHAIN_PROFILE: 'profile' },
  ]) assert.doesNotThrow(() => requireNotarization(env))
})
test('残缺高优先级配置不能借低优先级配置绕过检查且错误不泄露密钥', () => {
  for (const env of [
    { APPLE_ID: 'private-account', APPLE_KEYCHAIN_PROFILE: 'profile' },
    { APPLE_APP_SPECIFIC_PASSWORD: 'private-password', APPLE_KEYCHAIN_PROFILE: 'profile' },
    { APPLE_API_KEY: 'private-key', APPLE_KEYCHAIN_PROFILE: 'profile' },
    { APPLE_API_KEY: 'private-key', APPLE_API_KEY_ID: 'key', APPLE_API_ISSUER: ' ' },
  ]) assert.throws(() => requireNotarization(env), error => !String(error).includes('private-'))
})


test('开发包剥离账户、证书和钥匙串身份，保留运行环境且不修改原环境', () => {
  const source = { PATH: '/bin', TEMP: '/tmp', CSC_LINK: 'certificate', CSC_KEY_PASSWORD: 'password',
    WIN_CSC_LINK: 'windows-certificate', APPLE_KEYCHAIN_PROFILE: 'profile', APPLE_ID: 'account',
    APPLE_APP_SPECIFIC_PASSWORD: 'apple-password', APPLE_API_KEY: 'api-key',
    csc_name: 'windows-case-insensitive-identity', CSC_IDENTITY_AUTO_DISCOVERY: 'true' }
  const original = { ...source }
  assert.deepEqual(developmentEnvironment(source), { PATH: '/bin', TEMP: '/tmp', CSC_IDENTITY_AUTO_DISCOVERY: 'false' })
  assert.deepEqual(source, original)
})
