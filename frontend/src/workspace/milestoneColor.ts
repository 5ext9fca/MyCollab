/**
 * Deterministic milestone colour palette for the F5 dependency graph.
 *
 * A mission is never recoloured as data changes: the same milestone id always
 * maps to the same swatch, so the colour is a stable grouping cue between the
 * graph and the milestone legend — it never encodes a status or a permission.
 * Missions without a milestone get a neutral grey.
 */
export const UNASSIGNED_MILESTONE_COLOR = '#94a3b8'

const PALETTE = [
  '#2563eb', // 蓝
  '#16a34a', // 绿
  '#d97706', // 琥珀
  '#dc2626', // 红
  '#7c3aed', // 紫
  '#0891b2', // 青
  '#db2777', // 品红
  '#65a30d', // 黄绿
  '#0d9488', // 蓝绿
  '#9333ea', // 藤紫
]

export function milestoneColor(milestoneId: string | null | undefined): string {
  if (!milestoneId) return UNASSIGNED_MILESTONE_COLOR
  let hash = 0
  for (let index = 0; index < milestoneId.length; index += 1) {
    hash = (hash * 31 + milestoneId.charCodeAt(index)) >>> 0
  }
  return PALETTE[hash % PALETTE.length]
}

export function milestoneLabel(name: string | null | undefined): string {
  return name || '未归属里程碑'
}
