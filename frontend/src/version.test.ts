import { describe, expect, it } from 'vitest'
import { VERSION } from './version'

describe('Frontend Version Management', () => {
    it('should export a VERSION constant', () => {
        expect(VERSION).toBeDefined()
        expect(typeof VERSION).toBe('string')
    })

    it('should be in MAJOR.MINOR format', () => {
        const versionPattern = /^\d+\.\d+$/
        expect(VERSION).toMatch(versionPattern)
    })

    it('should have major and minor versions only', () => {
        const parts = VERSION.split('.')
        expect(parts).toHaveLength(2)
        expect(Number(parts[0])).toBeGreaterThanOrEqual(0)
        expect(Number(parts[1])).toBeGreaterThanOrEqual(0)
    })

    it('should have valid numeric components', () => {
        const parts = VERSION.split('.')
        parts.forEach(part => {
            expect(Number.isNaN(Number(part))).toBe(false)
        })
    })
})
