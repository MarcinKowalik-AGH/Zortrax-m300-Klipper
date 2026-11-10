// SPDX-License-Identifier: GPL-3.0-only
// @vitest-environment jsdom
import Vue from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import Tune from '@/views/Tune.vue'
import BedMeshControls from '@/components/widgets/bedmesh/BedMeshControls.vue'
import M300PadMeshStatus from '@/components/widgets/bedmesh/M300PadMeshStatus.vue'
import { SocketActions } from '@/api/socketActions'
import { isM300PadMeshAccepted, readM300PadMesh } from './m300-pad-mesh'
import { readM300ContactMap } from './m300-pad-contact-map'

vi.mock('@/api/socketActions', () => ({ SocketActions: { printerGcodeScript: vi.fn() } }))

const idle = () => ({
  state: 'IDLE',
  phase: 'IDLE',
  busy: false,
  run_id: null,
  points_measured: 0,
  total_points: 25,
  result: null,
  last_attempt: null,
  last_error: '',
  targets: null
})

function fixture () {
  const regions = [
    { name: 'front_right', center: [285, 15], bounds: [260, 0, 300, 51], explicit: true },
    { name: 'front_left', center: [15, 15], bounds: [0, 0, 43, 51], explicit: true },
    { name: 'center', center: [150, 150], bounds: [125, 125, 175, 175], explicit: true },
    { name: 'rear_right', center: [285, 290], bounds: [260, 262, 300, 305], explicit: true },
    { name: 'rear_left', center: [15, 290], bounds: [0, 260, 43, 305], explicit: true }
  ]
  return {
    webhooks: { state: 'ready' },
    toolhead: { homed_axes: '' },
    m300_pad_mesh: {
      ...idle(),
      contact_regions: regions,
      probe_points: regions.flatMap(region => {
        const [x0, y0, x1, y1] = region.bounds
        return [region.center, [x0, y0], [x1, y0], [x1, y1], [x0, y1]]
      }),
      measurements: [],
      plan_matches_run: false,
      travel: { configured_x: [0, 300], configured_y: [0, 305], fits: true }
    },
    m300_motion: {
      normal_control: true,
      ready: true,
      busy: false,
      state: 'READY',
      operation: '',
      session_token: 0,
      phase_id: 'IDLE'
    },
    bed_mesh: { profile_name: '', mesh_matrix: [[]], probed_matrix: [[]], profiles: {} },
    extruder: { temperature: 20.2, target: 0 },
    heater_bed: { temperature: 20.4, target: 0 }
  }
}

function context (source = fixture()) {
  const state = Vue.observable({ printer: { printer: source }, mesh: { matrix: 'mesh_matrix', scale: 0, boxScale: 1, wireframe: false, flatSurface: false } })
  return {
    source,
    mocks: {
      $typedState: state,
      $typedDispatch: vi.fn(),
      $typedGetters: {
        'printer/getKlippyReady': true,
        'printer/getPrinterState': 'idle',
        'printer/getHomedAxes': (axes: string) => axes.split('').every(axis => source.toolhead.homed_axes.includes(axis)),
        'printer/getPrinterSettings': {},
        'printer/getIsManualProbeActive': false,
        'printer/getSteppers': [],
        'printer/getProbe': null,
        'printer/getRunoutSensors': [],
        'printer/getSupportsBeacon': false,
        'mesh/getSupportsBedMesh': true,
        'mesh/getBedMeshProfiles': [],
        'wait/hasWait': () => false
      },
      $waits: { onHomeAll: 'onHomeAll', onMeshCalibrate: 'onMeshCalibrate' },
      $t: (key: string) => key,
      $vuetify: { breakpoint: { smAndDown: false } }
    }
  }
}
const slot = { template: '<section><slot /></section>' }
const panelStubs = { 'collapsable-card': slot, 'v-card-text': slot, 'v-alert': slot }

describe('M300 Tune entry, Home All and stable panel order', () => {
  beforeEach(() => vi.clearAllMocks())

  it('accepts only the real unmeasured IDLE state and never offers it for saving', () => {
    const state = readM300PadMesh(idle())
    expect(state?.state).toBe('IDLE')
    expect(isM300PadMeshAccepted(state)).toBe(false)
    for (const change of [
      { run_id: 'a'.repeat(24) }, { points_measured: 1 }, { last_attempt: {} },
      { result: {} }, { phase: 'PROBING' }, { busy: true }
    ]) expect(readM300PadMesh({ ...idle(), ...change })).toBeUndefined()
  })

  it('shows preparation and geometry before any BED_MESH without sending commands', () => {
    const ctx = context()
    const original = JSON.stringify(ctx.source)
    const map = readM300ContactMap(ctx.source.m300_pad_mesh)
    expect(map?.regions).toHaveLength(5)
    expect(map?.points).toHaveLength(25)
    expect(map?.heights.every(z => z === null)).toBe(true)
    const wrapper = shallowMount(M300PadMeshStatus, { mocks: ctx.mocks, stubs: panelStubs })
    expect(wrapper.find('[data-m300-idle]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Opening Tune does not start a measurement')
    expect(wrapper.text()).not.toContain('Save configuration')
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    expect(JSON.stringify(ctx.source)).toBe(original)
    wrapper.destroy()
  })

  it('uses the shared M300 macros for explicit All and Calibrate clicks', () => {
    const ctx = context()
    const wrapper = shallowMount(BedMeshControls, { mocks: ctx.mocks, stubs: panelStubs })
    const controls = wrapper.vm as BedMeshControls
    expect(controls.canCalibrate).toBe(true)
    controls.homeAll()
    controls.calibrate()
    expect(SocketActions.printerGcodeScript).toHaveBeenNthCalledWith(1, 'ZORTRAX_HOME_ALL', { wait: 'onHomeAll' })
    expect(SocketActions.printerGcodeScript).toHaveBeenNthCalledWith(2, 'BED_MESH', { wait: 'onMeshCalibrate' })
    wrapper.destroy()
  })

  it('retains ordinary printer commands and the ordinary pre-homing requirement', async () => {
    const ctx = context()
    Reflect.deleteProperty(ctx.source, 'm300_pad_mesh')
    Reflect.deleteProperty(ctx.source, 'm300_motion')
    const wrapper = shallowMount(BedMeshControls, { mocks: ctx.mocks, stubs: panelStubs })
    const controls = wrapper.vm as BedMeshControls
    expect(controls.canCalibrate).toBe(false)
    controls.calibrate()
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    controls.homeAll()
    expect(SocketActions.printerGcodeScript).toHaveBeenLastCalledWith('G28', { wait: 'onHomeAll' })
    ctx.source.toolhead.homed_axes = 'xyz'
    await Vue.nextTick()
    controls.calibrate()
    expect(SocketActions.printerGcodeScript).toHaveBeenLastCalledWith('BED_MESH_CALIBRATE', { wait: 'onMeshCalibrate' })
    wrapper.destroy()
  })

  it('shows standalone homing while keeping the measurement count at zero', async () => {
    const ctx = context()
    const wrapper = shallowMount(M300PadMeshStatus, { mocks: ctx.mocks, stubs: panelStubs })
    Object.assign(ctx.source.m300_motion, { busy: true, state: 'HOMING', operation: 'HOME_ALL' })
    await Vue.nextTick()
    expect(wrapper.find('[data-m300-homing]').text()).toContain('Homing ALL')
    expect(wrapper.text()).toContain('Homing only — no new mesh measurement.')
    expect(wrapper.text()).toContain('Nozzle actual: 20.2 °C. Nozzle target: 0.0 °C.')
    expect(wrapper.text()).not.toContain('Measuring point')
    expect(ctx.source.m300_pad_mesh.points_measured).toBe(0)
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it.each(['m300_pad_mesh', 'm300_motion'] as const)('does not overlap an active %s operation', owner => {
    const ctx = context()
    ctx.source[owner].busy = true
    const wrapper = shallowMount(BedMeshControls, { mocks: ctx.mocks, stubs: panelStubs })
    const controls = wrapper.vm as BedMeshControls
    expect(controls.canCalibrate).toBe(false)
    controls.homeAll()
    controls.calibrate()
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it.each(['printing', 'paused', 'busy'])('does not send competing commands while %s', state => {
    const ctx = context()
    ctx.mocks.$typedGetters['printer/getPrinterState'] = state
    const wrapper = shallowMount(BedMeshControls, { mocks: ctx.mocks, stubs: panelStubs })
    const controls = wrapper.vm as BedMeshControls
    expect(controls.canCalibrate).toBe(false)
    controls.homeAll()
    controls.calibrate()
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it('does not send commands when Klippy is not Ready', () => {
    const ctx = context()
    ctx.mocks.$typedGetters['printer/getKlippyReady'] = false
    const wrapper = shallowMount(BedMeshControls, { mocks: ctx.mocks, stubs: panelStubs })
    const controls = wrapper.vm as BedMeshControls
    expect(controls.canCalibrate).toBe(false)
    controls.homeAll()
    controls.calibrate()
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    wrapper.destroy()
  })

  it.each(['IDLE', 'PROBING', 'COMPLETE', 'FAILED'])('keeps one map above one heatmap in %s', state => {
    const ctx = context()
    ctx.source.m300_pad_mesh.state = state
    const wrapper = shallowMount(Tune, {
      mocks: ctx.mocks,
      stubs: {
        'v-row': slot,
        'v-col': slot,
        'bed-mesh-card': { template: '<div data-panel="heatmap" />' },
        'm300-pad-contact-map': { template: '<div data-panel="contact-map" />' }
      }
    })
    expect(wrapper.findAll('[data-panel]').wrappers.map(node => node.attributes('data-panel')))
      .toEqual(['contact-map', 'heatmap'])
    expect(SocketActions.printerGcodeScript).not.toHaveBeenCalled()
    wrapper.destroy()
  })
})
