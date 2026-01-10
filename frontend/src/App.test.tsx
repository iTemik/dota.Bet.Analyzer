import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

// Mock fetch globally
global.fetch = vi.fn()

describe('App Component', () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    describe('Rendering', () => {
        it('should render the main heading', () => {
            render(<App />)
            expect(screen.getByRole('heading', { name: /Dota 2 Bet Analyzer/i })).toBeInTheDocument()
        })

        it('should render team input fields', () => {
            render(<App />)
            expect(screen.getByLabelText(/Team #1/i)).toBeInTheDocument()
            expect(screen.getByLabelText(/Team #2/i)).toBeInTheDocument()
        })

        it('should render check button', () => {
            render(<App />)
            expect(screen.getByRole('button', { name: /Check Statistics/i })).toBeInTheDocument()
        })

        it('should have team1 input autofocused', () => {
            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i) as HTMLInputElement
            expect(document.activeElement).toBe(team1Input)
        })
    })

    describe('Input Validation', () => {
        it('should show error when submitting with empty teams', async () => {
            render(<App />)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.click(button)

            expect(screen.getByText(/Please enter both team names/i)).toBeInTheDocument()
        })

        it('should show error when only team1 is filled', async () => {
            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.click(button)

            expect(screen.getByText(/Please enter both team names/i)).toBeInTheDocument()
        })

        it('should show error when only team2 is filled', async () => {
            render(<App />)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            expect(screen.getByText(/Please enter both team names/i)).toBeInTheDocument()
        })

        it('should accept whitespace-only input as empty', async () => {
            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, '   ')
            await userEvent.type(team2Input, '   ')
            await userEvent.click(button)

            expect(screen.getByText(/Please enter both team names/i)).toBeInTheDocument()
        })
    })

    describe('API Integration', () => {
        it('should call fetch with correct parameters', async () => {
            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve({ teams: [] }),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Nigma Galaxy')
            await userEvent.type(team2Input, 'Aurora')
            await userEvent.click(button)

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith('/statistics?team=Nigma+Galaxy&team=Aurora')
            })
        })

        it('should display loading state during fetch', async () => {
            const mockFetch = vi.fn(
                () =>
                    new Promise((resolve) =>
                        setTimeout(
                            () =>
                                resolve({
                                    ok: true,
                                    json: () => Promise.resolve({ teams: [] }),
                                }),
                            100
                        )
                    )
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            expect(screen.getByRole('button', { name: /Loading/i })).toBeInTheDocument()
        })

        it('should handle HTTP errors', async () => {
            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: false,
                    status: 500,
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText(/HTTP error! status: 500/i)).toBeInTheDocument()
            })
        })

        it('should handle network errors', async () => {
            const mockFetch = vi.fn(() =>
                Promise.reject(new Error('Network error'))
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText(/Network error/i)).toBeInTheDocument()
            })
        })
    })

    describe('Results Display', () => {
        it('should display statistics when data is returned', async () => {
            const mockData = {
                teams: [
                    {
                        team: 'Nigma Galaxy',
                        tag: 'NGX',
                        team_id: 10000118,
                        rating: 2500,
                        delta: 25.5,
                        logo_url: 'https://example.com/logo1.png',
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                    {
                        team: 'Aurora Gaming',
                        tag: 'Aurora',
                        team_id: 9467224,
                        rating: 2400,
                        delta: -10.3,
                        logo_url: 'https://example.com/logo2.png',
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                ],
            }

            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(mockData),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Nigma Galaxy')
            await userEvent.type(team2Input, 'Aurora Gaming')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText(/Team Comparison/i)).toBeInTheDocument()
                expect(screen.getByText('Nigma Galaxy')).toBeInTheDocument()
                expect(screen.getByText('Aurora Gaming')).toBeInTheDocument()
            })
        })

        it('should display team tags', async () => {
            const mockData = {
                teams: [
                    {
                        team: 'Nigma Galaxy',
                        tag: 'NGX',
                        team_id: 10000118,
                        rating: 2500,
                        delta: 25.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                    {
                        team: 'Aurora Gaming',
                        tag: 'Aurora',
                        team_id: 9467224,
                        rating: 2400,
                        delta: -10.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                ],
            }

            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(mockData),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Nigma Galaxy')
            await userEvent.type(team2Input, 'Aurora Gaming')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText('NGX')).toBeInTheDocument()
                expect(screen.getByText('Aurora')).toBeInTheDocument()
            })
        })

        it('should display team IDs', async () => {
            const mockData = {
                teams: [
                    {
                        team: 'Nigma Galaxy',
                        tag: 'NGX',
                        team_id: 10000118,
                        rating: 2500,
                        delta: 25.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                    {
                        team: 'Aurora Gaming',
                        tag: 'Aurora',
                        team_id: 9467224,
                        rating: 2400,
                        delta: -10.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                ],
            }

            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(mockData),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Nigma Galaxy')
            await userEvent.type(team2Input, 'Aurora Gaming')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText('10000118')).toBeInTheDocument()
                expect(screen.getByText('9467224')).toBeInTheDocument()
            })
        })

        it('should display ratings', async () => {
            const mockData = {
                teams: [
                    {
                        team: 'Nigma Galaxy',
                        tag: 'NGX',
                        team_id: 10000118,
                        rating: 2500,
                        delta: 25.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                    {
                        team: 'Aurora Gaming',
                        tag: 'Aurora',
                        team_id: 9467224,
                        rating: 2400,
                        delta: -10.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                ],
            }

            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(mockData),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Nigma Galaxy')
            await userEvent.type(team2Input, 'Aurora Gaming')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText('2500')).toBeInTheDocument()
                expect(screen.getByText('2400')).toBeInTheDocument()
            })
        })
    })

    describe('Keyboard Input', () => {
        it('should submit form when Enter key is pressed in team1 input', async () => {
            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve({ teams: [] }),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            fireEvent.keyDown(team1Input, { key: 'Enter', code: 'Enter' })

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalled()
            })
        })

        it('should submit form when Enter key is pressed in team2 input', async () => {
            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve({ teams: [] }),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            fireEvent.keyDown(team2Input, { key: 'Enter', code: 'Enter' })

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalled()
            })
        })
    })

    describe('Delta Display', () => {
        it('should format delta with one decimal place', async () => {
            const mockData = {
                teams: [
                    {
                        team: 'Team A',
                        tag: 'A',
                        team_id: 1,
                        rating: 2500,
                        delta: 25.567,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                    {
                        team: 'Team B',
                        tag: 'B',
                        team_id: 2,
                        rating: 2400,
                        delta: -10.234,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                ],
            }

            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(mockData),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            await waitFor(() => {
                // Verify in the table, not in the raw JSON
                const tableCells = screen.getAllByRole('cell')
                const deltas = tableCells.filter(cell => cell.textContent?.includes('25.6') || cell.textContent?.includes('-10.2'))
                expect(deltas.length).toBeGreaterThan(0)
            })
        })

        it('should display PRIME label for positive delta > 15', async () => {
            const mockData = {
                teams: [
                    {
                        team: 'Team A',
                        tag: 'A',
                        team_id: 1,
                        rating: 2500,
                        delta: 20.0,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                    {
                        team: 'Team B',
                        tag: 'B',
                        team_id: 2,
                        rating: 2400,
                        delta: 10.0,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                ],
            }

            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(mockData),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText(/IN PRIME/)).toBeInTheDocument()
            })
        })

        it('should display RUINERS label for negative delta < -15', async () => {
            const mockData = {
                teams: [
                    {
                        team: 'Team A',
                        tag: 'A',
                        team_id: 1,
                        rating: 2500,
                        delta: -20.0,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                    {
                        team: 'Team B',
                        tag: 'B',
                        team_id: 2,
                        rating: 2400,
                        delta: -10.0,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                    },
                ],
            }

            const mockFetch = vi.fn(() =>
                Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(mockData),
                })
            ) as any

            global.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByLabelText(/Team #1/i)
            const team2Input = screen.getByLabelText(/Team #2/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText(/RUINERS/)).toBeInTheDocument()
            })
        })
    })
})
