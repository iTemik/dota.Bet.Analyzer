// Texts for the "i" tooltip of each Team Comparison row; edit them here.
// "Players" below means the 5 main roster players (most tournament games in the window).
export interface RowInfo {
  description: string // what the number is and how it's calculated
  colors?: string // colour highlighting rules: what's good and what's bad
  assumption?: string // why it matters when comparing teams
}

const PLACEHOLDER = 'TBD'

export const ROW_INFO: Record<string, RowInfo> = {
  rating: {
    description: 'OpenDota team rating (Elo style), from the synced teams list.',
    colors: 'Higher is green, lower is red; no colour when they differ by 100 or less.',
    assumption: 'Long-term team strength across all tournament games.',
  },
  lastMatchRating: {
    description: 'Rating change from the team’s latest rated match.',
    colors: 'Above +15 is green, below -15 is red, otherwise no colour.',
    assumption: 'Shows whether the team just won or lost against a strong or weak opponent. ' + PLACEHOLDER,
  },
  rosterChanges: {
    description:
      'Stable: only the 5 core players (75%+ of tournament games, else 50%+) played. Stand-ins: a clear core plus others in some games. New team: no clear core.',
    colors: 'Stable beats Stand-ins beats New team.',
    assumption: 'A settled lineup plays better together; stats of a new team say less.',
  },
  tournamentMatches: {
    description: 'Team wins-losses (win %) in tournament (league) games over the window.',
    colors: 'Higher win % is green, lower is red.',
    assumption: 'Current form in official games.',
  },
  lastMatch: {
    description: 'Date of the latest tournament game played by at least 3 of the 5 players.',
    assumption: 'A long break can mean rust or a lineup change. ' + PLACEHOLDER,
  },
  ratingMatches: {
    description: 'Ranked pub games played by all players in the window, summed.',
    colors: 'More is green, fewer is red.',
    assumption: PLACEHOLDER,
  },
  lobbyMatches: {
    description:
      'Captains Mode lobby games (tournament and scrims; OpenDota can’t tell them apart) played by all players in the window, summed. A game counts once per player.',
    colors: 'More is green, fewer is red.',
    assumption: 'More team practice. ' + PLACEHOLDER,
  },
  pubWin: {
    description: 'Wins / ranked pub games, over all players’ games.',
    colors: 'Higher is green, lower is red.',
    assumption: 'Individual form of the players. ' + PLACEHOLDER,
  },
  lobbyWin: {
    description: 'Wins / Captains Mode lobby games (tournament and scrims), over all players’ games.',
    colors: 'Higher is green, lower is red.',
    assumption: 'Team form, including scrims. ' + PLACEHOLDER,
  },
  avgRank: {
    description: 'Average leaderboard rank of the players who have one; players off the leaderboard are skipped.',
    colors: 'Lower (better) rank is green, higher is red.',
    assumption: 'Individual skill of the players.',
  },
  lowRankPlayers: {
    description: 'Players ranked worse than 150 on the leaderboard ("тысячники": once "not top 1000", ~top 150 after the July 2026 MMR rework).',
    colors: 'Fewer is green, more is red.',
    assumption: PLACEHOLDER,
  },
  otherMatches: {
    description: 'Players’ games that are neither ranked pubs nor Captains Mode lobbies (Turbo, unranked, other modes), summed.',
    assumption: PLACEHOLDER,
  },
  avgMatches: {
    description: 'All games in the window divided by the number of players.',
    colors: 'More is green, fewer is red.',
    assumption: 'How much the players play overall. ' + PLACEHOLDER,
  },
  medianMatches: {
    description: 'Median number of games per player in the window; less affected by one very active or inactive player.',
    colors: 'More is green, fewer is red.',
    assumption: 'How much a typical player plays. ' + PLACEHOLDER,
  },
}
