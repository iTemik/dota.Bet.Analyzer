import type { ReactNode } from 'react'
import { formatDate, teamName } from '../format'
import { getCorePlayers, getStandins, hasCore, renderName } from '../roster'
import type { Player, TeamData } from '../types'
import { RowInfoIcon, type RowInfo } from './RowInfo'

// Leaderboard rank per account id (null: not on the leaderboard); only players whose rank was fetched are in it
export type PlayerRanks = Map<number, number | null>

interface InsightsTableProps {
  teams: (TeamData | undefined)[] // team 1 and team 2
  ranks: PlayerRanks[] // player ranks per team
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

// Team insights: one row per insight, Team #1 vs Team #2; add new insights to this list
const insightRows: { label: string; info?: RowInfo; render: (team: TeamData | undefined, ranks: PlayerRanks) => ReactNode }[] = [
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
    label: 'Median Match Duration',
    info: {
      description: 'Median length of the team’s tournament games in the window (minutes:seconds).',
      assumption: 'Not used yet; kept for combined stats later.',
    },
    render: (team) => formatDuration(team?.league_form?.duration_median),
  },
]

/** Team Insights table for two teams; renders live statistics and saved snapshots alike. */
const InsightsTable = ({ teams, ranks }: InsightsTableProps) => (
  <table className="stats-table insights-table">
    <thead>
      <tr>
        <th></th>
        <th>{teamName(teams[0], 0)}</th>
        <th>{teamName(teams[1], 1)}</th>
      </tr>
    </thead>
    <tbody>
      {insightRows.map((row) => (
        <tr key={row.label}>
          <td className="row-label">
            {row.label}
            {row.info && <RowInfoIcon info={row.info} />}
          </td>
          <td>{row.render(teams[0], ranks[0] ?? new Map())}</td>
          <td>{row.render(teams[1], ranks[1] ?? new Map())}</td>
        </tr>
      ))}
    </tbody>
  </table>
)

export default InsightsTable
