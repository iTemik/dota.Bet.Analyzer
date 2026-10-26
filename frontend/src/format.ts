// Formatting shared by the Team Comparison and Team Insights tables

// Color constants - defined in App.css as CSS variables
export const COLOR_POSITIVE = '#6b9d7a'
export const COLOR_NEGATIVE = '#9d6b6b'

export const formatDate = (unixTime: number | null | undefined): string => {
  if (!unixTime) return '-'
  return new Date(unixTime * 1000).toLocaleDateString()
}

export const formatPercent = (value: number | null | undefined): string =>
  typeof value === 'number' ? value.toFixed(1) + '%' : '-'

export const formatFixed = (value: number | null | undefined, digits: number): string =>
  value ? value.toFixed(digits) : '-'

// Team name for a table header, or "Team #n" while it is unknown
export const teamName = (team: { team?: string } | undefined, index: number): string => team?.team || `Team #${index + 1}`

export const formatDateTime = (unixTime: number | null | undefined): string => {
  if (!unixTime) return '-'
  return new Date(unixTime * 1000).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })
}

// Date with a short month name and time, e.g. "Oct 26, 14:00"
export const formatShortDateTime = (unixTime: number | null | undefined): string => {
  if (!unixTime) return '-'
  return new Date(unixTime * 1000).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
