# Dota.Bet.Analyzer Frontend

A Vite + React + TypeScript frontend application for analyzing Dota 2 team statistics.

## Features

- **Team Statistics Form**: Enter two team names and fetch comparative statistics
- **Modern UI**: Built with React and styled with CSS
- **Type-Safe**: Full TypeScript support
- **API Integration**: Proxies requests to the Flask backend at `/statistics`

## Getting Started

### Prerequisites

- Node.js (LTS recommended)
- npm

### Installation

From the `frontend` directory:

```bash
npm install
```

### Development

Start the development server:

```bash
npm run dev
```

The frontend will be available at `http://localhost:5173` by default.

The development server includes a proxy for API requests:
- `/statistics` requests are forwarded to `http://localhost:5000` (Flask backend)

### Building for Production

```bash
npm run build
```

The production build will be output to the `dist/` directory.

### Preview Production Build

```bash
npm run preview
```

## Architecture

### Main Component (App.tsx)

The `App` component provides:
- Two text inputs for team names (Team #1 and Team #2)
- A "Check Statistics" button
- Fetches from `/statistics?team=team1&team=team2`
- Displays results or error messages
- Loading state management

### Styling (App.css)

- Gradient background with purple theme
- Responsive form layout
- Error message styling
- Results display with formatted JSON

## API Integration

The frontend expects the backend to provide a `/statistics` endpoint that accepts query parameters:

```
GET /statistics?team=team1&team=team2
```


## Project Structure

```
frontend/
├── src/
│   ├── App.tsx         # Main component with form and logic
│   ├── App.css         # Styling
│   ├── main.tsx        # Entry point
│   ├── index.css       # Global styles
│   └── assets/         # Static assets
├── index.html          # HTML template
├── vite.config.ts      # Vite configuration with API proxy
├── tsconfig.json       # TypeScript configuration
└── package.json        # Dependencies and scripts
```

## Development Tips

- The frontend automatically reloads when you make changes (HMR - Hot Module Replacement)
- Check the browser console for any errors
- Ensure the Flask backend is running on port 5000 for API calls to work
- TypeScript provides real-time type checking in your editor

### ESLint Configuration

For enhanced TypeScript linting with type-aware rules, you can configure ESLint with type checking enabled:

```js
// eslint.config.js
{
  files: ['**/*.{ts,tsx}'],
  extends: [
    // Other configs...

    // Remove tseslint.configs.recommended and replace with this
    tseslint.configs.recommendedTypeChecked,
    // Alternatively, use this for stricter rules
    tseslint.configs.strictTypeChecked,
    // Optionally, add this for stylistic rules
    tseslint.configs.stylisticTypeChecked,

    // Other configs...
  ],
  languageOptions: {
    parserOptions: {
      project: ['./tsconfig.node.json', './tsconfig.app.json'],
      tsconfigRootDir: import.meta.dirname,
    },
    // other options...
  },
},
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
