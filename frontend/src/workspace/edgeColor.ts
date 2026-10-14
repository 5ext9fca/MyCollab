/**
 * Deterministic dependency-line colour derived from the *source* mission (F5).
 *
 * A dependency line runs `prerequisite -> dependent`, so its "source" is the
 * prerequisite mission (`prerequisite_id`). Every line leaving the same source
 * gets the same stroke and arrow-head colour, and a source is never recoloured
 * as data changes: the colour is a stable function of the source id only. This
 * is a *separate semantic* from `milestoneColor` (the card swatch, which keeps
 * meaning "所属里程碑"): the palette below is deliberately different from the
 * milestone palette so a line colour can never be mistaken for the card's
 * milestone colour, and colour is never the only cue — satisfied/pending is
 * carried by the line style and by words in the relation list.
 *
 * The same source id always maps to the same swatch, across refreshes, filters,
 * selection changes and status changes.
 */

/**
 * Colour for an edge whose visible source endpoint is not loaded. It must not
 * borrow the target's colour: an abnormal edge stays neutral.
 */
export const NEUTRAL_EDGE_COLOR = '#64748b'

/**
 * Vivid, darker tones (Tailwind 700-ish) picked so the strokes stay legible on
 * the light canvas and stay distinct from the milestone card swatches.
 */
export const EDGE_PALETTE = [
  '#0369a1', // 天蓝
  '#b91c1c', // 红
  '#15803d', // 绿
  '#a16207', // 金
  '#6d28d9', // 紫
  '#be185d', // 玫红
  '#0f766e', // 青
  '#4d7c0f', // 橄榄绿
  '#c2410c', // 橙
  '#4338ca', // 靛蓝
]

/**
 * Stable line colour for the mission a dependency edge starts from. A missing
 * id (never expected for a real edge) falls back to the neutral swatch.
 */
export function sourceEdgeColor(missionId: string | null | undefined): string {
  if (!missionId) return NEUTRAL_EDGE_COLOR
  let hash = 0
  for (let index = 0; index < missionId.length; index += 1) {
    hash = (hash * 31 + missionId.charCodeAt(index)) >>> 0
  }
  return EDGE_PALETTE[hash % EDGE_PALETTE.length]
}
