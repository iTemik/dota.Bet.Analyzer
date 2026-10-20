import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useTeamInput } from './useTeamInput'

describe('useTeamInput', () => {
  it('sends the typed name when nothing is selected', () => {
    const { result } = renderHook(() => useTeamInput())
    act(() => result.current.onChange('Aurora'))
    expect(result.current.value).toBe('Aurora')
    expect(result.current.queryParam()).toEqual(['team', 'Aurora'])
  })

  it('sends team_id after picking a team from the list', () => {
    const { result } = renderHook(() => useTeamInput())
    // Autocomplete calls onChange with the team name, then onSelect
    act(() => result.current.onChange('Aurora'))
    act(() => result.current.onSelect({ team_id: 9467224, name: 'Aurora' }))
    expect(result.current.queryParam()).toEqual(['team_id', '9467224'])
  })

  it('falls back to the name once the text is edited after selecting', () => {
    const { result } = renderHook(() => useTeamInput())
    act(() => result.current.onChange('Aurora'))
    act(() => result.current.onSelect({ team_id: 9467224, name: 'Aurora' }))
    act(() => result.current.onChange('Aurora Gaming'))
    expect(result.current.queryParam()).toEqual(['team', 'Aurora Gaming'])
  })
})
