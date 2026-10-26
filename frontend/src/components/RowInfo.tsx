// "i" tooltip for a table row label; shared by the comparison and insights tables
export interface RowInfo {
  description: string // what the number is and how it's calculated
  colors?: string // colour highlighting rules: what's good and what's bad
  assumption?: string // why it matters when comparing teams; "TBD" while it is a placeholder
}

// "i" icon after a row label; its tooltip shows on hover or keyboard focus
export const RowInfoIcon = ({ info }: { info: RowInfo }) => (
  <span className="row-info" tabIndex={0} role="button" aria-label="Row info">
    i
    <span className="row-info-tooltip" role="tooltip">
      <span>
        <b>Description:</b> {info.description}
      </span>
      {info.colors && (
        <span>
          <b>Color Highlighting:</b> {info.colors}
        </span>
      )}
      {info.assumption && (
        <span>
          <b>Assumption:</b> {info.assumption}
        </span>
      )}
    </span>
  </span>
)
