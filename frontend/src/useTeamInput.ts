import { useState } from 'react'

interface SelectedTeam {
  team_id: number
  name: string
}

export interface TeamInput {
  value: string
  onChange: (value: string) => void
  onSelect: (team: SelectedTeam) => void
  // Fill the input with a team (picked when team_id is known, plain text otherwise); returns its query param
  fill: (team: { name: string; team_id: number | null }) => [string, string]
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
    fill: (team) => {
      setValue(team.name)
      setSelected(team.team_id === null ? null : { team_id: team.team_id, name: team.name })
      return team.team_id === null ? ['team', team.name] : ['team_id', String(team.team_id)]
    },
    queryParam: () =>
      selected !== null && value === selected.name ? ['team_id', String(selected.team_id)] : ['team', value],
  }
}
