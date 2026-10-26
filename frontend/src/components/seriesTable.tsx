// Cells and pager shared by the series tables (Upcoming / Finished Matches, Predictions)

/** Two cells for one team: icon, then name. */
export function TeamCells({ name, logoUrl }: { name: string; logoUrl: string | null }) {
  return (
    <>
      <td className="match-team-icon">{logoUrl && <img src={logoUrl} alt={`${name} logo`} />}</td>
      <td>{name}</td>
    </>
  )
}

/** Previous / Next buttons, shown only when there is more than one page. */
export function Pager({ page, pages, setPage }: { page: number; pages: number; setPage: (page: number) => void }) {
  if (pages <= 1) return null
  return (
    <div className="matches-pager">
      <button type="button" className="secondary-btn" onClick={() => setPage(page - 1)} disabled={page === 0}>
        Previous
      </button>
      <span>
        Page {page + 1} of {pages}
      </span>
      <button type="button" className="secondary-btn" onClick={() => setPage(page + 1)} disabled={page === pages - 1}>
        Next
      </button>
    </div>
  )
}
