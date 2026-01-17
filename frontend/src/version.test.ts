import { describe, expect, it } from 'vitest'
import { VERSION } from './version'

describe('Version', () => {
    it('should export a version string', () => {
        expect(VERSION).toBeDefined()
        expect(typeof VERSION).toBe('string')
    })

    it('should have a valid semantic version format', () => {
        // Match semantic versioning pattern: major.minor.patch
        const semverPattern = /^\d+\.\d+\.\d+$/
        expect(VERSION).toMatch(semverPattern)
    })

    it('should be 0.1.0', () => {
        expect(VERSION).toBe('0.1.0')
    })
})
