/** Fill colour: `neutral` white, `progress` bright green, `good` green, `bad` red. */
export type BarTone = 'neutral' | 'progress' | 'good' | 'bad'

/** `thin` 3 px full-width line under a value, `small` 80 px inline bar, `large` 20 px full-width progress bar. */
export type BarSize = 'thin' | 'small' | 'large'

interface BarProps {
  value: number
  max?: number
  tone?: BarTone
  size?: BarSize
  /** Accessible name; with it the bar is a `progressbar` for screen readers, without it the bar is hidden from them. */
  label?: string
}

/** The one horizontal bar of the app (Compare progress, Data status, Meta table cells); fill width = value / max. */
export default function Bar({ value, max = 100, tone = 'progress', size = 'small', label }: BarProps) {
  const percent = max > 0 ? Math.max(0, Math.min(100, (100 * value) / max)) : 0
  const a11y = label
    ? { role: 'progressbar', 'aria-label': label, 'aria-valuemin': 0, 'aria-valuemax': max, 'aria-valuenow': value }
    : { 'aria-hidden': true }
  return (
    <span className={`bar bar-${size}`} {...a11y}>
      <span className={`bar-fill bar-${tone}`} style={{ width: `${percent}%` }} />
    </span>
  )
}
