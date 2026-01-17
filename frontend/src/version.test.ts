import { describe, expect, it } from 'vitest'
import { VERSION } from './version'

describe('Frontend Version Management', () => {
    it('should export a VERSION constant', () => {
        expect(VERSION).toBeDefined()
        expect(typeof VERSION).toBe('string')
    })

    it('should be in semantic version format (X.Y.Z)', () => {
        const semverPattern = /^\d+\.\d+\.\d+$/
        expect(VERSION).toMatch(semverPattern)
    })

    it('should have major, minor, and patch versions', () => {
        const parts = VERSION.split('.')
        expect(parts).toHaveLength(3)
        expect(Number(parts[0])).toBeGreaterThanOrEqual(0)
        expect(Number(parts[1])).toBeGreaterThanOrEqual(0)
        expect(Number(parts[2])).toBeGreaterThanOrEqual(0)
    })

    it('should allow DEV as patch version', () => {
        const versionPattern = /^\d+\.\d+\.(\d+|DEV)$/
        expect(VERSION).toMatch(versionPattern)
    })

    it('should be greater than or equal to 1.0.0', () => {
        const [major, minor, patch] = VERSION.split('.')
        const majorNum = Number(major)
        const minorNum = Number(minor)
        expect(majorNum).toBeGreaterThanOrEqual(1)
    })
})
