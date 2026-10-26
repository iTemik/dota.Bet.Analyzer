// Labels and paging shared by the series tables (Upcoming / Finished Matches, Predictions)
import { useState } from 'react'

// Rows per page of a series table
export const PAGE_SIZE = 10

export const bestOfLabel = (bestOf: number | null): string => (bestOf ? `Bo${bestOf}` : '-')

// Map score "2:1", or "-" when it is not known
export const scoreLabel = (score1: number | null | undefined, score2: number | null | undefined): string =>
  score1 === null || score1 === undefined || score2 === null || score2 === undefined ? '-' : `${score1}:${score2}`

/** Current page of rows (remount the table with a new `key` to start again from the first page). */
export function usePage<T>(rows: T[]) {
  const [page, setPage] = useState(0)
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const current = Math.min(page, pages - 1)
  return { page: current, pages, shown: rows.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE), setPage }
}
