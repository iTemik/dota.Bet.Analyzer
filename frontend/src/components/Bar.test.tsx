import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Bar from './Bar'

const fill = (container: HTMLElement) => container.querySelector('.bar-fill') as HTMLElement

describe('Bar', () => {
  it('fills value / max with the default progress tone and small size', () => {
    const { container } = render(<Bar value={30} max={120} />)
    expect(container.firstChild).toHaveClass('bar', 'bar-small')
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true')
    expect(fill(container)).toHaveClass('bar-fill', 'bar-progress')
    expect(fill(container).style.width).toBe('25%')
  })

  it('clamps the fill to 0-100% and shows nothing when max is 0', () => {
    expect(fill(render(<Bar value={150} />).container).style.width).toBe('100%')
    expect(fill(render(<Bar value={-5} />).container).style.width).toBe('0%')
    expect(fill(render(<Bar value={5} max={0} />).container).style.width).toBe('0%')
  })

  it('applies tone and size classes', () => {
    const { container } = render(<Bar value={50} tone="bad" size="thin" />)
    expect(container.firstChild).toHaveClass('bar-thin')
    expect(fill(container)).toHaveClass('bar-bad')
  })

  it('is a labelled progressbar when given a label', () => {
    render(<Bar value={340} max={1800} label="OpenDota requests today" />)
    const bar = screen.getByRole('progressbar', { name: 'OpenDota requests today' })
    expect(bar).toHaveAttribute('aria-valuenow', '340')
    expect(bar).toHaveAttribute('aria-valuemax', '1800')
    expect(bar).toHaveAttribute('aria-valuemin', '0')
  })
})
