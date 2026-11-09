// SPDX-License-Identifier: GPL-3.0-only
// @vitest-environment jsdom
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Vue from 'vue'
import { shallowMount, type Wrapper } from '@vue/test-utils'
import M300OledPreview from '@/components/widgets/thermals/M300OledPreview.vue'
import { readM300OledPreview, type M300OledPreviewStatus } from './m300-oled-preview'

const control = vi.hoisted(() => ({
  starts: 0,
  stops: 0,
  show: null as ((frame: M300OledPreviewStatus) => Promise<void>) | null,
  live: null as ((active: boolean) => void) | null
}))
vi.mock('@/mixins/state', async () => ({ default: (await import('vue')).default }))
vi.mock('@/api/socketActions', () => ({ SocketActions: { printerObjectsQuery: vi.fn(() => new Promise(() => {})) } }))
vi.mock('@/util/m300-oled-navigation', () => ({
  M300NavigationEvents: class {
    constructor (show: (frame: M300OledPreviewStatus) => Promise<void>, live: (active: boolean) => void) {
      control.show = show; control.live = live
    }

    start () { control.starts++; control.live?.(true) }
    stop () { control.stops++; control.live?.(false) }
  }
}))

const raw = {
  online: true,
  sequence: 1,
  width: 256,
  height: 64,
  format: 'indexed4-png',
  source: 'host-rendered',
  image_base64: 'iVBORw0KGgo=',
  epoch: 'a'.repeat(32),
  navigation_revision: 1,
  navigation_api: 'NAV-EVENT-1'
}
const frame = (sequence: number, image_base64: string) => readM300OledPreview({
  m300_oled: { oled_preview: { ...raw, sequence, navigation_revision: sequence, image_base64 } }
})!
const images: TestImage[] = []
class TestImage {
  src = ''
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor () { images.push(this) }
}
const draw = vi.fn()
let wrapper: Wrapper<Vue> | undefined
async function mountPreview () {
  wrapper = shallowMount(M300OledPreview, {
    mocks: {
      socketReady: true,
      klippyReady: true,
      $typedState: Vue.observable({ printer: { printer: { m300_oled: { oled_preview: raw } } } })
    },
    stubs: { 'v-divider': true, 'v-btn': true }
  })
  await Vue.nextTick(); await Vue.nextTick()
  return wrapper
}

beforeEach(() => {
  vi.useFakeTimers()
  control.starts = control.stops = 0
  images.length = 0
  draw.mockClear()
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: draw } as unknown as CanvasRenderingContext2D)
  vi.stubGlobal('Image', TestImage)
})
afterEach(() => {
  wrapper?.destroy(); wrapper = undefined
  vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers()
})

describe('M300 navigation canvas', () => {
  it('retains native pixels and the fixed 344 by 86 layout', async () => {
    const view = await mountPreview()
    expect(view.find('canvas').attributes('width')).toBe('256')
    expect(view.find('canvas').attributes('height')).toBe('64')
    const source = readFileSync('src/components/widgets/thermals/M300OledPreview.vue', 'utf8')
    expect(source).toContain('width: 344px;')
    expect(source).toContain('height: 86px;')
    expect(source).not.toContain('height: auto;')
    expect(control.starts).toBeGreaterThan(0)
  })

  it('cannot repaint an old selection when its PNG finishes decoding late', async () => {
    await mountPreview()
    const old = images.at(-1)!
    const shown = control.show!(frame(16, 'dGVzdA=='))
    await Vue.nextTick(); await Vue.nextTick()
    const newest = images.at(-1)!
    expect(newest).not.toBe(old)
    newest.onload?.(); await shown
    old.onload?.()
    expect(draw).toHaveBeenCalledTimes(1)
    expect(draw).toHaveBeenLastCalledWith(newest, 0, 0, 256, 64)
  })

  it('cancels navigation when collapsed and re-arms when opened', async () => {
    const view = await mountPreview()
    const before = control.stops
    await view.setData({ collapsed: true })
    expect(control.stops).toBeGreaterThan(before)
    expect(view.find('canvas').exists()).toBe(false)
    const starts = control.starts
    await view.setData({ collapsed: false })
    expect(control.starts).toBeGreaterThan(starts)
  })

  it('never paints onto a removed widget after an outstanding decode', async () => {
    await mountPreview()
    const shown = control.show!(frame(2, 'dGVzdA=='))
    await Vue.nextTick(); await Vue.nextTick()
    const pending = images.at(-1)!
    wrapper!.destroy(); wrapper = undefined
    pending.onload?.(); await shown
    expect(draw).not.toHaveBeenCalled()
  })
})
