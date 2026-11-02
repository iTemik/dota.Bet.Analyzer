import { useState, type ReactNode } from 'react'

interface CollapsibleProps {
  title: string
  children: ReactNode
  /** Open on first render; closed by default. */
  defaultOpen?: boolean
}

/** A section with a clickable `h2` header that shows or hides its content (raw JSON blocks on the Compare tab). */
export default function Collapsible({ title, children, defaultOpen = false }: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen)
  const expanded = open ? 'expanded' : ''
  return (
    <>
      <div className="collapsible-header" onClick={() => setOpen(!open)}>
        <h2>{title}</h2>
        <span className={`collapsible-toggle ${expanded}`}>▼</span>
      </div>
      <div className={`collapsible-content ${expanded}`}>{children}</div>
    </>
  )
}
