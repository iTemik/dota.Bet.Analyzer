import type { ReactNode } from 'react'
import { COLOR_NEGATIVE, COLOR_POSITIVE, formatDate, formatFixed, formatPercent, teamName } from '../format'
import { ROSTER_STATES, getStandins } from '../roster'
import type { LeagueForm, MatchesSummary, TeamData } from '../types'

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
  title?: string
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
      <td className="row-label" title={row.title}>
        {row.label}
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

// Team Comparison: one row per stat, Team #1 vs Team #2; add new stats to this list
const compareRows = (teams: (TeamData | undefined)[], days: number): CompareRowConfig[] => [
  { label: 'Team Tag', render: (team) => (team?.tag ? team.tag : '-') },
  { label: 'Team ID', render: (team) => (team?.team_id ? team.team_id : '-') },
  {
    label: 'Rating',
    compare: (team) => team?.rating || null,
    better: 'higher',
    threshold: 100,
    render: (team) => (team?.rating ? team.rating : '-'),
  },
  {
    label: 'Last match rating',
    color: (team) => getDeltaBackgroundColor(team?.delta),
    render: (team) => (team?.delta ? `${team.delta > 0 ? '+' : ''}${team.delta.toFixed(1)}` : '-'),
  },
  { label: 'Roster Changes', compare: getRosterRank, better: 'lower', render: renderRosterState },
  {
    label: `Tournament matches, last ${teams[0]?.league_form?.days ?? days} days`,
    title: 'Wins and losses in tournament matches over the stats window',
    compare: (team) => team?.league_form?.win_percentage ?? null,
    better: 'higher',
    render: (team) => formatLeagueRecord(team?.league_form),
  },
  {
    label: 'Last Match',
    title: 'Latest tournament game played by at least 3 of the 5 players',
    render: (team) => formatDate(team?.roster_last_match_time ?? team?.league_form?.last_match_time),
  },
  {
    label: 'Rating Matches',
    summary: true,
    compare: (_, s) => s?.rating_matches ?? null,
    better: 'higher',
    render: (_, s) => String(s?.rating_matches ?? '-'),
  },
  {
    label: 'Tournament + scrim matches',
    summary: true,
    compare: (_, s) => s?.tournament_matches ?? null,
    better: 'higher',
    render: (_, s) => String(s?.tournament_matches ?? '-'),
  },
  {
    label: 'Pub Win %',
    summary: true,
    compare: (_, s) => s?.rating_win_percentage ?? null,
    better: 'higher',
    render: (_, s) => formatPercent(s?.rating_win_percentage),
  },
  {
    label: 'Lobby Win %',
    summary: true,
    compare: (_, s) => s?.tournament_win_percentage ?? null,
    better: 'higher',
    render: (_, s) => formatPercent(s?.tournament_win_percentage),
  },
  {
    label: 'Average Player Rank',
    summary: true,
    compare: (_, s) => s?.avg_rank ?? null,
    better: 'lower',
    render: (_, s) => formatFixed(s?.avg_rank, 0),
  },
  {
    label: (
      <>
        Low Rank Players
        <br />
        (тысячники в команде)
      </>
    ),
    summary: true,
    compare: (_, s) => s?.bad_rank_players ?? null,
    better: 'lower',
    render: (_, s) => String(s?.bad_rank_players ?? '-'),
  },
  { label: 'Other Matches', summary: true, render: (_, s) => String(s?.other_matches ?? '-') },
  {
    label: 'Average Matches Per Player',
    summary: true,
    compare: (_, s) => s?.matches_avg ?? null,
    better: 'higher',
    render: (_, s) => formatFixed(s?.matches_avg, 2),
  },
  {
    label: 'Median Matches Per Player',
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
