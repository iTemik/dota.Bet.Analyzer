import { describe, expect, it } from 'vitest'
import {
  formatDate,
  formatDateTime,
  formatFixed,
  formatPercent,
  formatShortCount,
  formatShortDateTime,
  teamName,
} from './format'

const TIME = 1_700_000_000
const date = new Date(TIME * 1000)

describe('format', () => {
  it('shows "-" for a missing or zero time', () => {
    for (const format of [formatDate, formatDateTime, formatShortDateTime]) {
      expect(format(null)).toBe('-')
      expect(format(undefined)).toBe('-')
      expect(format(0)).toBe('-')
    }
  })

  it('formats unix seconds in the local format', () => {
    expect(formatDate(TIME)).toBe(date.toLocaleDateString())
    expect(formatDateTime(TIME)).toBe(date.toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }))
    expect(formatShortDateTime(TIME)).toBe(
      date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
    )
  })

  it('formats percents with one decimal, including 0', () => {
    expect(formatPercent(52.345)).toBe('52.3%')
    expect(formatPercent(0)).toBe('0.0%')
    expect(formatPercent(null)).toBe('-')
    expect(formatPercent(undefined)).toBe('-')
  })

  it('formats fixed digits and shows "-" for 0 or a missing value', () => {
    expect(formatFixed(512.456, 1)).toBe('512.5')
    expect(formatFixed(3, 2)).toBe('3.00')
    expect(formatFixed(0, 1)).toBe('-')
    expect(formatFixed(null, 1)).toBe('-')
  })

  it('names a team or falls back to "Team #n"', () => {
    expect(teamName({ team: 'Team A' }, 0)).toBe('Team A')
    expect(teamName({ team: '' }, 1)).toBe('Team #2')
    expect(teamName(undefined, 0)).toBe('Team #1')
  })

  it('shortens counts like OpenDota', () => {
    expect(formatShortCount(950)).toBe('950')
    expect(formatShortCount(1000)).toBe('1k')
    expect(formatShortCount(1234)).toBe('1.2k')
    expect(formatShortCount(164_400)).toBe('164k')
    expect(formatShortCount(1_250_000)).toBe('1.3M')
    expect(formatShortCount(12_000_000)).toBe('12M')
  })
})
