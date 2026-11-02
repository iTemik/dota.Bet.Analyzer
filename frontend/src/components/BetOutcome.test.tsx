import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { prediction } from '../test/predictionFixtures'
import BetOutcome, { Loss, Profit, SIMULATION_NOTE } from './BetOutcome'

const settled = { team1_maps_won: 2, team2_maps_won: 1 }

describe('BetOutcome', () => {
  it('shows a won bet with its net profit', () => {
    const { container } = render(<BetOutcome prediction={prediction({ ...settled, bet_won: true })} />)
    expect(container).toHaveTextContent('Won +85')
    expect(screen.getByText('+85')).toHaveClass('money-profit')
  })

  it('shows a lost bet with its stake', () => {
    const { container } = render(<BetOutcome prediction={prediction({ ...settled, bet_won: false })} />)
    expect(container).toHaveTextContent('Lost -100')
    expect(screen.getByText('-100')).toHaveClass('money-loss')
  })

  it('shows a pending bet with possible profit and loss', () => {
    const { container } = render(<BetOutcome prediction={prediction()} />)
    expect(container).toHaveTextContent('Pending +85 / -100')
  })

  it('shows only the label without a bet', () => {
    const { container } = render(<BetOutcome prediction={prediction({ bet_team: null, stake: null })} />)
    expect(container).toHaveTextContent(/^No bet$/)
  })

  it('signs amounts only when not zero and marks them as simulated', () => {
    render(
      <>
        <Profit value={92.5} />
        <Profit value={0} />
        <Loss value={0} />
      </>,
    )
    expect(screen.getByText('+92.5')).toHaveAttribute('title', SIMULATION_NOTE)
    expect(screen.getAllByText('0')).toHaveLength(2)
  })
})
