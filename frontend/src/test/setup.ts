import '@testing-library/jest-dom'

// Treat console warnings as test failures (except React development warnings)
// Note: We don't fail on console.error since some tests intentionally trigger error handling
const originalWarn = console.warn
const REACT_WARNING_PATTERNS = [
    'An update to App inside a test was not wrapped in act(...)',
    'useLayoutEffect does nothing on the server',
    'Warning: ReactDOM.render',
    'Not implemented: HTMLFormElement.prototype.submit'
]

beforeAll(() => {
    console.warn = (...args: unknown[]) => {
        const message = args.join(' ')
        // Allow React development warnings and other internal warnings
        const isReactWarning = REACT_WARNING_PATTERNS.some(pattern => message.includes(pattern))

        originalWarn(...args)

        if (!isReactWarning) {
            throw new Error(`Test failed due to console.warn: ${message}`)
        }
    }
})

afterAll(() => {
    console.warn = originalWarn
});
