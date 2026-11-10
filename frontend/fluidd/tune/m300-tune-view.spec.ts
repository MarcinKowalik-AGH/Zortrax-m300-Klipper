// SPDX-License-Identifier: GPL-3.0-only
// @vitest-environment jsdom
import Vue from 'vue'
import { shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Tune from '@/views/Tune.vue'
import BedMeshCard from '@/components/widgets/bedmesh/BedMeshCard.vue'
import BedMeshControls from '@/components/widgets/bedmesh/BedMeshControls.vue'
import M300PadContactMap from '@/components/widgets/bedmesh/M300PadContactMap.vue'
import M300PadMeshObserver from '@/components/common/M300PadMeshObserver.vue'
import AppBtn from '@/components/ui/AppBtn.vue'
import { SocketActions } from '@/api/socketActions'
import { getters } from '@/store/mesh/getters'
import type { MeshState } from '@/store/mesh/types'
import type { RootState } from '@/store/types'

vi.mock('@/api/socketActions', () => ({ SocketActions: {
  printerObjectsQuery: vi.fn().mockResolvedValue({ status: {} }),
  printerGcodeScript: vi.fn().mockResolvedValue({})
} }))

const slot = { template: '<section><slot /><slot name="menu" /></section>' }
const stubs = { 'v-row': slot, 'v-col': slot, 'v-card-text': slot, 'collapsable-card': slot }
const flush = async () => { await Vue.nextTick(); await Promise.resolve(); await Vue.nextTick() }

function setup (saved = false) {
  const names = ['front_right', 'front_left', 'center', 'rear_right', 'rear_left']
  const bounds = [[260, 0, 300, 51], [0, 0, 43, 51], [125, 125, 175, 175], [260, 262, 300, 305], [0, 260, 43, 305]]
  const regions = bounds.map((b, index) => ({
    name: names[index], bounds: b, center: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2], explicit: true
  }))
  const points = regions.flatMap(r => [r.center, [r.bounds[0], r.bounds[1]], [r.bounds[2], r.bounds[1]],
    [r.bounds[2], r.bounds[3]], [r.bounds[0], r.bounds[3]]])
  const printer = {
    webhooks: { state: 'ready' },
    m300_motion: { normal_control: true, ready: true, busy: false, state: 'IDLE', operation: 'HOME_ALL', session_token: 7, phase_id: 0 },
    m300_pad_mesh: {
      state: 'IDLE', phase: 'IDLE', busy: false, run_id: null, total_points: 25,
      points_measured: 0, last_error: '', last_attempt: null, result: null, plan_matches_run: false,
      contact_regions: regions, probe_points: points,
      travel: { configured_x: [0, 300], configured_y: [0, 305], fits: true }
    },
    toolhead: { homed_axes: '' },
    motion_report: { live_position: [0, 305, 5, 0] },
    bed_mesh: {
      profile_name: '', mesh_matrix: [[]], probed_matrix: [[]], mesh_min: [0, 0], mesh_max: [0, 0],
      profiles: saved ? { m300_pads: {
        points: [[0, 0.01, 0.02], [0.01, 0.02, 0.03], [0.02, 0.03, 0.04]],
        mesh_params: { min_x: 0, min_y: 0, max_x: 300, max_y: 305, algo: 'direct',
          x_count: 3, y_count: 3, mesh_x_pps: 0, mesh_y_pps: 0, tension: 0.2 }
      } } : {}
    }
  } as unknown as Klipper.PrinterState
  const state = Vue.observable({ printer: { printer }, mesh: {
    range: 0, wireframe: false, scale: 0, boxScale: 1, flatSurface: false, matrix: 'mesh_matrix'
  } as MeshState })
  const dispatch = vi.fn()
  const query = { printer: 'm300' }
  const push = vi.fn().mockResolvedValue(undefined)
  const mocks = {
    $typedState: state,
    $typedGetters: {
      'printer/getKlippyReady': true,
      'socket/getIsReady': true,
      'printer/getPrinterState': 'idle',
      'printer/getPrinterSettings': { bed_mesh: {}, m300_pad_mesh: {} },
      'mesh/getSupportsBedMesh': true,
      'mesh/getBedMeshProfiles': [],
      'printer/getSteppers': [],
      'printer/getProbe': null,
      'printer/getRunoutSensors': [],
      'printer/getSupportsBeacon': false,
      'printer/getHomedAxes': () => false,
      'wait/hasWait': () => false,
      get 'mesh/getCurrentMeshData' () {
        return getters.getCurrentMeshData(state.mesh, {}, state as unknown as RootState)
      }
    },
    $typedDispatch: dispatch,
    $waits: { onHomeAll: 'onHomeAll', onMeshCalibrate: 'onMeshCalibrate' },
    $vuetify: { breakpoint: { smAndDown: false } },
    $route: { name: 'home', query },
    $router: { push },
    $t: (value: string) => value
  }
  return { state, printer: state.printer.printer, mocks, push, dispatch, query }
}

function tune (f: ReturnType<typeof setup>) {
  return shallowMount(Tune, { mocks: f.mocks, stubs: {
    ...stubs,
    'bed-mesh-card': { template: '<div data-order="heatmap" />' },
    'm300-pad-contact-map': { template: '<div data-order="contact-map" />' }
  } })
}

const order = (wrapper: ReturnType<typeof tune>) => wrapper.findAll('[data-order]').wrappers.map(w => w.attributes('data-order'))

describe('M300 Tune entry, Home All and stable chart order', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each(['IDLE', 'PROBING', 'COMPLETE', 'FAILED'])('keeps heatmap first with no active surface in %s', state => {
    const f = setup()
    Object.assign(f.printer.m300_pad_mesh!, { state, busy: state === 'PROBING' })
    const wrapper = tune(f)
    expect(order(wrapper)).toEqual(['heatmap', 'contact-map'])
    expect(wrapper.attributes('data-m300-tune-revision')).toBe('TUNE-VIEW-2')
    wrapper.destroy()
  })

  it('reads current view data on manual entry without movement, heating, calibration or loading', async () => {
    const f = setup(true)
    const original = JSON.stringify(f.printer)
    const wrapper = tune(f)
    await flush()
    expect(SocketActions.printerObjectsQuery).toHaveBeenCalledExactlyOnceWith(
      { bed_mesh: null, m300_pad_mesh: null }, { suppressError: true }
    )
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    expect(JSON.stringify(f.printer)).toBe(original)
    expect(wrapper.text()).toContain('All homes the axes only')
    wrapper.destroy()
  })

  it('previews a saved profile before calibration without enabling compensation', () => {
    const f = setup(true)
    const wrapper = shallowMount(BedMeshCard, { propsData: { fullscreen: true }, mocks: f.mocks, stubs })
    expect(wrapper.text()).toContain('Saved profile: m300_pads (not active)')
    expect(wrapper.find('[data-mesh-summary]').text()).toContain('Range 0.0400 mm')
    expect(wrapper.findComponent({ name: 'BedMeshChart' }).exists()).toBe(true)
    expect(f.printer.bed_mesh?.mesh_matrix).toEqual([[]])
    expect(f.printer.bed_mesh?.profile_name).toBe('')
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('shows an explicit empty state, not a fabricated flat mesh, without measurements', () => {
    const f = setup()
    const wrapper = shallowMount(BedMeshCard, { propsData: { fullscreen: true }, mocks: f.mocks, stubs })
    expect(wrapper.find('[data-m300-mesh-empty]').text()).toContain('No current M300 mesh')
    expect(wrapper.findComponent({ name: 'BedMeshChart' }).exists()).toBe(false)
    wrapper.destroy()
  })

  it('shows contact geometry before All and adds the live nozzle after homing without measurements', async () => {
    const f = setup()
    const wrapper = shallowMount(M300PadContactMap, { mocks: f.mocks, stubs })
    expect(wrapper.findAll('[data-pad]')).toHaveLength(5)
    expect(wrapper.findAll('[data-point]')).toHaveLength(25)
    expect(wrapper.find('[data-nozzle]').exists()).toBe(false)
    expect(wrapper.findAll('[data-height]')).toHaveLength(0)
    f.printer.toolhead!.homed_axes = 'xyz'
    await flush()
    expect(wrapper.find('[data-nozzle]').exists()).toBe(true)
    expect(wrapper.findAll('[data-height]')).toHaveLength(0)
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('keeps the real All button as G28 and refreshes Tune after native homing completes', async () => {
    const f = setup(true)
    const wrapper = tune(f)
    const controls = shallowMount(BedMeshControls, { mocks: f.mocks, stubs })
    const all = controls.findAllComponents(AppBtn).wrappers.find(button => button.text().includes('app.general.btn.all'))
    expect(all).toBeDefined()
    all!.vm.$emit('click')
    expect(SocketActions.printerGcodeScript).toHaveBeenCalledExactlyOnceWith('G28', { wait: 'onHomeAll' })
    await flush()
    Object.assign(f.printer.m300_motion!, { state: 'HOMING', busy: true })
    await flush()
    expect(SocketActions.printerObjectsQuery).toHaveBeenCalledTimes(1)
    Object.assign(f.printer.m300_motion!, { state: 'IDLE', busy: false })
    await flush()
    expect(SocketActions.printerObjectsQuery).toHaveBeenCalledTimes(2)
    expect(order(wrapper)).toEqual(['heatmap', 'contact-map'])
    expect(f.printer.bed_mesh?.profile_name).toBe('')
    controls.destroy()
    wrapper.destroy()
  })

  it('uses the same view after BED_MESH routes to Tune, and never swaps cards while measuring', async () => {
    const f = setup()
    Object.assign(f.printer.m300_pad_mesh!, {
      state: 'PROBING', phase: 'HEATING', busy: true, run_id: 'a'.repeat(24)
    })
    const observer = shallowMount(M300PadMeshObserver, { mocks: f.mocks })
    expect(f.push).toHaveBeenCalledExactlyOnceWith({ name: 'tune', query: f.query })
    const wrapper = tune(f)
    expect(order(wrapper)).toEqual(['heatmap', 'contact-map'])
    Object.assign(f.printer.m300_pad_mesh!, { phase: 'PROBING', points_measured: 10 })
    await flush()
    expect(order(wrapper)).toEqual(['heatmap', 'contact-map'])
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    observer.destroy()
    wrapper.destroy()
  })

  it('does not add M300 reads or labels for an ordinary printer', () => {
    const f = setup()
    delete f.printer.m300_pad_mesh
    Reflect.deleteProperty(f.mocks.$typedGetters['printer/getPrinterSettings'], 'm300_pad_mesh')
    const wrapper = tune(f)
    expect(wrapper.find('[data-m300-tune-help]').exists()).toBe(false)
    expect(SocketActions.printerObjectsQuery).not.toHaveBeenCalled()
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    wrapper.destroy()
  })
})
