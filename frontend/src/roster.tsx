import type { Player, RosterState, TeamData } from './types'

// Roster state, from best to worst; stand-ins are players outside the core (below 75%, or 50%, of the games)
export const ROSTER_STATES: Record<RosterState, { rank: number; label: string; hint: string }> = {
  stable: { rank: 0, label: 'Stable', hint: 'Only the core players played' },
  standins: { rank: 1, label: 'Stand-ins', hint: 'A clear core of 5 players, plus stand-ins in some games' },
  new_team: { rank: 2, label: 'New team', hint: 'No clear core of 5 players: players rotate' },
}

// Core: players with 75% (or 50%) of the games; without a clear core, the main 5
export const hasCore = (team: TeamData): boolean => team.players.some((p) => p.is_core)

export const getCorePlayers = (team: TeamData): Player[] =>
  team.roster_source === 'recent_matches' && hasCore(team) ? team.players.filter((p) => p.is_core) : team.players

// Stand-ins: everyone else who played for the team in the window
export const getStandins = (team: TeamData): Player[] => {
  const core = new Set(getCorePlayers(team).map((p) => p.id))
  return [...team.players, ...(team.other_players ?? [])].filter((p) => !core.has(p.id) && p.games !== 0)
}

// Players without a name on OpenDota come as "#<account id>"; show them as an ID so they don't read as a nickname
export const renderName = (player: Player) => {
  const accountId = /^#(\d+)$/.exec(player.name)?.[1]
  if (!accountId) return player.name
  return (
    <span className="account-id" title="No player name on OpenDota; this is the account ID">
      ID {accountId}
    </span>
  )
}
