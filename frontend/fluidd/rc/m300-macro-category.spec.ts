// SPDX-License-Identifier: GPL-3.0-only
import { describe, expect, it } from 'vitest'
import { m300MacroDefaultCategory, m300MacroHidden } from '@/util/m300-macro-category'
import { getters } from '@/store/macros/getters'
import type { MacrosState } from '@/store/macros/types'
import type { RootState } from '@/store/types'

const names = ['ZORTRAX_HEAT_PLATFORM', 'ZORTRAX_FULL_PLATFORM_PREHEAT', 'START_PRINT', 'END_PRINT']

function macros (stored: MacrosState['stored'] = [], model = 'M300_CLASSIC') {
  const state: MacrosState = {
    stored,
    expanded: [],
    categories: [{ id: 'z', name: 'ZORTRAX M300' }, { id: 'k', name: 'Klipper' }, { id: 'c', name: 'Custom' }]
  }
  const printer = {
    m300_mcu: { model },
    configfile: { settings: {} },
    ...Object.fromEntries(names.map(name => ['gcode_macro ' + name, {}]))
  }
  const root = { printer: { printer } } as unknown as RootState
  return { state, root, get: () => getters.getMacros(state, {}, root) }
}

describe('M300 defaults for newly introduced macros', () => {
  it('groups the two platform macros under Zortrax and Start/End under Klipper without stored rows', () => {
    const ctx = macros()
    expect(ctx.get().map(macro => [macro.name, macro.categoryId]))
      .toEqual(names.map(name => [name, name.startsWith('ZORTRAX_') ? 'z' : 'k']))
    expect(ctx.state.stored).toEqual([])
  })

  it('repairs uncategorized and orphaned preferences while preserving visibility and color', () => {
    const stored = names.map((name, i) => ({ name, categoryId: i % 2 ? 'removed' : '0', visible: false, color: 'purple' }))
    const ctx = macros(stored)
    const before = JSON.stringify(ctx.state)
    expect(ctx.get().every(macro => macro.categoryId !== '0' && !macro.visible && macro.color === 'purple')).toBe(true)
    expect(JSON.stringify(ctx.state)).toBe(before)
  })

  it('preserves an explicit valid custom category and alias', () => {
    const ctx = macros([{ name: names[0], categoryId: 'c', visible: true, alias: 'My bed' }])
    expect(ctx.get()[0]).toMatchObject({ categoryId: 'c', category: { name: 'Custom' }, alias: 'My bed' })
  })

  it('does not change another printer or invent a missing category', () => {
    expect(macros([], 'OTHER').get().every(macro => macro.categoryId === '0')).toBe(true)
    const ctx = macros()
    ctx.state.categories = []
    expect(ctx.get().every(macro => macro.categoryId === '0')).toBe(true)
  })
})

describe('RC1 production macro surface', () => {
  it.each(['ZORTRAX_OLED_BRIGHTNESS', 'ZORTRAX_LED_BRIGHTNESS', 'ZORTRAX_PROCEDURE', 'ZORTRAX_DIAGNOSTICS'])(
    'exposes %s in the Zortrax group', name => {
      expect(m300MacroDefaultCategory(name, 'M300_CLASSIC')).toBe('ZORTRAX M300')
      expect(m300MacroHidden(name, 'M300_CLASSIC')).toBe(false)
    }
  )
  it.each(['TEST_ZORTRAX_XY', 'TEST_M300_STATUS', 'ZORTRAX_OLED_PERF', 'ZORTRAX_PRINT'])(
    'hides %s without affecting another printer', name => {
      expect(m300MacroHidden(name, 'M300_CLASSIC')).toBe(true)
      expect(m300MacroHidden(name, 'OTHER')).toBe(false)
      expect(m300MacroDefaultCategory(name, 'M300_CLASSIC')).toBeUndefined()
    }
  )
  it('overrides a stale visible flag without mutating preferences', () => {
    const ctx = macros([{ name: 'TEST_ZORTRAX_XY', categoryId: 'c', visible: true }])
    const root = ctx.root as unknown as { printer: { printer: Record<string, unknown> } }
    root.printer.printer['gcode_macro TEST_ZORTRAX_XY'] = {}
    const before = JSON.stringify(ctx.state)
    expect(ctx.get().find(m => m.name === 'TEST_ZORTRAX_XY')?.visible).toBe(false)
    expect(JSON.stringify(ctx.state)).toBe(before)
  })
  it('keeps OEM fan service and unrelated user tests available', () => {
    expect(m300MacroHidden('ZORTRAX_FAN_TEST_START', 'M300_CLASSIC')).toBe(false)
    expect(m300MacroHidden('MY_TEST', 'M300_CLASSIC')).toBe(false)
  })
})
