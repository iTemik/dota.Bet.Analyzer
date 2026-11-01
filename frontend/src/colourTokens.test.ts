import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// vitest blanks CSS imports, so read the files from disk. index.css is the one place that defines colour tokens.
const SRC = join(process.cwd(), 'src')

/** Reads every .css and .tsx file under src except tests and index.css, keyed by path relative to src. */
function readSources(): Record<string, string> {
    const files: Record<string, string> = {}
    for (const name of readdirSync(SRC, { recursive: true }) as string[]) {
        const path = name.split('\\').join('/')
        if (!/\.(css|tsx)$/.test(path) || path.endsWith('.test.tsx') || path === 'index.css') continue
        files[path] = readFileSync(join(SRC, name), 'utf8')
    }
    return files
}

const sources = readSources()

// Hex colours (#fff, #ffffff, #ffffff80) and rgb()/rgba()/hsl()/hsla() calls.
const COLOUR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/g

/** Lists "file:line: literal" for each colour literal in the given sources. */
function findColourLiterals(files: Record<string, string>): string[] {
    const found: string[] = []
    for (const [path, text] of Object.entries(files)) {
        text.split('\n').forEach((line, index) => {
            for (const match of line.matchAll(COLOUR_LITERAL)) {
                found.push(`${path}:${index + 1}: ${match[0]}`)
            }
        })
    }
    return found
}

describe('colour tokens', () => {
    it('reads the stylesheets and components', () => {
        expect(Object.keys(sources)).toContain('App.css')
        expect(Object.keys(sources)).toContain('App.tsx')
        expect(Object.keys(sources)).toContain('components/TeamAutocomplete.css')
        expect(Object.keys(sources)).not.toContain('index.css')
    })

    it('finds hex and rgb/hsl literals', () => {
        expect(
            findColourLiterals({ 'a.css': '.x { color: #fff; }\n.y { background: rgba(0, 0, 0, 0.5); border: hsl(0 0% 0%); }' }),
        ).toEqual(['a.css:1: #fff', 'a.css:2: rgba(', 'a.css:2: hsl('])
        expect(findColourLiterals({ 'b.css': '.x { color: var(--accent); }' })).toEqual([])
    })

    it('uses no colour literals outside index.css (add a token there and use var(--token))', () => {
        expect(findColourLiterals(sources)).toEqual([])
    })
})
