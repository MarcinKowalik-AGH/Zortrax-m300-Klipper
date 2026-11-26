// SPDX-License-Identifier: GPL-3.0-only
// @vitest-environment jsdom
import Vue from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import M300PadMeshObserver from '@/components/common/M300PadMeshObserver.vue'
import { SocketActions } from '@/api/socketActions'

vi.mock('@/api/socketActions', () => ({ SocketActions: { printerGcodeScript: vi.fn() } }))

function fixture (job = 'standby', active = false) {
  const printer = Vue.observable({
    m300_pad_mesh: {
      run_id: 'a'.repeat(24),
      state: 'PROBING',
      phase: 'HEATING',
      busy: true,
      points_measured: 0,
      total_points: 25,
      last_error: '',
      last_attempt: null
    },
    print_stats: { state: job },
    virtual_sdcard: { is_active: active }
  })
  const ready = Vue.observable({ 'printer/getKlippyReady': true })
  const route = Vue.observable({ name: 'home', query: { printer: 'm300' } })
  const push = vi.fn().mockResolvedValue(undefined)
  const wrapper = shallowMount(M300PadMeshObserver, {
    mocks: {
      $typedState: { printer: { printer } },
      $typedGetters: ready,
      $route: route,
      $router: { push },
      $typedDispatch: vi.fn()
    }
  })
  return { wrapper, printer, ready, route, push }
}

describe('M300 mesh navigation while a print owns the UI', () => {
  it('still opens Tune once for an independent mesh operation', async () => {
    const ctx = fixture()
    expect(ctx.push).toHaveBeenCalledExactlyOnceWith({ name: 'tune', query: ctx.route.query })
    ctx.route.name = 'console'
    ctx.printer.m300_pad_mesh.phase = 'PROBING'
    await Vue.nextTick()
    expect(ctx.push).toHaveBeenCalledTimes(1)
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    ctx.wrapper.destroy()
  })

  it.each([['printing', true], ['printing', false], ['paused', false], ['standby', true]])(
    'keeps the job view when state=%s and virtual SD active=%s', (state, active) => {
      const ctx = fixture(String(state), Boolean(active))
      expect(ctx.push).not.toHaveBeenCalled()
      expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
      ctx.wrapper.destroy()
    })

  it('does not replay a suppressed mesh run when the print finishes', async () => {
    const ctx = fixture('printing', true)
    ctx.route.name = 'console'
    ctx.printer.virtual_sdcard.is_active = false
    ctx.printer.print_stats.state = 'complete'
    await Vue.nextTick()
    expect(ctx.push).not.toHaveBeenCalled()
    ctx.printer.m300_pad_mesh.run_id = 'b'.repeat(24)
    await Vue.nextTick()
    expect(ctx.push).toHaveBeenCalledExactlyOnceWith({ name: 'tune', query: ctx.route.query })
    ctx.wrapper.destroy()
  })

  it('keeps the selected view across a reconnect during printing', async () => {
    const ctx = fixture('printing', true)
    ctx.ready['printer/getKlippyReady'] = false
    await Vue.nextTick()
    ctx.ready['printer/getKlippyReady'] = true
    await Vue.nextTick()
    expect(ctx.push).not.toHaveBeenCalled()
    ctx.wrapper.destroy()
  })
})
