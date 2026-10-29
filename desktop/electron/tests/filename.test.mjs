import { test } from 'node:test'
import assert from 'node:assert/strict'
import { downloadFilename } from '../filename.mjs'

test('普通文件名、带分号的引号参数与 UTF-8 扩展名均保留', () => {
  assert.equal(downloadFilename('attachment; filename="acceptance.txt"'), 'acceptance.txt')
  assert.equal(downloadFilename('inline; filename=photo.png'), 'photo.png')
  assert.equal(downloadFilename('attachment; filename="part;one.txt"'), 'part;one.txt')
  assert.equal(downloadFilename("attachment; filename=fallback.txt; filename*=UTF-8'zh'%E9%AA%8C%E6%94%B6.txt"), '验收.txt')
  assert.equal(downloadFilename("attachment; filename*=UTF-8''%ZZ; filename=valid.txt"), 'valid.txt')
})

test('保存默认名不包含路径、控制字符或 Windows 保留设备名', () => {
  assert.equal(downloadFilename('attachment; filename="../../photo.png"'), 'photo.png')
  assert.equal(downloadFilename("attachment; filename*=UTF-8''C%3A%5Ctemp%5Cphoto.png"), 'photo.png')
  assert.equal(downloadFilename('attachment; filename="CON.txt"'), '_CON.txt')
  assert.equal(downloadFilename('attachment; filename=".."'), '素材文件')
  assert.equal(downloadFilename(null), '素材文件')
  assert.equal(downloadFilename("attachment; filename*=UTF-8''a%00b.txt"), 'a_b.txt')
})
