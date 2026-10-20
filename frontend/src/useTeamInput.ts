import { useState } from 'react'

interface SelectedTeam {
  team_id: number
  name: string
}

export interface TeamInput {
  value: string
  onChange: (value: string) => void
  onSelect: (team: SelectedTeam) => void
  // /api/statistics query param: `team_id` if the text still matches the team picked from the list, else `team`
  queryParam: () => [string, string]
}

/** State of one team input: typed text plus the team picked from the autocomplete list. */
export function useTeamInput(): TeamInput {
  const [value, setValue] = useState('')
  const [selected, setSelected] = useState<SelectedTeam | null>(null)

  return {
    value,
    onChange: (text) => {
      setValue(text)
      // Typing clears the selection; onSelect sets it again if the user picks from the list
      setSelected(null)
    },
    onSelect: (team) => setSelected({ team_id: team.team_id, name: team.name }),
    queryParam: () =>
      selected !== null && value === selected.name ? ['team_id', String(selected.team_id)] : ['team', value],
  }
}
