import type { ReactNode } from 'react'
import { COLOR_NEGATIVE, COLOR_POSITIVE, formatDate, formatFixed, formatPercent, teamName } from '../format'
import { ROSTER_STATES, getStandins } from '../roster'
import type { LeagueForm, MatchesSummary, TeamData } from '../types'
import { RowInfoIcon, type RowInfo } from './RowInfo'

type Summary = MatchesSummary | null

interface ComparisonTableProps {
  teams: (TeamData | undefined)[] // team 1 and team 2
  summaries: Summary[] // match summary per team, null while it is loading
  showSummaryRows: boolean // rows that need the summary are hidden until it has arrived
  days: number // window used for the label when the team has no league form
}

// Team Comparison row: `compare` picks the number to colour by, `better` says which side wins
interface CompareRowConfig {
  label: ReactNode
  info?: RowInfo // texts for the row's "i" tooltip
  summary?: boolean // shown only once the match summary has arrived
  compare?: (team: TeamData | undefined, summary: Summary) => number | null
  better?: 'higher' | 'lower'
  threshold?: number // differences up to this are not coloured
  color?: (team: TeamData | undefined) => string // per-team colour, for rows that don't compare
  render: (team: TeamData | undefined, summary: Summary) => ReactNode
}

// Colours for team 1 and team 2: the better value is positive, the other negative
const compareColors = (a: number | null, b: number | null, better: 'higher' | 'lower', threshold = 0): [string, string] => {
  if (a === null || b === null || Math.abs(a - b) <= threshold) return ['transparent', 'transparent']
  const firstWins = better === 'higher' ? a > b : a < b
  return firstWins ? [COLOR_POSITIVE, COLOR_NEGATIVE] : [COLOR_NEGATIVE, COLOR_POSITIVE]
}

// A cell with nothing to show: no value or an empty 0-0 record
const isEmptyCell = (value: ReactNode): boolean => value == null || value === '-' || (typeof value === 'string' && value.startsWith('0-0'))

const CompareRow = ({ row, teams, summaries }: { row: CompareRowConfig; teams: (TeamData | undefined)[]; summaries: Summary[] }) => {
  const cells = teams.map((team, i) => row.render(team, summaries[i]))
  // Rows that are empty for both teams are hidden
  if (cells.every(isEmptyCell)) return null
  let colors: string[] | null = null
  if (row.compare && row.better) {
    colors = compareColors(row.compare(teams[0], summaries[0]), row.compare(teams[1], summaries[1]), row.better, row.threshold)
  } else if (row.color) {
    colors = teams.map(row.color)
  }
  return (
    <tr>
      <td className="row-label">
        {row.label}
        {row.info && <RowInfoIcon info={row.info} />}
      </td>
      {cells.map((cell, i) => (
        <td key={i} style={colors ? { backgroundColor: colors[i] } : undefined}>
          {cell}
        </td>
      ))}
    </tr>
  )
}

const getDeltaBackgroundColor = (delta: number | undefined): string => {
  if (!delta) return 'transparent'
  if (delta < -15) return COLOR_NEGATIVE
  if (delta > 15) return COLOR_POSITIVE
  return 'transparent'
}

const getRosterRank = (team: TeamData | undefined): number | null =>
  team?.roster_source === 'recent_matches' && team.roster_state ? (ROSTER_STATES[team.roster_state]?.rank ?? null) : null

const renderRosterState = (team: TeamData | undefined) => {
  const state = team?.roster_source === 'recent_matches' && team.roster_state ? ROSTER_STATES[team.roster_state] : null
  if (!team || !state) return '-'
  const standins = getStandins(team).length
  const suffix = standins ? ` (${standins} stand-in${standins === 1 ? '' : 's'})` : ''
  return <span title={state.hint}>{`${state.label}${suffix}`}</span>
}

const formatLeagueRecord = (form: LeagueForm | null | undefined): string => {
  if (!form || !form.matches) return '-'
  return `${form.wins}-${form.losses} (${(form.win_percentage ?? 0).toFixed(1)}%)`
}

// Team Comparison: one row per stat, Team #1 vs Team #2; add new stats to this list.
// `info` texts: "Players" means the 5 main roster players (most tournament games in the window).
const compareRows = (teams: (TeamData | undefined)[], days: number): CompareRowConfig[] => [
  { label: 'Team Tag', render: (team) => (team?.tag ? team.tag : '-') },
  { label: 'Team ID', render: (team) => (team?.team_id ? team.team_id : '-') },
  {
    label: 'Rating',
    info: {
      description:
        'OpenDota Elo rating over all tournament games since the team was created (start 1000, up to 32 points per game, never reset). Even teams trade 16 points a game; about 7 straight wins over equal teams add 100.',
      colors: 'Higher is green, lower is red; no colour when they differ by 100 or less.',
      assumption:
        'A 100-point gap means the stronger team is expected to win about 64% of games (about 70% of a Bo3). Beating a team 100 points stronger gives +20.5, losing to it only -11.5.',
    },
    compare: (team) => team?.rating || null,
    better: 'higher',
    threshold: 100,
    render: (team) => (team?.rating ? team.rating : '-'),
  },
  {
    label: 'Last match rating',
    info: {
      description:
        'Elo points from the team’s latest game (one game, not the series): a win gives 0 to +32, a loss 0 to -32. Even teams: ±16; beating a team 100 points stronger: +20.5, losing to it: -11.5.',
      colors: 'Above +15 is green (won against an equal or stronger team), below -15 is red (lost to an equal or weaker team), otherwise no colour.',
      assumption: 'A big gain means a win over a strong team; a small one means an expected win over a weaker team. TBD',
    },
    color: (team) => getDeltaBackgroundColor(team?.delta),
    render: (team) => (team?.delta ? `${team.delta > 0 ? '+' : ''}${team.delta.toFixed(1)}` : '-'),
  },
  {
    label: 'Roster Changes',
    info: {
      description:
        'Stable: only the 5 core players (75%+ of tournament games, else 50%+) played. Stand-ins: a clear core plus others in some games. New team: no clear core.',
      colors: 'Stable beats Stand-ins beats New team.',
      assumption: 'A settled lineup plays better together; stats of a new team say less.',
    },
    compare: getRosterRank,
    better: 'lower',
    render: renderRosterState,
  },
  {
    label: `Tournament matches, last ${teams[0]?.league_form?.days ?? days} days`,
    info: {
      description: 'Team wins-losses (win %) in tournament (league) games over the window.',
      colors: 'Higher win % is green, lower is red.',
      assumption: 'Current form in official games.',
    },
    compare: (team) => team?.league_form?.win_percentage ?? null,
    better: 'higher',
    render: (team) => formatLeagueRecord(team?.league_form),
  },
  {
    label: 'Last Match',
    info: {
      description: 'Date of the latest tournament game played by at least 3 of the 5 players.',
      assumption: 'A long break can mean rust or a lineup change. TBD',
    },
    render: (team) => formatDate(team?.roster_last_match_time ?? team?.league_form?.last_match_time),
  },
  {
    label: 'Rating Matches',
    info: {
      description: 'Ranked pub games played by all players in the window, summed.',
      colors: 'More is green, fewer is red.',
      assumption: 'TBD',
    },
    summary: true,
    compare: (_, s) => s?.rating_matches ?? null,
    better: 'higher',
    render: (_, s) => String(s?.rating_matches ?? '-'),
  },
  {
    label: 'Tournament + scrim matches',
    info: {
      description:
        'Captains Mode lobby games (tournament and scrims; OpenDota can’t tell them apart) played by all players in the window, summed. A game counts once per player.',
      colors: 'More is green, fewer is red.',
      assumption: 'More team practice. TBD',
    },
    summary: true,
    compare: (_, s) => s?.tournament_matches ?? null,
    better: 'higher',
    render: (_, s) => String(s?.tournament_matches ?? '-'),
  },
  {
    label: 'Pub Win %',
    info: {
      description: 'Wins / ranked pub games, over all players’ games.',
      colors: 'Higher is green, lower is red.',
      assumption: 'Individual form of the players. TBD',
    },
    summary: true,
    compare: (_, s) => s?.rating_win_percentage ?? null,
    better: 'higher',
    render: (_, s) => formatPercent(s?.rating_win_percentage),
  },
  {
    label: 'Lobby Win %',
    info: {
      description: 'Wins / Captains Mode lobby games (tournament and scrims), over all players’ games.',
      colors: 'Higher is green, lower is red.',
      assumption: 'Team form, including scrims. TBD',
    },
    summary: true,
    compare: (_, s) => s?.tournament_win_percentage ?? null,
    better: 'higher',
    render: (_, s) => formatPercent(s?.tournament_win_percentage),
  },
  {
    label: 'Average Player Rank',
    info: {
      description: 'Average leaderboard rank of the players who have one; players off the leaderboard are skipped.',
      colors: 'Lower (better) rank is green, higher is red.',
      assumption: 'Individual skill of the players.',
    },
    summary: true,
    compare: (_, s) => s?.avg_rank ?? null,
    better: 'lower',
    render: (_, s) => formatFixed(s?.avg_rank, 0),
  },
  {
    label: 'Low Rank Players',
    info: {
      description: 'Players ranked worse than 150 on the leaderboard ("тысячники": once "not top 1000", ~top 150 after the July 2026 MMR rework).',
      colors: 'Fewer is green, more is red.',
      assumption: 'TBD',
    },
    summary: true,
    compare: (_, s) => s?.bad_rank_players ?? null,
    better: 'lower',
    render: (_, s) => String(s?.bad_rank_players ?? '-'),
  },
  {
    label: 'Other Matches',
    info: {
      description: 'Players’ games that are neither ranked pubs nor Captains Mode lobbies (Turbo, unranked, other modes), summed.',
      assumption: 'TBD',
    },
    summary: true,
    render: (_, s) => String(s?.other_matches ?? '-'),
  },
  {
    label: 'Average Matches Per Player',
    info: {
      description: 'All games in the window divided by the number of players.',
      colors: 'More is green, fewer is red.',
      assumption: 'How much the players play overall. TBD',
    },
    summary: true,
    compare: (_, s) => s?.matches_avg ?? null,
    better: 'higher',
    render: (_, s) => formatFixed(s?.matches_avg, 2),
  },
  {
    label: 'Median Matches Per Player',
    info: {
      description: 'Median number of games per player in the window; less affected by one very active or inactive player.',
      colors: 'More is green, fewer is red.',
      assumption: 'How much a typical player plays. TBD',
    },
    summary: true,
    compare: (_, s) => s?.matches_median ?? null,
    better: 'higher',
    render: (_, s) => formatFixed(s?.matches_median, 2),
  },
]

/** Team Comparison table for two teams; renders live statistics and saved snapshots alike. */
const ComparisonTable = ({ teams, summaries, showSummaryRows, days }: ComparisonTableProps) => (
  <table className="stats-table comparison-table">
    <thead>
      <tr>
        <th></th>
        {[0, 1].map((i) => (
          <th key={i}>
            <div className="team-header">
              <span>{teamName(teams[i], i)}</span>
              {teams[i]?.logo_url && <img src={teams[i].logo_url} alt={`Team ${i + 1} Logo`} className="team-logo" />}
            </div>
          </th>
        ))}
      </tr>
    </thead>
    <tbody>
      {compareRows(teams, days)
        .filter((row) => !row.summary || showSummaryRows)
        .map((row, i) => (
          <CompareRow key={i} row={row} teams={teams} summaries={summaries} />
        ))}
    </tbody>
  </table>
)

export default ComparisonTable
