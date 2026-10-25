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

  it('fill picks a known team and returns its query param', () => {
    const { result } = renderHook(() => useTeamInput())
    let param: [string, string] = ['', '']
    act(() => {
      param = result.current.fill({ name: 'Aurora', team_id: 9467224 })
    })
    expect(param).toEqual(['team_id', '9467224'])
    expect(result.current.value).toBe('Aurora')
    expect(result.current.queryParam()).toEqual(['team_id', '9467224'])
  })

  it('fill uses the name for a team without id', () => {
    const { result } = renderHook(() => useTeamInput())
    act(() => result.current.onSelect({ team_id: 1, name: 'Old' }))
    let param: [string, string] = ['', '']
    act(() => {
      param = result.current.fill({ name: 'New Team', team_id: null })
    })
    expect(param).toEqual(['team', 'New Team'])
    expect(result.current.queryParam()).toEqual(['team', 'New Team'])
  })
})
