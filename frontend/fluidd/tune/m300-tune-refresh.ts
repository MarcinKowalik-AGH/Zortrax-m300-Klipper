// SPDX-License-Identifier: GPL-3.0-only
export const M300_TUNE_REVISION = 'TUNE-VIEW-2'
const objects = ['bed_mesh', 'm300_pad_mesh'] as const

export function supportsM300Tune (printer: Klipper.PrinterState, settings?: Klipper.SettingsState): boolean {
  return printer.m300_pad_mesh != null || settings?.m300_pad_mesh != null
}

type Fingerprints = Record<typeof objects[number], string | undefined>

function fingerprints (printer: Klipper.PrinterState): Fingerprints {
  return {
    bed_mesh: JSON.stringify(printer.bed_mesh),
    m300_pad_mesh: JSON.stringify(printer.m300_pad_mesh)
  }
}

export interface TuneRefreshOptions {
  available: () => boolean
  state: () => Klipper.PrinterState
  query: () => Promise<{ status: Partial<Klipper.PrinterState> }>
  publish: (status: Partial<Klipper.PrinterState>) => void | Promise<unknown>
}

/** Read-only, bounded snapshot on entry/homing completion, NOT periodic polling.
 * Never send G-code, load compensation or replace a newer subscription update.
 */
export class M300TuneRefresh {
  private generation = 0
  private request: object | null = null
  private queued = false

  constructor (private readonly options: TuneRefreshOptions) {}

  invalidate () {
    this.generation++
    this.request = null
    this.queued = false
  }

  async refresh (): Promise<void> {
    if (!this.options.available()) return
    if (this.request) {
      this.queued = true
      return
    }
    const token = this.request = {}
    const generation = this.generation
    const before = fingerprints(this.options.state())
    try {
      const response = await this.options.query()
      if (generation !== this.generation || !this.options.available() || !response?.status) return
      const current = fingerprints(this.options.state())
      const status = Object.fromEntries(objects.flatMap(key => {
        const value = response.status[key]
        return before[key] === current[key] && value != null &&
          typeof value === 'object' && !Array.isArray(value)
          ? [[key, value]]
          : []
      })) as Partial<Klipper.PrinterState>
      if (Object.keys(status).length) await this.options.publish(status)
    } catch {
      // Ordinary subscriptions remain authoritative. No automatic retry loop,
      // motion, calibration or compensating G-code on a failed snapshot.
    } finally {
      if (this.request === token) {
        this.request = null
        if (this.queued) {
          this.queued = false
          this.refresh().catch(() => undefined)
        }
      }
    }
  }
}
