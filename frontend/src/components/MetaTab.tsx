import { useEffect, useState, type FormEvent } from 'react'
import { formatDateTime, formatPercent } from '../format'
import { requestJson } from '../predictions'
import { DEFAULT_META_PARAMS, META_PARAMS_KEY } from '../meta'
import type { Meta, MetaParams, ProMetaHero, PubMetaHero } from '../types'

// Saved thresholds over the defaults; keys no longer used (e.g. from an older version) are dropped
const loadParams = (): MetaParams => {
  try {
    const saved = JSON.parse(localStorage.getItem(META_PARAMS_KEY) ?? '{}')
    const keys = Object.keys(DEFAULT_META_PARAMS) as (keyof MetaParams)[]
    return Object.fromEntries(keys.map((k) => [k, saved[k] ?? DEFAULT_META_PARAMS[k]])) as unknown as MetaParams
  } catch {
    return DEFAULT_META_PARAMS
  }
}

const metaUrl = (params: MetaParams): string =>
  `/api/heroes/meta?${new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))}`

/** Icon and name of a hero. */
function HeroCell({ hero }: { hero: { localized_name: string; icon: string } }) {
  return (
    <td className="meta-hero">
      <img src={hero.icon} alt={`${hero.localized_name} icon`} />
      {hero.localized_name}
    </td>
  )
}

function ProMetaTable({ label, heroes }: { label: string; heroes: ProMetaHero[] }) {
  if (!heroes.length) return <p className="prediction-hint">No heroes match these thresholds.</p>
  return (
    <table className="stats-table meta-table" aria-label={label}>
      <thead>
        <tr>
          <th>Hero</th>
          <th>Pick + Ban</th>
          <th>Picks</th>
          <th>Bans</th>
          <th>Win %</th>
        </tr>
      </thead>
      <tbody>
        {heroes.map((h) => (
          <tr key={h.hero_id}>
            <HeroCell hero={h} />
            <td>{formatPercent(h.pick_ban_rate)}</td>
            <td>{h.picks}</td>
            <td>{h.bans}</td>
            <td>{formatPercent(h.win_rate)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function PubMetaTable({ heroes }: { heroes: PubMetaHero[] }) {
  if (!heroes.length) return <p className="prediction-hint">No pub games in this bracket.</p>
  return (
    <table className="stats-table meta-table" aria-label="Pub meta">
      <thead>
        <tr>
          <th>Hero</th>
          <th>Win %</th>
          <th>Pick %</th>
          <th>Picks</th>
        </tr>
      </thead>
      <tbody>
        {heroes.map((h) => (
          <tr key={h.hero_id}>
            <HeroCell hero={h} />
            <td>{formatPercent(h.win_rate)}</td>
            <td>{formatPercent(h.pick_rate)}</td>
            <td>{h.picks}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

const FIELDS: { key: keyof MetaParams; label: string; min: number; max?: number; step?: number }[] = [
  { key: 'pro_min_pick_ban', label: 'Pro meta: Pick + Ban % above', min: 0, max: 100, step: 0.1 },
  { key: 'ultra_min_win', label: 'Ultra meta: Win % above', min: 0, max: 100, step: 0.1 },
  { key: 'ultra_min_picks', label: 'Ultra meta: at least picks', min: 1 },
  { key: 'pub_top', label: 'Pub meta: top Immortal heroes', min: 1, max: 200 },
]

/** Meta tab: pro, ultra and pub meta heroes from OpenDota hero stats, with adjustable thresholds. */
function MetaTab() {
  const [params, setParams] = useState<MetaParams>(loadParams)
  const [form, setForm] = useState<MetaParams>(params)
  const [data, setData] = useState<Meta | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  useEffect(() => {
    let cancelled = false
    requestJson<Meta>(metaUrl(params))
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
      })
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [params])

  const apply = (e: FormEvent) => {
    e.preventDefault()
    localStorage.setItem(META_PARAMS_KEY, JSON.stringify(form))
    setParams(form)
  }
  const reset = () => {
    localStorage.removeItem(META_PARAMS_KEY)
    setForm(DEFAULT_META_PARAMS)
    setParams(DEFAULT_META_PARAMS)
  }
  // New hero stats from OpenDota instead of the backend's 1 hour cache
  const refresh = () => {
    setRefreshing(true)
    requestJson<Meta>(`${metaUrl(params)}&refresh=true`)
      .then((result) => {
        setData(result)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setRefreshing(false))
  }
  const setField = (key: keyof MetaParams, value: string) => setForm({ ...form, [key]: Number(value) })

  return (
    <div className="meta-section">
      <form className="bookmaker-box meta-settings" onSubmit={apply} aria-label="Meta settings">
        <div className="prediction-row">
          {FIELDS.map((f) => (
            <label key={f.key} className="prediction-field">
              <span>{f.label}</span>
              <input
                type="number"
                min={f.min}
                max={f.max}
                step={f.step ?? 1}
                required
                value={form[f.key]}
                onChange={(e) => setField(f.key, e.target.value)}
              />
            </label>
          ))}
        </div>
        <div className="meta-buttons">
          <button type="submit">Apply</button>
          <button type="button" onClick={reset}>
            Defaults
          </button>
        </div>
      </form>

      {error && <div className="error-message">Meta: {error}</div>}
      {!data && !error && <p>Loading meta...</p>}
      {data && (
        <>
          <div className="meta-updated">
            <p className="prediction-hint">
              OpenDota hero stats for about the last 7 days: {data.pro_matches} pro matches. Updated{' '}
              {formatDateTime(data.fetched_at)}.
            </p>
            <button type="button" onClick={refresh} disabled={refreshing}>
              {refreshing ? 'Refreshing...' : 'Refresh data'}
            </button>
          </div>
          <h2>Pro Meta</h2>
          <p className="prediction-hint">
            Pick + Ban rate in pro matches above {data.params.pro_min_pick_ban}%.
          </p>
          <ProMetaTable label="Pro meta" heroes={data.pro_meta} />
          <h2>Ultra Meta</h2>
          <p className="prediction-hint">
            Pro meta heroes with a win rate above {data.params.ultra_min_win}% and at least{' '}
            {data.params.ultra_min_picks} picks.
          </p>
          <ProMetaTable label="Ultra meta" heroes={data.ultra_meta} />
          <h2>Pub Meta</h2>
          <p className="prediction-hint">
            Top {data.params.pub_top} heroes by win rate in {data.pub_bracket} games ({data.pub_matches} matches).
            {data.pub_bracket !== 'Immortal' && ` OpenDota has no Immortal games, so ${data.pub_bracket} is shown.`}
          </p>
          <PubMetaTable heroes={data.pub_meta} />
          <p className="prediction-hint">
            Data:{' '}
            <a href="https://www.opendota.com/heroes/pro" target="_blank" rel="noreferrer">
              OpenDota
            </a>
          </p>
        </>
      )}
    </div>
  )
}

export default MetaTab
