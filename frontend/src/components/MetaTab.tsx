import { Fragment, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { formatDateTime, formatPercent, formatShortCount } from '../format'
import { requestJson } from '../predictions'
import { DEFAULT_META_PARAMS, META_PARAMS_KEY } from '../meta'
import type { Meta, MetaHero, MetaKind, MetaParams } from '../types'

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

const META_RANK: Record<MetaKind, number> = { ultra: 0, pro: 1, pub: 2 }
const isUltra = (h: MetaHero) => h.meta.includes('ultra')

// Meta tags of a hero: an ultra meta hero is pro meta too, so it shows Ultra instead of Pro
const metaTags = (h: MetaHero): MetaKind[] => h.meta.filter((m) => !(m === 'pro' && isUltra(h)))

const metaRule = (kind: MetaKind, p: MetaParams): string =>
  ({
    ultra: `Ultra meta: pro meta with a win rate above ${p.ultra_min_win}% and at least ${p.ultra_min_picks} picks`,
    pro: `Pro meta: Pick + Ban rate in pro matches above ${p.pro_min_pick_ban}%`,
    pub: `Pub meta: of the ${p.pub_top} most picked Immortal, Divine and Ancient heroes, a win rate above ${p.pub_min_win}%`,
  })[kind]

const META_LABEL: Record<MetaKind, string> = { ultra: '★ Ultra', pro: 'Pro', pub: 'Pub' }

const count = (n: number) => n.toLocaleString('en-US')

/** Number with a bar under it, like OpenDota's hero tables; the tooltip shows the numbers behind it. */
function BarCell({
  text,
  value,
  max,
  title,
  win,
}: {
  text: string
  value: number | null
  max: number
  title: string
  win?: boolean
}) {
  const width = value !== null && max > 0 ? Math.min(100, (100 * value) / max) : 0
  const tone = win && value !== null ? (value >= 50 ? 'good' : 'bad') : 'plain'
  return (
    <td className="meta-bar-cell" title={title}>
      <span>{text}</span>
      <span className="meta-bar">
        <span className={`meta-bar-fill ${tone}`} style={{ width: `${width}%` }} />
      </span>
    </td>
  )
}

interface Column {
  key: string
  label: string
  title: string // header tooltip
  value: (h: MetaHero) => number | string | null
  firstDir: 'asc' | 'desc' // direction of the first click
  cell: (h: MetaHero, data: Meta, max: number) => ReactNode
  bar?: (h: MetaHero) => number | null // value the bar is scaled by (to the column's highest)
}

// One object per column: header, sort value and cell
const COLUMNS: Column[] = [
  {
    key: 'hero',
    label: 'Hero',
    title: 'Hero name',
    value: (h) => h.localized_name,
    firstDir: 'asc',
    cell: (h) => (
      <td className="meta-hero">
        <img src={h.icon} alt={`${h.localized_name} icon`} />
        {h.localized_name}
      </td>
    ),
  },
  {
    key: 'meta',
    label: 'Meta',
    title: 'Ultra, Pro or Pub meta (ultra first)',
    value: (h) => META_RANK[h.meta[0]],
    firstDir: 'asc',
    cell: (h, data) => (
      <td className="meta-kind">
        {metaTags(h).map((m) => (
          <span key={m} className={`meta-tag meta-tag-${m}`} title={metaRule(m, data.params)}>
            {META_LABEL[m]}
          </span>
        ))}
      </td>
    ),
  },
  {
    key: 'pro_pick_ban_rate',
    label: 'Pro P+B',
    title: 'Pick + Ban rate in pro matches',
    value: (h) => h.pro_pick_ban_rate,
    bar: (h) => h.pro_pick_ban_rate,
    firstDir: 'desc',
    cell: (h, data, max) => (
      <BarCell
        text={formatPercent(h.pro_pick_ban_rate)}
        value={h.pro_pick_ban_rate}
        max={max}
        title={`${count(h.pro_picks)} picks + ${count(h.pro_bans)} bans in ${count(data.pro_matches)} pro matches`}
      />
    ),
  },
  {
    key: 'pro_win_rate',
    label: 'Pro Win',
    title: 'Win rate in pro matches',
    value: (h) => h.pro_win_rate,
    bar: (h) => h.pro_win_rate,
    firstDir: 'desc',
    cell: (h, _data, max) => (
      <BarCell
        text={formatPercent(h.pro_win_rate)}
        value={h.pro_win_rate}
        max={max}
        title={`${count(h.pro_wins)} wins in ${count(h.pro_picks)} pro picks`}
        win
      />
    ),
  },
  {
    key: 'pub_picks',
    label: 'Pub Picks',
    title: 'Picks in Immortal, Divine and Ancient matches',
    value: (h) => h.pub_picks,
    bar: (h) => h.pub_picks,
    firstDir: 'desc',
    cell: (h, data, max) => (
      <BarCell
        text={formatShortCount(h.pub_picks)}
        value={h.pub_picks}
        max={max}
        title={`${count(h.pub_picks)} picks, ${formatPercent(h.pub_pick_rate)} of ${count(data.pub_matches)} Imm/Div/Anc matches`}
      />
    ),
  },
  {
    key: 'pub_win_rate',
    label: 'Pub Win',
    title: 'Win rate in Immortal, Divine and Ancient matches',
    value: (h) => h.pub_win_rate,
    bar: (h) => h.pub_win_rate,
    firstDir: 'desc',
    cell: (h, _data, max) => (
      <BarCell
        text={formatPercent(h.pub_win_rate)}
        value={h.pub_win_rate}
        max={max}
        title={`${count(h.pub_wins)} wins in ${count(h.pub_picks)} Imm/Div/Anc picks`}
        win
      />
    ),
  },
]

interface Sort {
  key: string
  dir: 'asc' | 'desc'
}
// The backend order: ultra, pro, then pub only, each by pro Pick + Ban
const DEFAULT_SORT: Sort = { key: 'meta', dir: 'asc' }

// Sorted copy; empty values last, ties keep the backend order
const sortHeroes = (heroes: MetaHero[], sort: Sort): MetaHero[] => {
  const column = COLUMNS.find((c) => c.key === sort.key) ?? COLUMNS[1]
  const sign = sort.dir === 'asc' ? 1 : -1
  return heroes
    .map((h, i) => ({ h, i, v: column.value(h) }))
    .sort((a, b) => {
      if (a.v === b.v) return a.i - b.i
      if (a.v === null) return 1
      if (b.v === null) return -1
      return sign * (typeof a.v === 'string' ? a.v.localeCompare(String(b.v)) : a.v - (b.v as number))
    })
    .map(({ h }) => h)
}

/** All meta heroes in one compact table, sorted by clicking a column header like on OpenDota. */
function MetaTable({ data }: { data: Meta }) {
  const [sort, setSort] = useState<Sort>(DEFAULT_SORT)
  if (!data.heroes.length) return <p className="prediction-hint">No heroes match these thresholds.</p>

  const clickHeader = (c: Column) =>
    setSort(
      sort.key === c.key ? { key: c.key, dir: sort.dir === 'asc' ? 'desc' : 'asc' } : { key: c.key, dir: c.firstDir },
    )
  const maxOf = (c: Column) => Math.max(0, ...data.heroes.map((h) => c.bar?.(h) ?? 0))
  const maxes = COLUMNS.map(maxOf)

  return (
    <table className="stats-table meta-table" aria-label="Meta heroes">
      <thead>
        <tr>
          {COLUMNS.map((c) => {
            const active = sort.key === c.key
            return (
              <th
                key={c.key}
                title={c.title}
                aria-sort={active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
              >
                <button type="button" className="meta-sort" onClick={() => clickHeader(c)}>
                  {c.label}
                  <span className="meta-sort-arrow" aria-hidden="true">
                    {active ? (sort.dir === 'asc' ? '▲' : '▼') : ''}
                  </span>
                </button>
              </th>
            )
          })}
        </tr>
      </thead>
      <tbody>
        {sortHeroes(data.heroes, sort).map((h) => (
          <tr key={h.hero_id} className={isUltra(h) ? 'meta-ultra' : undefined}>
            {COLUMNS.map((c, i) => (
              <Fragment key={c.key}>{c.cell(h, data, maxes[i])}</Fragment>
            ))}
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
  { key: 'pub_top', label: 'Pub meta: most picked heroes', min: 1, max: 200 },
  { key: 'pub_min_win', label: 'Pub meta: Win % above', min: 0, max: 100, step: 0.1 },
]

/** Meta tab: pro, ultra and pub meta heroes from OpenDota hero stats in one table, thresholds below it. */
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
  // New hero stats from OpenDota instead of the backend's cache
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
      {error && <div className="error-message">Meta: {error}</div>}
      {!data && !error && <p>Loading meta...</p>}
      {data && (
        <>
          <p className="prediction-hint meta-updated">
            OpenDota hero stats for about the last 7 days: {count(data.pro_matches)} pro matches,{' '}
            {formatShortCount(data.pub_matches)} Immortal, Divine and Ancient matches. Updated{' '}
            {formatDateTime(data.fetched_at)}. Click a column to sort, hover a number for details.
          </p>
          <MetaTable data={data} />
        </>
      )}

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
          <button type="submit" className="check-btn">
            Apply
          </button>
          <button type="button" className="check-btn" onClick={reset}>
            Defaults
          </button>
          <button type="button" className="check-btn" onClick={refresh} disabled={refreshing}>
            {refreshing ? 'Refreshing...' : 'Refresh data'}
          </button>
        </div>
      </form>
      <p className="prediction-hint meta-source">
        Data:{' '}
        <a href="https://www.opendota.com/heroes/pro" target="_blank" rel="noreferrer">
          OpenDota
        </a>
      </p>
    </div>
  )
}

export default MetaTab
