import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

// Helper to create proper mock responses with text() method for version endpoint
const createMockResponse = (data: unknown, ok = true, status = 200) => ({
    ok,
    status,
    text: () => Promise.resolve(JSON.stringify(data)),
    json: () => Promise.resolve(data),
})

// Helper to create version endpoint mock response
const createVersionResponse = () => {
    const versionResponse = JSON.stringify({ backend: '0.4.DEV' })
    return Promise.resolve({
        ok: true,
        text: () => Promise.resolve(versionResponse),
        json: () => Promise.resolve({ backend: '0.4.DEV' }),
    })
}

// Mock fetch globally
globalThis.fetch = vi.fn()

describe('App Component', () => {
    beforeEach(() => {
        vi.clearAllMocks()
            // Setup default fetch mock that handles all routes
            ; (globalThis.fetch as any).mockImplementation((url: string) => {
            if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                // Default response for other endpoints
                return Promise.resolve(createMockResponse({ teams: [] }))
            })
    })

    describe('Rendering', () => {
        it('should render the main heading', async () => {
            await act(async () => {
                render(<App />)
            })
            expect(screen.getByRole('heading', { name: /Dota 2 Bet Analyzer/i })).toBeInTheDocument()
        })

        it('should render version in header', async () => {
            await act(async () => {
                render(<App />)
            })
            expect(screen.getByText(/v\d+\.\d+\.\d+/)).toBeInTheDocument()
        })

        it('should render team input fields', async () => {
            await act(async () => {
                render(<App />)
            })
            expect(screen.getByPlaceholderText(/Enter first team name/i)).toBeInTheDocument()
            expect(screen.getByPlaceholderText(/Enter second team name/i)).toBeInTheDocument()
        })

        it('should render check button', async () => {
            await act(async () => {
                render(<App />)
            })
            expect(screen.getByRole('button', { name: /Check Statistics/i })).toBeInTheDocument()
        })

        it('should have team1 input autofocused', async () => {
            await act(async () => {
                render(<App />)
            })
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i) as HTMLInputElement
            // Wait for both autofocus and version fetch to complete
            await waitFor(() => {
                expect(document.activeElement).toBe(team1Input)
            }, { timeout: 1000 })
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
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.click(button)

            expect(screen.getByText(/Please enter both team names/i)).toBeInTheDocument()
        })

        it('should show error when only team2 is filled', async () => {
            render(<App />)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            expect(screen.getByText(/Please enter both team names/i)).toBeInTheDocument()
        })

        it('should accept whitespace-only input as empty', async () => {
            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, '   ')
            await userEvent.type(team2Input, '   ')
            await userEvent.click(button)

            expect(screen.getByText(/Please enter both team names/i)).toBeInTheDocument()
        })
    })

    describe('API Integration', () => {
        it('should call fetch with correct parameters', async () => {
            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse({ teams: [] }))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Nigma Galaxy')
            await userEvent.type(team2Input, 'Aurora')
            await userEvent.click(button)

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalledWith('/api/statistics?team=Nigma+Galaxy&team=Aurora')
            })
        })

        it('should display loading state during fetch', async () => {
            const mockFetch = vi.fn((url: string) =>
                new Promise((resolve) =>
                    setTimeout(
                        () => {
                            if (url === '/api/version') {
                                resolve(createMockResponse({ backend: '0.4.DEV' }))
                            } else {
                                resolve(createMockResponse({ teams: [] }))
                            }
                        },
                        100
                    )
                )
            ) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            expect(screen.getByRole('button', { name: /Loading/i })).toBeInTheDocument()
        })

        it('should handle HTTP errors', async () => {
            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse({}, false, 500))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText(/HTTP error! status: 500/i)).toBeInTheDocument()
            })
        })

        it('should handle network errors', async () => {
            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return createVersionResponse()
                }
                return Promise.reject(new Error('Network error'))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
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
                        task_id: null,
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
                        task_id: null,
                    },
                ],
            }

            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse(mockData))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
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
                        task_id: null,
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
                        task_id: null,
                    },
                ],
            }

            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse(mockData))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
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
                        task_id: null,
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
                        task_id: null,
                    },
                ],
            }

            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse(mockData))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
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
                        task_id: null,
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
                        task_id: null,
                    },
                ],
            }

            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse(mockData))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
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

    describe('Summary Data Display', () => {
        it('should display summary statistics when task completes', async () => {
            const mockStats = {
                teams: [
                    {
                        team: 'Team A',
                        tag: 'A',
                        team_id: 1,
                        rating: 2500,
                        delta: 25.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: 'task_123',
                    },
                    {
                        team: 'Team B',
                        tag: 'B',
                        team_id: 2,
                        rating: 2400,
                        delta: -10.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: 'task_456',
                    },
                ],
            }

            const mockSummary = {
                task_123: {
                    results: [],
                    summary: {
                        rating_matches: 28,
                        tournament_matches: 20,
                        other_matches: 6,
                        matches_avg: 9,
                        matches_median: 4,
                        win_percentage: null,
                    },
                    successful: 6,
                    total: 6,
                },
                task_456: {
                    results: [],
                    summary: {
                        rating_matches: 15,
                        tournament_matches: 10,
                        other_matches: 3,
                        matches_avg: 5.6,
                        matches_median: 4,
                        win_percentage: null,
                    },
                    successful: 6,
                    total: 6,
                },
            }

            let callCount = 0
            const mockFetch = vi.fn((url: string) => {
                callCount++
                if (url === '/api/statistics?team=Team+A&team=Team+B') {
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve(mockStats),
                    })
                }
                if (url.includes('/api/results/')) {
                    const taskId = url.split('/').pop()
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve(mockSummary[taskId as keyof typeof mockSummary]),
                    })
                }
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.reject(new Error('Unknown URL'))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            // The component should display the initial stats
            await waitFor(() => {
                expect(screen.getByText('Team A')).toBeInTheDocument()
            })
        })

        it('should display rating matches in summary table', async () => {
            const mockStats = {
                teams: [
                    {
                        team: 'Team A',
                        tag: 'A',
                        team_id: 1,
                        rating: 2500,
                        delta: 25.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: 'task_rating_1',
                    },
                    {
                        team: 'Team B',
                        tag: 'B',
                        team_id: 2,
                        rating: 2400,
                        delta: -10.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: 'task_rating_2',
                    },
                ],
            }

            const mockSummary = {
                task_rating_1: {
                    results: [],
                    summary: {
                        rating_matches: 28,
                        tournament_matches: 20,
                        other_matches: 6,
                        matches_avg: 9,
                        matches_median: 4,
                        win_percentage: 65.0,
                        avg_rank: 3500,
                        bad_rank_players: 2,
                    },
                    successful: 6,
                    total: 6,
                },
                task_rating_2: {
                    results: [],
                    summary: {
                        rating_matches: 15,
                        tournament_matches: 10,
                        other_matches: 3,
                        matches_avg: 5.6,
                        matches_median: 4,
                        win_percentage: 55.0,
                        avg_rank: 4000,
                        bad_rank_players: 3,
                    },
                    successful: 6,
                    total: 6,
                },
            }

            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return createVersionResponse()
                }
                if (url.includes('/api/statistics')) {
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve(mockStats),
                    })
                }
                if (url.includes('/api/stream-progress/')) {
                    const taskId = url.split('/').pop()
                    return Promise.resolve({
                        ok: true,
                        text: () => Promise.resolve(JSON.stringify({
                            step: 1,
                            message: 'Complete',
                            progress: 100,
                            data: mockSummary[taskId as keyof typeof mockSummary],
                            timestamp: Date.now()
                        })),
                    })
                }
                if (url.includes('/api/results/')) {
                    const taskId = url.split('/').pop()
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve(mockSummary[taskId as keyof typeof mockSummary]),
                    })
                }
                return Promise.reject(new Error('Unknown URL'))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            // Wait for statistics to be displayed
            await waitFor(() => {
                expect(screen.getByText('Team A')).toBeInTheDocument()
            })

            // Wait for summary data to be polled and rating matches to appear
            await waitFor(() => {
                expect(screen.getByText(/Rating Matches/i)).toBeInTheDocument()
                expect(screen.getByText('28')).toBeInTheDocument()
                expect(screen.getByText('15')).toBeInTheDocument()
            }, { timeout: 5000 })
        }, 10000)
    })

    describe('Keyboard Input', () => {
        it('should submit form when Enter key is pressed in team1 input', async () => {
            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse({ teams: [] }))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            fireEvent.keyDown(team1Input, { key: 'Enter', code: 'Enter' })

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalled()
            })
        })

        it('should submit form when Enter key is pressed in team2 input', async () => {
            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse({ teams: [] }))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)

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
                        task_id: null,
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
                        task_id: null,
                    },
                ],
            }

            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse(mockData))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
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
    })

    describe('Color Highlighting', () => {
        it('should apply positive color for higher rating', async () => {
            const mockData = {
                teams: [
                    {
                        team: 'Team A',
                        tag: 'A',
                        team_id: 1,
                        rating: 2500,
                        delta: 25.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: null,
                    },
                    {
                        team: 'Team B',
                        tag: 'B',
                        team_id: 2,
                        rating: 2300,
                        delta: -10.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: null,
                    },
                ],
            }

            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse(mockData))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            // Wait for the table to render with statistics
            await waitFor(() => {
                expect(screen.getByText('Team A')).toBeInTheDocument()
            })

            // Now query for rating cells
            const ratingCells = screen.getAllByRole('cell')
            const teamARatingCell = ratingCells.find(cell =>
                cell.parentElement?.children[0]?.textContent === 'Rating' &&
                cell.textContent === '2500'
            )

            expect(teamARatingCell).toHaveStyle({
                backgroundColor: '#6b9d7a' // COLOR_POSITIVE (higher rating)
            })

            const teamBRatingCell = ratingCells.find(cell =>
                cell.parentElement?.children[0]?.textContent === 'Rating' &&
                cell.textContent === '2300'
            )

            expect(teamBRatingCell).toHaveStyle({
                backgroundColor: '#9d6b6b' // COLOR_NEGATIVE (lower rating)
            })
        })
    })

    describe('Summary Statistics - Team Quality Metrics', () => {
        it('should display average player rank in summary table', async () => {
            const mockStats = {
                teams: [
                    {
                        team: 'Team A',
                        tag: 'A',
                        team_id: 1,
                        rating: 2500,
                        delta: 25.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: 'task_avg_rank_1',
                    },
                    {
                        team: 'Team B',
                        tag: 'B',
                        team_id: 2,
                        rating: 2400,
                        delta: -10.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: 'task_avg_rank_2',
                    },
                ],
            }

            const mockSummary = {
                task_avg_rank_1: {
                    results: [],
                    summary: {
                        rating_matches: 28,
                        tournament_matches: 20,
                        other_matches: 6,
                        matches_avg: 9,
                        matches_median: 4,
                        win_percentage: 75.5,
                        avg_rank: 3500,
                        bad_rank_players: 2,
                    },
                    successful: 6,
                    total: 6,
                },
                task_avg_rank_2: {
                    results: [],
                    summary: {
                        rating_matches: 15,
                        tournament_matches: 10,
                        other_matches: 3,
                        matches_avg: 5.6,
                        matches_median: 4,
                        win_percentage: 60.0,
                        avg_rank: 4000,
                        bad_rank_players: 3,
                    },
                    successful: 6,
                    total: 6,
                },
            }

            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return createVersionResponse()
                }
                if (url.includes('/api/statistics')) {
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve(mockStats),
                    })
                }
                if (url.includes('/api/stream-progress/')) {
                    const taskId = url.split('/').pop()
                    return Promise.resolve({
                        ok: true,
                        text: () => Promise.resolve(JSON.stringify({
                            step: 1,
                            message: 'Complete',
                            progress: 100,
                            data: mockSummary[taskId as keyof typeof mockSummary],
                            timestamp: Date.now()
                        })),
                    })
                }
                if (url.includes('/api/results/')) {
                    const taskId = url.split('/').pop()
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve(mockSummary[taskId as keyof typeof mockSummary]),
                    })
                }
                return Promise.reject(new Error('Unknown URL'))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            // Wait for statistics to be displayed
            await waitFor(() => {
                expect(screen.getByText('Team A')).toBeInTheDocument()
            })

            // Wait for summary data to be polled and the rows to be rendered
            await waitFor(() => {
                expect(screen.getByText(/Average Player Rank/i)).toBeInTheDocument()
            }, { timeout: 5000 })
        }, 10000)

        it('should display bad rank players count in summary table', async () => {
            const mockStats = {
                teams: [
                    {
                        team: 'Team C',
                        tag: 'C',
                        team_id: 3,
                        rating: 2600,
                        delta: 35.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: 'task_bad_rank_1',
                    },
                    {
                        team: 'Team D',
                        tag: 'D',
                        team_id: 4,
                        rating: 2300,
                        delta: -20.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: 'task_bad_rank_2',
                    },
                ],
            }

            const mockSummary = {
                task_bad_rank_1: {
                    results: [],
                    summary: {
                        rating_matches: 32,
                        tournament_matches: 22,
                        other_matches: 7,
                        matches_avg: 10.5,
                        matches_median: 5,
                        win_percentage: 72.0,
                        avg_rank: 3200,
                        bad_rank_players: 1,
                    },
                    successful: 6,
                    total: 6,
                },
                task_bad_rank_2: {
                    results: [],
                    summary: {
                        rating_matches: 18,
                        tournament_matches: 12,
                        other_matches: 4,
                        matches_avg: 6.2,
                        matches_median: 4,
                        win_percentage: 55.5,
                        avg_rank: 4200,
                        bad_rank_players: 4,
                    },
                    successful: 6,
                    total: 6,
                },
            }

            const mockFetch = vi.fn((url: string) => {
                if (url.includes('/api/statistics')) {
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve(mockStats),
                    })
                }
                if (url.includes('/api/stream-progress/')) {
                    const taskId = url.split('/').pop()
                    return Promise.resolve({
                        ok: true,
                        text: () => Promise.resolve(JSON.stringify({
                            step: 1,
                            message: 'Complete',
                            progress: 100,
                            data: mockSummary[taskId as keyof typeof mockSummary],
                            timestamp: Date.now()
                        })),
                    })
                }
                if (url.includes('/api/results/')) {
                    const taskId = url.split('/').pop()
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve(mockSummary[taskId as keyof typeof mockSummary]),
                    })
                }
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.reject(new Error('Unknown URL'))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            await userEvent.type(team1Input, 'Team C')
            await userEvent.type(team2Input, 'Team D')
            await userEvent.click(button)

            // Wait for statistics to be displayed
            await waitFor(() => {
                expect(screen.getByText('Team C')).toBeInTheDocument()
            })

            // Wait for summary data to be polled and the rows to be rendered
            await waitFor(() => {
                expect(screen.getByText(/Bad Rank Players/i)).toBeInTheDocument()
            }, { timeout: 5000 })
        }, 10000)
    })

    describe('Polling Management', () => {
        it('should clear previous results when checking new statistics', async () => {
            const mockData1 = {
                teams: [
                    {
                        team: 'Team A',
                        tag: 'A',
                        team_id: 1,
                        rating: 2500,
                        delta: 25.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: null,
                    },
                    {
                        team: 'Team B',
                        tag: 'B',
                        team_id: 2,
                        rating: 2400,
                        delta: -10.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: null,
                    },
                ],
            }

            const mockData2 = {
                teams: [
                    {
                        team: 'Team C',
                        tag: 'C',
                        team_id: 3,
                        rating: 2600,
                        delta: 35.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: null,
                    },
                    {
                        team: 'Team D',
                        tag: 'D',
                        team_id: 4,
                        rating: 2300,
                        delta: -20.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: null,
                    },
                ],
            }

            let callCount = 0
            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    const versionResponse = JSON.stringify({ backend: '0.4.DEV' })
                    return Promise.resolve({
                        ok: true,
                        text: () => Promise.resolve(versionResponse),
                        json: () => Promise.resolve({ backend: '0.4.DEV' }),
                    })
                }

                callCount++
                // First call returns Team A vs B, second call returns Team C vs D
                const data = callCount === 1 ? mockData1 : mockData2
                return Promise.resolve({
                    ok: true,
                    json: () => Promise.resolve(data),
                })
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            // First search
            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText('Team A')).toBeInTheDocument()
            }, { timeout: 5000 })

            // Clear inputs and do second search
            await userEvent.clear(team1Input)
            await userEvent.clear(team2Input)
            await userEvent.type(team1Input, 'Team C')
            await userEvent.type(team2Input, 'Team D')
            await userEvent.click(button)

            // Previous results should be cleared, new results should be displayed
            await waitFor(() => {
                expect(screen.getByText('Team C')).toBeInTheDocument()
                expect(screen.queryByText('Team A')).not.toBeInTheDocument()
            }, { timeout: 5000 })
        }, 10000)

        it('should stop polling if a new search starts while polling', async () => {
            const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval')

            const mockData = {
                teams: [
                    {
                        team: 'Team A',
                        tag: 'A',
                        team_id: 1,
                        rating: 2500,
                        delta: 25.5,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: 'task_123', // Has task ID to trigger polling
                    },
                    {
                        team: 'Team B',
                        tag: 'B',
                        team_id: 2,
                        rating: 2400,
                        delta: -10.3,
                        error_code: null,
                        error_message: null,
                        players: [],
                        other_players: [],
                        task_id: null,
                    },
                ],
            }

            const mockFetch = vi.fn((url: string) => {
                if (url === '/api/version') {
                    return Promise.resolve(createMockResponse({ backend: '0.4.DEV' }))
                }
                return Promise.resolve(createMockResponse(mockData))
            }) as any

            globalThis.fetch = mockFetch

            render(<App />)
            const team1Input = screen.getByPlaceholderText(/Enter first team name/i)
            const team2Input = screen.getByPlaceholderText(/Enter second team name/i)
            const button = screen.getByRole('button', { name: /Check Statistics/i })

            // First search with task ID
            await userEvent.type(team1Input, 'Team A')
            await userEvent.type(team2Input, 'Team B')
            await userEvent.click(button)

            await waitFor(() => {
                expect(screen.getByText('Team A')).toBeInTheDocument()
            })

            // Second search should clear previous polling
            await userEvent.clear(team1Input)
            await userEvent.clear(team2Input)
            await userEvent.type(team1Input, 'Team C')
            await userEvent.type(team2Input, 'Team D')
            await userEvent.click(button)

            // clearInterval should have been called to stop the previous polling
            await waitFor(() => {
                expect(clearIntervalSpy).toHaveBeenCalled()
            })

            clearIntervalSpy.mockRestore()
        })
    })
})
