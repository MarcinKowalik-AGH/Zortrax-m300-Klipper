// SPDX-License-Identifier: GPL-3.0-only
const internalMacros = new Set([
  'ZORTRAX_PRINT', 'ZORTRAX_OLED_PERF', 'ZORTRAX_TEST_PRINT_FAN',
  'ZORTRAX_TEST_HOTEND_FAN', 'PID_ARM', 'PID_HEAT_CHECK', 'PID_STOP'
])

export function m300MacroHidden (name: string, model: unknown): boolean {
  if (model !== 'M300_CLASSIC') return false
  const key = name.toUpperCase()
  return internalMacros.has(key) || /^(?:TEST_M300_|TEST_ZORTRAX_|ZORTRAX_TEST_)/.test(key)
}

// An explicit valid custom category is preserved by the getter.
export function m300MacroDefaultCategory (name: string, model: unknown): string | undefined {
  if (model !== 'M300_CLASSIC' || m300MacroHidden(name, model)) return
  const key = name.toUpperCase()
  if (key.startsWith('ZORTRAX_')) return 'ZORTRAX M300'
  if (key.startsWith('PID_') || ['START_PRINT', 'END_PRINT', 'BED_MESH', 'PAUSE',
    'RESUME', 'CANCEL_PRINT', 'M600', 'M601', 'COOLDOWN', 'PRINT_CONTROL_STATUS'].includes(key)) {
    return 'Klipper'
  }
}
