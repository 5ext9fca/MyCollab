/** 从响应头选择安全的保存默认名；UTF-8 扩展参数优先，普通参数作为回退。 */
/** @param {string | null} disposition */
export function downloadFilename(disposition) {
  const parameters = new Map()
  for (const match of (disposition || '').matchAll(/(?:^|;)\s*(filename\*?)\s*=\s*(?:"((?:\\.|[^"\\])*)"|([^;]*))/gi)) {
    const key = match[1].toLowerCase()
    if (!parameters.has(key)) parameters.set(key, match[2] === undefined ? match[3].trim() : match[2].replace(/\\(.)/g, '$1'))
  }
  let name = parameters.get('filename') || ''
  const extended = /^UTF-8'[^']*'(.*)$/i.exec(parameters.get('filename*') || '')
  if (extended) {
    try { name = decodeURIComponent(extended[1]) || name } catch { /* 使用普通文件名回退。 */ }
  }
  name = name.split(/[\\/]/).at(-1).replace(/[<>:"/\\|?*\x00-\x1f\x7f]/g, '_').replace(/[. ]+$/, '').trim()
  if (!name || name === '.') return '素材文件'
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) name = '_' + name
  return name
}
