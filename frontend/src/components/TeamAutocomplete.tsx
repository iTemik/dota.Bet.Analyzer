import { useEffect, useRef, useState } from 'react'
import './TeamAutocomplete.css'

interface Team {
  team_id: number
  name: string
  tag: string
  logo_url?: string
  rating?: number
}

interface TeamAutocompleteProps {
  value: string
  onChange: (value: string) => void
  onSelect?: (team: Team) => void
  placeholder?: string
  disabled?: boolean
  autoFocus?: boolean
}

const MIN_CHARS = 2
const DEBOUNCE_MS = 300
const CACHE_DURATION = 5 * 60 * 1000 // 5 minutes

/**
 * TeamAutocomplete Component
 *
 * Features:
 * - Debounced API requests (300ms)
 * - Result caching (5 minutes)
 * - Keyboard navigation (arrow keys, enter, escape)
 * - Loading state indicator
 * - Click-outside to close dropdown
 * - Mobile-friendly
 */
export function TeamAutocomplete({
  value,
  onChange,
  onSelect,
  placeholder = 'Enter team name',
  disabled = false,
  autoFocus = false,
}: TeamAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<Team[]>([])
  const [loading, setLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [error, setError] = useState<string | null>(null)

  // Cache to avoid repeated requests for same query
  const cacheRef = useRef<Map<string, { data: Team[]; timestamp: number }>>(new Map())
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Clear cache entry when it expires
  const getCachedResult = (query: string): Team[] | null => {
    const cached = cacheRef.current.get(query.toLowerCase())
    if (!cached) return null

    if (Date.now() - cached.timestamp > CACHE_DURATION) {
      cacheRef.current.delete(query.toLowerCase())
      return null
    }

    return cached.data
  }

  const setCachedResult = (query: string, data: Team[]) => {
    cacheRef.current.set(query.toLowerCase(), { data, timestamp: Date.now() })
  }

  // Fetch teams from API
  const fetchTeams = async (query: string) => {
    if (query.length < MIN_CHARS) {
      setSuggestions([])
      setIsOpen(false)
      return
    }

    // Check cache first
    const cached = getCachedResult(query)
    if (cached) {
      setSuggestions(cached)
      setIsOpen(cached.length > 0)
      setError(null)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const params = new URLSearchParams({ q: query, limit: '10' })
      const response = await fetch(`/api/teams/search?${params.toString()}`)

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      setSuggestions(data)
      setCachedResult(query, data)
      setIsOpen(data.length > 0)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to fetch teams'
      setError(errorMsg)
      setSuggestions([])
      setIsOpen(false)
    } finally {
      setLoading(false)
    }
  }

  // Debounced search
  const handleInputChange = (inputValue: string) => {
    onChange(inputValue)
    setHighlightedIndex(-1)

    // Clear existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }

    if (!inputValue.trim()) {
      setSuggestions([])
      setIsOpen(false)
      setError(null)
      return
    }

    // Set new timer
    debounceTimerRef.current = setTimeout(() => {
      fetchTeams(inputValue.trim())
    }, DEBOUNCE_MS)
  }

  // Handle team selection
  const handleSelectTeam = (team: Team) => {
    onChange(team.name)
    setIsOpen(false)
    setSuggestions([])
    setHighlightedIndex(-1)
    onSelect?.(team)
  }

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen) return

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setHighlightedIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : prev))
        break

      case 'ArrowUp':
        e.preventDefault()
        setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : -1))
        break

      case 'Enter':
        e.preventDefault()
        if (highlightedIndex >= 0) {
          handleSelectTeam(suggestions[highlightedIndex])
        }
        break

      case 'Escape':
        e.preventDefault()
        setIsOpen(false)
        break

      default:
        break
    }
  }

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Autofocus input if requested
  useEffect(() => {
    if (autoFocus && inputRef.current) {
      inputRef.current.focus()
    }
  }, [autoFocus])

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightedIndex >= 0 && highlightedIndex < suggestions.length) {
      const highlightedElement = document.getElementById(`team-option-${highlightedIndex}`)
      highlightedElement?.scrollIntoView({ block: 'nearest' })
    }
  }, [highlightedIndex, suggestions.length])

  return (
    <div className="team-autocomplete" ref={containerRef}>
      <div className="autocomplete-input-wrapper">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => isOpen && setIsOpen(true)}
          placeholder={placeholder}
          disabled={disabled}
          className="autocomplete-input"
          autoComplete="off"
          aria-autocomplete="list"
          aria-expanded={isOpen}
          aria-controls="autocomplete-listbox"
        />
        {loading && <span className="autocomplete-spinner" title="Loading suggestions..." />}
      </div>

      {error && <div className="autocomplete-error">{error}</div>}

      {isOpen && (
        <ul className="autocomplete-dropdown" id="autocomplete-listbox" role="listbox">
          {suggestions.length > 0 ? (
            suggestions.map((team, index) => (
              <li
                key={team.team_id}
                id={`team-option-${index}`}
                onClick={() => handleSelectTeam(team)}
                className={`autocomplete-option ${index === highlightedIndex ? 'highlighted' : ''}`}
                role="option"
                aria-selected={index === highlightedIndex}
              >
                <div className="option-content">
                  {team.logo_url && (
                    <img src={team.logo_url} alt={team.name} className="option-logo" />
                  )}
                  <div className="option-text">
                    <div className="option-name">{team.name}</div>
                    {team.tag && <div className="option-tag">{team.tag}</div>}
                  </div>
                  {team.rating !== undefined && team.rating !== null && (
                    <div className="option-rating">{team.rating.toFixed(0)}</div>
                  )}
                </div>
              </li>
            ))
          ) : (
            <li className="autocomplete-empty">No teams found</li>
          )}
        </ul>
      )}
    </div>
  )
}

export default TeamAutocomplete
