import { describe, expect, it } from 'vitest'
import { VERSION } from './version'

describe('Version', () => {
    it('should export a version string', () => {
        expect(VERSION).toBeDefined()
        expect(typeof VERSION).toBe('string')
    })

    it('should be in format X.Y.Z', () => {
        // Match semantic versioning pattern: major.minor.patch
        const semverPattern = /^\d+\.\d+\.\d+$/
        expect(VERSION).toMatch(semverPattern)
    })
})
