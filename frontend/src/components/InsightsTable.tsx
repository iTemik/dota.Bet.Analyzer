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

// "Since Oct 5: 3+ meta heroes in 14 of 19 games (74%)"
const formatMetaWindow = (window: TeamMetaWindow, minHeroes: number): string =>
  `Since ${formatDate(window.start)}: ${minHeroes}+ meta heroes in ${window.meta_games} of ${window.games} games` +
  (window.games ? ` (${formatPct(window.meta_games_pct)})` : '')

const renderMetaState = (meta: TeamMeta | null | undefined) => {
  if (!meta) return '-'
  if (meta.error) return <span className="field-error">Unavailable: {meta.error}</span>
  if (!meta.state || !meta.deep || !meta.recent) return '-'
  const minHeroes = Number(meta.params?.meta_min_heroes ?? 3)
  return (
    <div className="team-meta">
      <div className="team-meta-state">{META_STATE_LABELS[meta.state]}</div>
      {meta.deep.games > 0 && (
        <div>
          {formatPct(meta.deep.meta_picks_pct)} meta picks (pro avg {formatPct(meta.pro_meta_picks_pct)})
        </div>
      )}
      <div>{formatMetaWindow(meta.recent, minHeroes)}</div>
      {meta.deep.start !== meta.recent.start && <div>{formatMetaWindow(meta.deep, minHeroes)}</div>}
      {meta.patch && <div className="roster-source">patch {meta.patch}</div>}
    </div>
  )
}

// Tags of a picked meta hero: ultra; 60d (picked only before the recent window) or pub (never picked by the team,
// known from a core player's league + pub practice); a hero picked in the recent window has no window tag
const metaHeroTags = (hero: TeamMetaHero, deepDays: number): { label: string; title: string; ultra?: boolean }[] => {
  const tags: { label: string; title: string; ultra?: boolean }[] = []
  if (hero.ultra) tags.push({ label: 'ultra', title: 'Ultra meta hero', ultra: true })
  if (!hero.games) tags.push({ label: 'pub', title: 'Not picked by the team; core players practise it in league or pub games' })
  else if (!hero.recent_games) tags.push({ label: `${deepDays}d`, title: `Picked only in the last ${deepDays} days, not in the recent window` })
  return tags
}

const renderMetaHeroes = (meta: TeamMeta | null | undefined) => {
  if (!meta?.heroes) return '-'
  if (!meta.heroes.length) return 'None'
  const deepDays = Number(meta.params?.deep_days ?? 60)
  return (
    <div className="team-meta-heroes">
      {meta.heroes.map((hero) => (
        <div key={hero.hero_id} className="team-meta-hero">
          <img src={hero.icon} alt={`${hero.localized_name} icon`} />
          {hero.localized_name}
          {hero.games > 0 && ` · ${hero.games} games`}
          {hero.practice_players > 0 && (
            <span title="Core players with 3+ league games, or 5+ league and pub games, on this hero in the last 60 days">
              {` · practised by ${hero.practice_players}`}
            </span>
          )}
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
        'Does the team play the meta heroes of the Meta tab (pro and ultra, with your Meta tab thresholds)? A meta game has 3+ meta heroes in the team draft (stand-ins included). Actively plays: 65%+ meta games among 20+ games of the recent window; Tries: the same only in the last 60 days; Players know meta: 3+ core players practise a meta hero (3+ league or 5+ league and pub games in 60 days); Doesn’t play meta: 20+ games but none of that; No info: too few games. Windows start no earlier than the latest patch.',
      assumption: 'A team that plays the meta is better prepared. Thresholds to be tuned after testing.',
    },
    render: (_team, _ranks, meta) => renderMetaState(meta),
  },
  {
    label: 'Meta Heroes',
    needsMeta: true,
    info: {
      description:
        'Meta heroes the team picked in 3+ tournament games (most games first) or a core player practises. "practised by N" = N core players with 3+ league or 5+ league and pub games on the hero in 60 days. Tags: ultra = ultra meta; 60d = picked only before the recent window; pub = never picked by the team, known from a player’s league or pub games; no tag = picked in the recent window.',
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
