import type { ReactNode } from 'react'
import { formatDate, teamName } from '../format'
import { getCorePlayers, getStandins, hasCore, renderName } from '../roster'
import type { Player, TeamData, TeamMeta, TeamMetaHero, TeamMetaState, TeamMetaWindow } from '../types'
import { RowInfoIcon, type RowInfo } from './RowInfo'

// Leaderboard rank per account id (null: not on the leaderboard); only players whose rank was fetched are in it
export type PlayerRanks = Map<number, number | null>

interface InsightsTableProps {
  teams: (TeamData | undefined)[] // team 1 and team 2
  ranks: PlayerRanks[] // player ranks per team
  metas?: (TeamMeta | null | undefined)[] // team meta per team from the task results; without it the meta rows are hidden
}

// " · games: N · rank: R" after a player's name; "N of total" when the player missed some of the team's
// tournament games in the window; rank only for players whose rank was fetched ("-" when not on the leaderboard)
const formatPlayerStats = (player: Player, team: TeamData, ranks: PlayerRanks): string => {
  const total = team.roster_games
  let text = ''
  if (player.games) text += ` · games: ${player.games}${total && player.games < total ? ` of ${total}` : ''}`
  if (ranks.has(player.id)) text += ` · rank: ${ranks.get(player.id) ?? '-'}`
  return text
}

const formatDuration = (seconds: number | null | undefined): string => {
  if (!seconds) return '-'
  const rounded = Math.round(seconds)
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`
}

const formatRadiantRecord = (team: TeamData | undefined): string => {
  const form = team?.league_form
  if (!form?.radiant_matches) return '-'
  const wins = form.radiant_wins ?? 0
  return `${wins}-${form.radiant_matches - wins} (${(form.radiant_win_percentage ?? 0).toFixed(1)}%)`
}

const renderPlayers = (players: Player[], team: TeamData, ranks: PlayerRanks) =>
  players.map((p) => (
    <div key={p.id}>
      {renderName(p)}
      {formatPlayerStats(p, team, ranks)}
    </div>
  ))

const renderCorePlayers = (team: TeamData | undefined, ranks: PlayerRanks) => {
  if (!team || !team.players?.length) return '-'
  const clearCore = team.roster_source === 'recent_matches' && hasCore(team)
  return (
    <div className="roster">
      {renderPlayers(getCorePlayers(team), team, ranks)}
      {team.roster_source !== 'recent_matches' && <div className="roster-source">unconfirmed: no recent tournament match</div>}
      {team.roster_source === 'recent_matches' && !clearCore && <div className="roster-source">no clear core: players rotate</div>}
    </div>
  )
}

const renderPlayedList = (players: Player[], team: TeamData, ranks: PlayerRanks) => {
  if (!players.length) return 'None'
  return <div className="roster">{renderPlayers(players, team, ranks)}</div>
}

const renderStandinPlayers = (team: TeamData | undefined, ranks: PlayerRanks) =>
  team?.roster_source === 'recent_matches' ? renderPlayedList(getStandins(team), team, ranks) : '-'

// Other players: listed on the team by OpenDota but without league games in the window
const renderOtherPlayers = (team: TeamData | undefined, ranks: PlayerRanks) => {
  if (!team) return '-'
  const others = team.other_players ?? []
  return renderPlayedList(team.roster_source === 'recent_matches' ? others.filter((p) => p.games === 0) : others, team, ranks)
}

const META_STATE_LABELS: Record<TeamMetaState, string> = {
  actively: 'Actively plays meta',
  tries: 'Tries to play meta',
  players_know: 'Players know meta',
  doesnt_play: "Doesn't play meta",
  no_info: 'No info',
}

const formatPct = (value: number | null | undefined): string => (value == null ? '-' : `${Math.round(value)}%`)

// "Since 10/15/2026: 3+ meta heroes in 16 of 28 games (57%)", for the tooltip
const describeMetaGames = (window: TeamMetaWindow, minHeroes: number): string =>
  `Since ${formatDate(window.start)}: ${minHeroes}+ meta heroes in ${window.meta_games} of ${window.games} games` +
  (window.games ? ` (${formatPct(window.meta_games_pct)})` : '')

// State and one number: the share of games with 3+ meta heroes in the window the state comes from (the recent window
// for "Actively plays meta", else the deeper one), green when it reaches the rule's threshold; details in the tooltip
const renderMetaState = (meta: TeamMeta | null | undefined) => {
  if (!meta) return '-'
  if (meta.error) return <span className="field-error">Unavailable: {meta.error}</span>
  if (!meta.state || !meta.deep || !meta.recent) return '-'
  const minHeroes = Number(meta.params?.meta_min_heroes ?? 3)
  const minPct = Number(meta.params?.meta_min_games_pct ?? 65)
  const minGames = Number(meta.params?.meta_min_games ?? 20)
  const window = meta.state === 'actively' ? meta.recent : meta.deep
  // Both windows start at the latest patch when it is newer than the recent window: then one is enough
  const windows = meta.deep.start === meta.recent.start ? [meta.deep] : [meta.recent, meta.deep]
  const tooltip = [
    `Share of the team's games with ${minHeroes}+ meta heroes in the draft (plays meta: ${minPct}%+ of at least ${minGames} games).`,
    ...windows.map((w) => describeMetaGames(w, minHeroes)),
    `Meta heroes are ${formatPct(meta.deep.meta_picks_pct)} of all the team's picks (all pro games: ${formatPct(meta.pro_meta_picks_pct)}).`,
  ].join('\n')
  return (
    <div className="team-meta" title={tooltip}>
      <span className="team-meta-state">{META_STATE_LABELS[meta.state]}</span>
      {window.games > 0 && (
        <>
          {' · '}
          <span className={(window.meta_games_pct ?? 0) >= minPct ? 'team-meta-pos' : 'team-meta-neg'}>
            {formatPct(window.meta_games_pct)}
          </span>
        </>
      )}
    </div>
  )
}

// Ultra tag, and a 60d tag for a hero picked only before the recent window (no tag: picked in the recent window)
const metaHeroTags = (hero: TeamMetaHero, deepDays: number): { label: string; title: string; ultra?: boolean }[] => {
  const tags: { label: string; title: string; ultra?: boolean }[] = []
  if (hero.ultra) tags.push({ label: 'ultra', title: 'Ultra meta hero', ultra: true })
  if (!hero.recent_games) tags.push({ label: `${deepDays}d`, title: `Picked only in the last ${deepDays} days, not in the recent window` })
  return tags
}

// Tooltip of a meta hero: picks per window and how many core players practise it
const describeMetaHero = (hero: TeamMetaHero, deepDays: number): string =>
  `${hero.games} games in ${deepDays} days, ${hero.recent_games} in the recent window. ` +
  `Practised by ${hero.practice_players} core player${hero.practice_players === 1 ? '' : 's'} ` +
  `(3+ league games, or 5+ league and pub games, in ${deepDays} days).`

const renderMetaHeroes = (meta: TeamMeta | null | undefined) => {
  if (!meta?.heroes) return '-'
  const deepDays = Number(meta.params?.deep_days ?? 60)
  const minGames = Number(meta.params?.meta_hero_min_games ?? 3)
  // The meta list changes size with the thresholds and the week, so the count is out of its current size
  const total =
    meta.meta_heroes_total != null && (
      <div className="team-meta-count" title={`Meta heroes the team picked ${minGames}+ times in ${deepDays} days, out of all current meta heroes`}>
        {meta.heroes.length} of {meta.meta_heroes_total} meta heroes
      </div>
    )
  if (!meta.heroes.length) return total || 'None'
  const heroes = [...meta.heroes].sort((a, b) => a.localized_name.localeCompare(b.localized_name))
  return (
    <div className="team-meta-heroes">
      {total}
      {heroes.map((hero) => (
        <div key={hero.hero_id} className="team-meta-hero">
          <img src={hero.icon} alt={`${hero.localized_name} icon`} />
          {hero.localized_name} ·{' '}
          <span className="team-meta-games" title={describeMetaHero(hero, deepDays)}>
            {hero.games}
          </span>
          {metaHeroTags(hero, deepDays).map((tag) => (
            <span key={tag.label} className={`meta-tag team-meta-tag${tag.ultra ? ' meta-tag-ultra' : ''}`} title={tag.title}>
              {tag.label}
            </span>
          ))}
        </div>
      ))}
    </div>
  )
}

type InsightRow = {
  label: string
  info?: RowInfo
  needsMeta?: boolean // shown only with team meta (live Compare, not saved snapshots)
  render: (team: TeamData | undefined, ranks: PlayerRanks, meta: TeamMeta | null | undefined) => ReactNode
}

// Team insights: one row per insight, Team #1 vs Team #2; add new insights to this list
const insightRows: InsightRow[] = [
  { label: 'Team Tag', render: (team) => team?.tag || '-' },
  { label: 'Team ID', render: (team) => team?.team_id || '-' },
  {
    label: 'Core Players',
    info: {
      description:
        'The 5 players with 75%+ of the team’s tournament games in the window (50%+ if none). "games: N of total" when a player missed some; "rank" is the leaderboard rank.',
      assumption: 'The main stats come from these players. TBD',
    },
    render: renderCorePlayers,
  },
  {
    label: 'Stand-ins',
    info: {
      description: 'Players outside the core who played tournament games for the team in the window.',
      assumption: 'Stand-ins weaken teamplay. TBD',
    },
    render: renderStandinPlayers,
  },
  {
    label: 'Other Players',
    info: {
      description: 'Listed on the team by OpenDota but without tournament games in the window (backups, former players).',
      assumption:
        'Usually the coach and backup players. A good sign: the team discusses strategies and has a ready replacement.',
    },
    render: renderOtherPlayers,
  },
  {
    label: 'Last Tournament Match with core players',
    info: {
      description: 'Date of the team’s latest tournament game and how many players outside the core played it.',
      assumption: 'Players outside the core in the latest game can mean a roster problem. TBD',
    },
    render: (team) => {
      if (team?.roster_source !== 'recent_matches' || !team.latest_match_time) return '-'
      // Mention players outside the core only when there were any
      const outside = team.latest_match_standins ?? 0
      const suffix = outside ? `, ${outside} player${outside === 1 ? '' : 's'} outside the core` : ''
      return `${formatDate(team.latest_match_time)}${suffix}`
    },
  },
  {
    label: 'Radiant Win %',
    info: {
      description: 'Team wins-losses (win %) in tournament games of the window played on the Radiant side.',
      assumption: 'TBD',
    },
    render: formatRadiantRecord,
  },
  {
    label: 'Median Match Duration',
    info: {
      description: 'Median length of the team’s tournament games in the window (minutes:seconds).',
      assumption: 'Not used yet; kept for combined stats later.',
    },
    render: (team) => formatDuration(team?.league_form?.duration_median),
  },
  {
    label: 'Meta',
    needsMeta: true,
    info: {
      description:
        'Does the team play the meta heroes of the Meta tab (pro and ultra, with your Meta tab thresholds)? A meta game has 3+ meta heroes in the team draft (stand-ins included). Actively plays: 65%+ meta games among 20+ games of the recent window; Tries: the same only in the last 60 days; Players know meta: 3+ core players practise a meta hero (3+ league or 5+ league and pub games in 60 days); Doesn’t play meta: 20+ games but none of that; No info: too few games. Windows start no earlier than the latest patch. The number: share of games with 3+ meta heroes in the window the state comes from, green at 65%+; hover it for both windows and the share of meta picks.',
      assumption: 'A team that plays the meta is better prepared. Thresholds to be tuned after testing.',
    },
    render: (_team, _ranks, meta) => renderMetaState(meta),
  },
  {
    label: 'Meta Heroes',
    needsMeta: true,
    info: {
      description:
        'How many of the current meta heroes the team picked in 3+ tournament games of the last 60 days, then those heroes by name with the number of games. Tags: ultra = ultra meta; 60d = picked only before the recent window (no tag: picked in the recent window). Hover the number of games for the games per window and how many core players practise it.',
      assumption: 'TBD',
    },
    render: (_team, _ranks, meta) => renderMetaHeroes(meta),
  },
]

/** Team Insights table for two teams; renders live statistics and saved snapshots alike. */
const InsightsTable = ({ teams, ranks, metas }: InsightsTableProps) => (
  <table className="stats-table insights-table">
    <thead>
      <tr>
        <th></th>
        <th>{teamName(teams[0], 0)}</th>
        <th>{teamName(teams[1], 1)}</th>
      </tr>
    </thead>
    <tbody>
      {insightRows.filter((row) => metas || !row.needsMeta).map((row) => (
        <tr key={row.label}>
          <td className="row-label">
            {row.label}
            {row.info && <RowInfoIcon info={row.info} />}
          </td>
          <td>{row.render(teams[0], ranks[0] ?? new Map(), metas?.[0])}</td>
          <td>{row.render(teams[1], ranks[1] ?? new Map(), metas?.[1])}</td>
        </tr>
      ))}
    </tbody>
  </table>
)

export default InsightsTable
