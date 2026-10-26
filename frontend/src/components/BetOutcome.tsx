import { OUTCOME_LABELS, formatMoney, outcome, possibleLoss, possibleProfit } from '../predictions'
import type { Prediction } from '../types'

// Amounts are simulated (no real money is tracked); they get a sign only when not zero
export const SIMULATION_NOTE = 'Simulation: not real money'

export const Profit = ({ value }: { value: number }) => (
  <span className="money-profit" title={SIMULATION_NOTE}>
    {(value > 0 ? '+' : '') + formatMoney(value)}
  </span>
)
export const Loss = ({ value }: { value: number }) => (
  <span className="money-loss" title={SIMULATION_NOTE}>
    {(value > 0 ? '-' : '') + formatMoney(value)}
  </span>
)

/** Outcome label with the bet's profit (won), loss (lost) or both possible amounts (pending). */
function BetOutcome({ prediction }: { prediction: Prediction }) {
  const result = outcome(prediction)
  const profit = possibleProfit(prediction)
  const loss = possibleLoss(prediction)
  return (
    <>
      {OUTCOME_LABELS[result]}
      {result === 'won' && profit !== null && (
        <>
          {' '}
          <Profit value={profit} />
        </>
      )}
      {result === 'lost' && loss !== null && (
        <>
          {' '}
          <Loss value={loss} />
        </>
      )}
      {result === 'pending' && profit !== null && loss !== null && (
        <>
          {' '}
          <Profit value={profit} /> / <Loss value={loss} />
        </>
      )}
    </>
  )
}

export default BetOutcome
