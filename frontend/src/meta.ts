// Meta tab settings: thresholds of GET /api/heroes/meta
import type { MetaParams } from './types'

// Same defaults as the backend (backend.meta.MetaParams)
export const DEFAULT_META_PARAMS: MetaParams = {
  pro_min_pick_ban: 30,
  ultra_min_win: 55,
  ultra_min_picks: 5,
  pub_top: 30,
  pub_min_win: 52,
}
// The thresholds are kept in the browser, so they survive a reload
export const META_PARAMS_KEY = 'metaParams'
