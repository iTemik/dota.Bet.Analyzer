import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import Collapsible from './Collapsible'

const content = () => screen.getByText('body').parentElement as HTMLElement

describe('Collapsible', () => {
  it('starts closed and toggles the content on header click', async () => {
    const { container } = render(
      <Collapsible title="Raw JSON">
        <pre>body</pre>
      </Collapsible>,
    )
    expect(screen.getByRole('heading', { name: 'Raw JSON' })).toBeInTheDocument()
    expect(content()).toHaveClass('collapsible-content')
    expect(content()).not.toHaveClass('expanded')

    await userEvent.click(screen.getByRole('heading', { name: 'Raw JSON' }))
    expect(content()).toHaveClass('expanded')
    expect(container.querySelector('.collapsible-toggle')).toHaveClass('expanded')

    await userEvent.click(screen.getByRole('heading', { name: 'Raw JSON' }))
    expect(content()).not.toHaveClass('expanded')
  })

  it('starts open with defaultOpen', () => {
    render(
      <Collapsible title="Raw JSON" defaultOpen>
        <pre>body</pre>
      </Collapsible>,
    )
    expect(content()).toHaveClass('expanded')
  })
})
