import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
    plugins: [react()],
    test: {
        globals: true,
        environment: 'jsdom',
        setupFiles: './src/test/setup.ts',
        reporters: ['default', 'junit'],
        outputFile: {
            junit: '../test-results/frontend/junit.xml',
        },
    },
})
