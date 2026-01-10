# Frontend Tests

This directory contains comprehensive tests for the React frontend application using Vitest and React Testing Library.

## Test Structure

The tests are organized in `src/App.test.tsx` and cover:

### 1. Rendering Tests
- Main heading renders correctly
- Team input fields are present
- Check button is visible
- Team #1 input has autofocus

### 2. Input Validation Tests
- Error shown when submitting with empty teams
- Error shown when only Team #1 is filled
- Error shown when only Team #2 is filled
- Whitespace-only input is treated as empty

### 3. API Integration Tests
- Fetch is called with correct parameters
- Loading state displayed during API call
- HTTP errors are handled (e.g., 500 errors)
- Network errors are handled gracefully

### 4. Results Display Tests
- Statistics display when data is returned
- Team tags are displayed correctly
- Team IDs are displayed correctly
- Ratings are displayed correctly

### 5. Keyboard Input Tests
- Form submits when Enter is pressed in Team #1 input
- Form submits when Enter is pressed in Team #2 input

### 6. Delta Display Tests
- Delta values are formatted with one decimal place
- "IN PRIME" label shown for delta > 15
- "RUINERS" label shown for delta < -15

## Running Tests

### Run tests in watch mode
```bash
npm test
```

### Run tests once
```bash
npm test -- --run
```

### Run tests with UI
```bash
npm run test:ui
```

### Run specific test file
```bash
npm test -- src/App.test.tsx
```

### Run specific test suite
```bash
npm test -- --grep "Input Validation"
```

## Test Coverage

The test suite covers:
- ✅ Component rendering
- ✅ User interactions (typing, clicking)
- ✅ Form validation
- ✅ API calls and error handling
- ✅ Data display logic
- ✅ Conditional styling and labels

## Dependencies

- **vitest**: Fast unit testing framework
- **@testing-library/react**: React component testing utilities
- **@testing-library/user-event**: User interaction simulation
- **@testing-library/jest-dom**: Custom DOM matchers
- **jsdom**: DOM implementation for Node.js

## Mocking

API calls are mocked using `vi.fn()` to test:
- Correct parameters passed to fetch
- Loading states
- Success responses
- Error handling (HTTP and network errors)

## Best Practices

1. Tests use semantic queries (getByRole, getByLabelText) instead of implementation details
2. User interactions are simulated with @testing-library/user-event
3. Async operations use waitFor for proper timing
4. Fetch is mocked to avoid real API calls
5. Each test is independent and can run in any order
