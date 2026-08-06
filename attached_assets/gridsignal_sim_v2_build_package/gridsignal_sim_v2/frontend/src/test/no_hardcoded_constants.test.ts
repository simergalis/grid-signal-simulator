/**
 * no_hardcoded_constants.test.ts — Guard E (GS-DES-CFG-001 §E).
 *
 * Scans TypeScript source files for module-scope ALL_CAPS numeric constants.
 *
 * Tier 1 (BLOCKING) — src/subsystem/panels/*.ts
 *   These are site/physics values.  Hard-coding them makes the panel wrong
 *   for any configuration other than the demo scenario.
 *   Expected violations in Phase 0 (7):
 *     panels/turbineFleet.ts:39   PEAK_LOAD_MW = 23.95
 *     panels/generation.ts:20-21  RATED_MW = 25.0 · RAMP_MW_S = 0.2
 *     panels/storage.ts:23-24     RATED_MW = 18.0 · USABLE_MWH = 8.0
 *     panels/thermal.ts:22-23     DT_THERMAL_S = 90 · ALPHA_MAX = 0.20
 *   Do not fix any of them in Phase 0.
 *
 * Tier 2 (INFORMATIONAL) — all other src/**\/*.ts and src/**\/*.tsx files
 *   Layout constants, timing constants, and other numeric literals outside
 *   the panels directory.  Reported only; not blocking.
 *
 * Prohibited
 *   • Widening the name pattern to catch layout constants (would hide Tier 1).
 *   • Narrowing the pattern to exclude physics constants (would hide Tier 1).
 *   • Adding a file or name to the exemption list without a stated reason.
 *
 * Exemptions
 *   _TIER1_EXEMPTIONS lists (filename, constantName) pairs that are
 *   intentionally excluded from Tier 1 with a documented reason.
 *   Currently empty.
 */

import { readFileSync } from 'node:fs'
import * as path from 'node:path'
import * as fs from 'node:fs'
import { describe, it, expect } from 'vitest'

// ── Configuration ──────────────────────────────────────────────────────────────

// The frontend src/ directory relative to this test file.
// test/ → ../ → src/
const SRC_DIR = path.resolve(__dirname, '..')

// Tier 1 scan target: all .ts files in src/subsystem/panels/
const PANELS_DIR = path.join(SRC_DIR, 'subsystem', 'panels')

// Tier 2 scan target: all .ts and .tsx in src/ (excluding panels/ — already Tier 1)
const TIER2_EXTENSIONS = ['.ts', '.tsx']

// Pattern: module-scope ALL_CAPS constant with a numeric literal.
// Match: lines starting with "const NAME = NUMBER" (no leading whitespace).
// ALL_CAPS means: starts with uppercase letter, rest uppercase letters/digits/underscores.
// String literals (colour hex values) start with ' or " — excluded automatically
// because the value group only matches digits, dots, and leading minus.
const ALLCAPS_NUMERIC_RE = /^const ([A-Z][A-Z0-9_]+)\s*=\s*(-?\d+(?:\.\d+)?)\s*(?:\/\/.*)?$/

// Exemptions: [(filename (basename), constantName, reason)]
// Each exemption must document WHY the constant is permitted.
const _TIER1_EXEMPTIONS: Array<[string, string, string]> = [
  // No exemptions.  Any addition requires an explicit decision record.
]

// ── Scanner ────────────────────────────────────────────────────────────────────

interface Hit {
  relPath: string
  line: number
  name: string
  value: string
}

function scanFile(filePath: string, srcRoot: string): Hit[] {
  const content = readFileSync(filePath, 'utf-8')
  const lines = content.split('\n')
  const relPath = path.relative(srcRoot, filePath).replace(/\\/g, '/')
  const hits: Hit[] = []

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const m = ALLCAPS_NUMERIC_RE.exec(line)
    if (m) {
      hits.push({ relPath, line: i + 1, name: m[1], value: m[2] })
    }
  }
  return hits
}

function walkDir(dir: string, extensions: string[]): string[] {
  const results: string[] = []
  if (!fs.existsSync(dir)) return results
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  for (const entry of entries) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      results.push(...walkDir(full, extensions))
    } else if (entry.isFile() && extensions.some(ext => entry.name.endsWith(ext))) {
      results.push(full)
    }
  }
  return results.sort()
}

function isTier1Exempt(relPath: string, name: string): boolean {
  const basename = path.basename(relPath)
  return _TIER1_EXEMPTIONS.some(
    ([fn, n]) => (fn === basename || fn === relPath) && n === name
  )
}

// ── Tests ──────────────────────────────────────────────────────────────────────

describe('Guard E — no hardcoded site constants', () => {

  it('Tier 1: no module-scope ALL_CAPS numeric constants in panels (BLOCKING)', () => {
    const panelFiles = walkDir(PANELS_DIR, ['.ts'])
    const violations: Hit[] = []

    for (const file of panelFiles) {
      const hits = scanFile(file, SRC_DIR)
      for (const h of hits) {
        if (!isTier1Exempt(h.relPath, h.name)) {
          violations.push(h)
        }
      }
    }

    if (violations.length > 0) {
      const lines = [
        '\nGuard E Tier 1 — module-scope ALL_CAPS numeric constants in panels:',
        '(These must be derived from tick payload or site_parameters; not hardcoded.)',
        '',
      ]
      for (const v of violations) {
        lines.push(`  ${v.relPath}:${v.line}  ${v.name} = ${v.value}`)
      }
      lines.push(`\n  Total Tier 1 violations: ${violations.length}`)
      console.error(lines.join('\n'))
    }

    // Phase 0: 7 violations expected and documented above.
    // This assertion will fail, which is the correct Phase 0 behaviour.
    expect(violations, [
      'Guard E Tier 1 failed.',
      'Module-scope ALL_CAPS numeric constants found in panels/.',
      'See stderr output for the list.',
      'Fix these in Phases 3, 5, and 6 per GS-DES-CFG-001.',
    ].join(' ')).toHaveLength(0)
  })

  it('Tier 2 (informational): report ALL_CAPS numeric constants outside panels', () => {
    // Collect all TS/TSX files under src/ that are NOT in panels/
    const allFiles = walkDir(SRC_DIR, TIER2_EXTENSIONS)
    const tier2Files = allFiles.filter(f => !f.startsWith(PANELS_DIR + path.sep))

    const backlog: Hit[] = []
    for (const file of tier2Files) {
      // Skip this guard file itself and setup files
      if (file.includes('no_hardcoded_constants')) continue
      backlog.push(...scanFile(file, SRC_DIR))
    }

    if (backlog.length > 0) {
      const lines = [
        '\nGuard E Tier 2 backlog — ALL_CAPS numeric constants outside panels/:',
        '(Informational only.  Review whether each should be derived from the catalogue.)',
        '',
      ]
      for (const v of backlog) {
        lines.push(`  ${v.relPath}:${v.line}  ${v.name} = ${v.value}`)
      }
      lines.push(`\n  Total Tier 2 constants: ${backlog.length}`)
      console.log(lines.join('\n'))
    } else {
      console.log('\nGuard E Tier 2 backlog: empty.')
    }

    // Tier 2 is informational — this test always passes.
    expect(true).toBe(true)
  })

})
