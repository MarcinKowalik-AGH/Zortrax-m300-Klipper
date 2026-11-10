// SPDX-License-Identifier: GPL-3.0-only
import { describe, expect, it, vi } from 'vitest'
import { M300TuneRefresh, supportsM300Tune } from './m300-tune-refresh'

const deferred = <T>() => {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((_resolve, _reject) => { resolve = _resolve; reject = _reject })
  return { promise, resolve, reject }
}

function fixture () {
  let available = true
  const printer = { bed_mesh: { profile_name: '', mesh_matrix: [[]] } } as unknown as Klipper.PrinterState
  const pending = deferred<{ status: Partial<Klipper.PrinterState> }>()
  const query = vi.fn(() => pending.promise)
  const publish = vi.fn()
  const refresh = new M300TuneRefresh({
    state: () => printer,
    available: () => available,
    query,
    publish
  })
  return { printer, pending, query, publish, refresh, disconnect: () => { available = false } }
}

const response = () => ({
  status: {
    bed_mesh: { profile_name: '', mesh_matrix: [[]], profiles: {} },
    m300_pad_mesh: { state: 'IDLE', busy: false, total_points: 25, points_measured: 0 }
  } as unknown as Partial<Klipper.PrinterState>
})

describe('read-only M300 Tune snapshots', () => {
  it('recognizes the configured service before its first status arrives', () => {
    expect(supportsM300Tune({} as Klipper.PrinterState)).toBe(false)
    expect(supportsM300Tune({ m300_pad_mesh: {} } as unknown as Klipper.PrinterState)).toBe(true)
    expect(supportsM300Tune({} as Klipper.PrinterState, { m300_pad_mesh: {} } as Klipper.SettingsState)).toBe(true)
  })

  it('refreshes the two view objects and nothing else', async () => {
    const f = fixture()
    const work = f.refresh.refresh()
    const reply = response()
    Object.assign(reply.status, { extruder: { target: 260 }, toolhead: { homed_axes: 'xyz' } })
    f.pending.resolve(reply)
    await work
    expect(f.publish).toHaveBeenCalledExactlyOnceWith({
      bed_mesh: reply.status.bed_mesh, m300_pad_mesh: reply.status.m300_pad_mesh
    })
    expect(f.printer.bed_mesh?.profile_name).toBe('')
  })

  it('does not replace a newer mesh activation from the subscription', async () => {
    const f = fixture()
    const work = f.refresh.refresh()
    f.printer.bed_mesh!.profile_name = 'm300_pads'
    f.printer.bed_mesh!.mesh_matrix = [[0, 0], [0, 0]]
    f.pending.resolve(response())
    await work
    expect(f.publish).toHaveBeenCalledExactlyOnceWith({ m300_pad_mesh: response().status.m300_pad_mesh })
  })

  it('does not overwrite a measurement that started during the query', async () => {
    const f = fixture()
    const work = f.refresh.refresh()
    f.printer.m300_pad_mesh = { state: 'PROBING', busy: true } as NonNullable<Klipper.PrinterState['m300_pad_mesh']>
    f.pending.resolve(response())
    await work
    expect(f.publish).toHaveBeenCalledExactlyOnceWith({ bed_mesh: response().status.bed_mesh })
  })

  it('does not restore a profile deleted during the query', async () => {
    const f = fixture()
    f.printer.bed_mesh!.profiles = { m300_pads: {} as Klipper.BedMeshProfileState }
    const work = f.refresh.refresh()
    f.printer.bed_mesh!.profiles = {}
    f.pending.resolve(response())
    await work
    expect(f.publish.mock.calls[0][0]).not.toHaveProperty('bed_mesh')
  })

  it.each(['invalidate', 'disconnect'] as const)('ignores a late reply after %s', async action => {
    const f = fixture()
    const work = f.refresh.refresh()
    if (action === 'invalidate') f.refresh.invalidate()
    else f.disconnect()
    f.pending.resolve(response())
    await work
    expect(f.publish).not.toHaveBeenCalled()
  })

  it('coalesces repeated refresh requests to one bounded follow-up', async () => {
    const f = fixture()
    const next = deferred<{ status: Partial<Klipper.PrinterState> }>()
    f.query.mockImplementationOnce(() => f.pending.promise).mockImplementationOnce(() => next.promise)
    const work = f.refresh.refresh()
    for (let i = 0; i < 100; i++) await f.refresh.refresh()
    expect(f.query).toHaveBeenCalledTimes(1)
    f.pending.resolve(response())
    await work
    expect(f.query).toHaveBeenCalledTimes(2)
    next.resolve(response())
    await Promise.resolve()
    await Promise.resolve()
    expect(f.query).toHaveBeenCalledTimes(2)
  })

  it('keeps a reconnect request independent of a late previous connection', async () => {
    const f = fixture()
    const old = f.refresh.refresh()
    f.refresh.invalidate()
    const next = deferred<{ status: Partial<Klipper.PrinterState> }>()
    f.query.mockImplementationOnce(() => next.promise)
    const current = f.refresh.refresh()
    f.pending.resolve(response())
    await old
    expect(f.publish).not.toHaveBeenCalled()
    next.resolve(response())
    await current
    expect(f.publish).toHaveBeenCalledTimes(1)
  })

  it('does not query while disconnected and does not retry failed reads automatically', async () => {
    const f = fixture()
    const work = f.refresh.refresh()
    f.pending.reject(new Error('offline'))
    await work
    expect(f.query).toHaveBeenCalledTimes(1)
    expect(f.publish).not.toHaveBeenCalled()
    f.disconnect()
    await f.refresh.refresh()
    expect(f.query).toHaveBeenCalledTimes(1)
  })

  it('rejects malformed object payloads', async () => {
    const f = fixture()
    const work = f.refresh.refresh()
    f.pending.resolve({ status: { bed_mesh: null, m300_pad_mesh: [] } as unknown as Klipper.PrinterState })
    await work
    expect(f.publish).not.toHaveBeenCalled()
  })
})
