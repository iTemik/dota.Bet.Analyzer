// Meta tab settings: thresholds of GET /api/heroes/meta
import type { MetaParams } from './types'

// Same defaults as the backend (backend.meta.MetaParams)
export const DEFAULT_META_PARAMS: MetaParams = {
  pro_min_pick_ban: 40,
  ultra_min_win: 55,
  ultra_min_picks: 5,
  pub_top: 30,
  pub_min_win: 52,
}
// The thresholds are kept in the browser, so they survive a reload
export const META_PARAMS_KEY = 'metaParams'

// Saved thresholds over the defaults; keys no longer used (e.g. from an older version) are dropped
export const loadMetaParams = (): MetaParams => {
  try {
    const saved = JSON.parse(localStorage.getItem(META_PARAMS_KEY) ?? '{}')
    const keys = Object.keys(DEFAULT_META_PARAMS) as (keyof MetaParams)[]
    return Object.fromEntries(keys.map((k) => [k, saved[k] ?? DEFAULT_META_PARAMS[k]])) as unknown as MetaParams
  } catch {
    return DEFAULT_META_PARAMS
  }
}
