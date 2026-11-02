import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RowInfoIcon } from './RowInfo'

describe('RowInfoIcon', () => {
  it('is a focusable icon whose tooltip shows every given part', () => {
    render(<RowInfoIcon info={{ description: 'Games won', colors: 'Higher is green', assumption: 'TBD' }} />)
    const icon = screen.getByRole('button', { name: 'Row info' })
    expect(icon).toHaveAttribute('tabindex', '0')
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent('Description: Games won')
    expect(tooltip).toHaveTextContent('Color Highlighting: Higher is green')
    expect(tooltip).toHaveTextContent('Assumption: TBD')
  })

  it('leaves out missing colour and assumption parts', () => {
    render(<RowInfoIcon info={{ description: 'Games won' }} />)
    const tooltip = screen.getByRole('tooltip')
    expect(tooltip).toHaveTextContent(/^Description: Games won$/)
  })
})
