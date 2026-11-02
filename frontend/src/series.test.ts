import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PAGE_SIZE, bestOfLabel, scoreLabel, usePage } from './series'

const rows = (count: number) => Array.from({ length: count }, (_, i) => i)

describe('series labels', () => {
  it('labels the series format', () => {
    expect(bestOfLabel(3)).toBe('Bo3')
    expect(bestOfLabel(null)).toBe('-')
  })

  it('shows a score only when both sides are known', () => {
    expect(scoreLabel(2, 1)).toBe('2:1')
    expect(scoreLabel(0, 0)).toBe('0:0')
    expect(scoreLabel(null, 1)).toBe('-')
    expect(scoreLabel(2, undefined)).toBe('-')
  })
})

describe('usePage', () => {
  it('shows the first page of rows', () => {
    const { result } = renderHook(() => usePage(rows(25)))
    expect(PAGE_SIZE).toBe(10)
    expect(result.current.page).toBe(0)
    expect(result.current.pages).toBe(3)
    expect(result.current.shown).toEqual(rows(10))
  })

  it('has one empty page without rows', () => {
    const { result } = renderHook(() => usePage([]))
    expect(result.current.pages).toBe(1)
    expect(result.current.shown).toEqual([])
  })

  it('moves to another page and clamps to the last page when rows shrink', () => {
    const { result, rerender } = renderHook(({ items }) => usePage(items), { initialProps: { items: rows(25) } })
    act(() => result.current.setPage(2))
    expect(result.current.shown).toEqual([20, 21, 22, 23, 24])
    rerender({ items: rows(15) })
    expect(result.current.page).toBe(1)
    expect(result.current.shown).toEqual([10, 11, 12, 13, 14])
  })
})
